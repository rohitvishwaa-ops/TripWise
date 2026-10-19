// Thin client for the TripWise FastAPI backend. Geoapify is only ever called
// by the backend; the browser never sees an API key.

import { FirebaseAuthError, getIdToken } from './firebaseAuth.js'

const API_URL = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/+$/, '')
const TIMEOUT_MS = 20000

export class ApiError extends Error {
  constructor(message, { status = 0, kind = 'http' } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.kind = kind // 'http' | 'network' | 'timeout'
  }
}

function messageFor(status, detail) {
  // Backend error details are fixed, user-safe strings; 422s are arrays.
  if (typeof detail === 'string' && detail) return detail
  if (status === 422) return 'Some of the values sent were not accepted. Check them and try again.'
  if (status >= 500) return 'The server ran into a problem. Try again in a moment.'
  return `Request failed (HTTP ${status}).`
}

async function request(path, { method = 'GET', tripId, body, signal, timeoutMs = TIMEOUT_MS } = {}) {
  const controller = new AbortController()
  let timedOut = false
  const timer = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)
  const onAbort = () => controller.abort()
  signal?.addEventListener('abort', onAbort, { once: true })

  const headers = { Accept: 'application/json' }
  if (tripId) headers['X-Trip-ID'] = tripId
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  try {
    const idToken = await getIdToken()
    if (idToken) headers.Authorization = `Bearer ${idToken}`
  } catch (err) {
    if (err instanceof FirebaseAuthError) {
      throw new ApiError('Your session has expired. Sign in again to continue.', { status: 401 })
    }
    throw err
  }

  let response
  try {
    response = await fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    })
  } catch (err) {
    if (signal?.aborted) throw err // caller cancelled; let them ignore it
    if (timedOut) {
      throw new ApiError('The request took too long. Try again.', { kind: 'timeout' })
    }
    throw new ApiError(
      "Can't reach the TripWise server. Check that the backend is running and try again.",
      { kind: 'network' },
    )
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', onAbort)
  }

  if (response.status === 204) return null

  let data = null
  try {
    data = await response.json()
  } catch {
    data = null
  }

  if (!response.ok) {
    throw new ApiError(messageFor(response.status, data?.detail), { status: response.status })
  }
  return data
}

/**
 * GET /api/places
 * params: { latitude, longitude, radius, categories: string[], limit, sort }
 * returns { count, places: [{ id, name, address, latitude, longitude, categories }] }
 */
export function searchPlaces(params, { signal } = {}) {
  const query = new URLSearchParams({
    latitude: String(params.latitude),
    longitude: String(params.longitude),
    radius: String(params.radius),
    limit: String(params.limit),
    sort: params.sort,
  })
  if (params.categories?.length) query.set('categories', params.categories.join(','))
  return request(`/api/places?${query}`, { signal })
}

/**
 * GET /api/geocode: city/place name -> candidate locations.
 * returns { query, count, confident, results: [{ id, name, address, latitude,
 *           longitude, type, country, confidence }] }
 * `confident` is true only when one result clearly fits; otherwise the user chooses.
 */
export function geocodeLocation(text, { signal } = {}) {
  const query = new URLSearchParams({ text, limit: '5' })
  return request(`/api/geocode?${query}`, { signal })
}

/** GET /api/itinerary -> { trip_id, count, places: [{ ...place, added_at }] } */
export function getItinerary(tripId, { signal } = {}) {
  return request('/api/itinerary', { tripId, signal })
}

/** POST /api/itinerary -> saved place (201); 409 if already saved. */
export function addToItinerary(tripId, place) {
  const { id, name, address, latitude, longitude, categories } = place
  return request('/api/itinerary', {
    method: 'POST',
    tripId,
    body: { id, name, address, latitude, longitude, categories: categories ?? [] },
  })
}

/** DELETE /api/itinerary/{place_id} -> 204; 404 if not in this trip. */
export function removeFromItinerary(tripId, placeId) {
  return request(`/api/itinerary/${encodeURIComponent(placeId)}`, {
    method: 'DELETE',
    tripId,
  })
}

// --- Trip planner -----------------------------------------------------------

// Generation makes several Geoapify requests (one per interest, possibly a
// wider second pass), so allow more time than ordinary requests.
const GENERATE_TIMEOUT_MS = 60000

/** GET /api/trips -> { count, trips: [summary] } (newest first) */
export function listTrips(tripId, { signal } = {}) {
  return request('/api/trips', { tripId, signal })
}

/** GET /api/trips/{id} -> full trip with cities, days and activities */
export function getTrip(tripId, id, { signal } = {}) {
  return request(`/api/trips/${encodeURIComponent(id)}`, { tripId, signal })
}

/**
 * POST /api/trips. With generate=true the backend fills the days with real
 * places (single city only for now). Returns the full trip plus `warnings`.
 */
export function createTrip(tripId, body, { signal } = {}) {
  return request('/api/trips', {
    method: 'POST',
    tripId,
    body,
    signal,
    timeoutMs: body.generate ? GENERATE_TIMEOUT_MS : TIMEOUT_MS,
  })
}

// --- Itinerary editing (all return the full, updated trip) -------------------

const tripPath = (id) => `/api/trips/${encodeURIComponent(id)}`

/** PUT .../days/{dayId}/order: activityIds must list every activity of the day once. */
export function reorderDay(tripId, id, dayId, activityIds) {
  return request(`${tripPath(id)}/days/${dayId}/order`, {
    method: 'PUT',
    tripId,
    body: { activity_ids: activityIds },
  })
}

/** PATCH .../activities/{activityId}: { note } and/or { day_id, position } */
export function updateActivity(tripId, id, activityId, changes) {
  return request(`${tripPath(id)}/activities/${activityId}`, { method: 'PATCH', tripId, body: changes })
}

/** DELETE .../activities/{activityId} */
export function deleteActivity(tripId, id, activityId) {
  return request(`${tripPath(id)}/activities/${activityId}`, { method: 'DELETE', tripId })
}

/** POST .../activities: add a saved place; without day_id the closest day is used. */
export function addTripActivity(tripId, id, { place, dayId = null, note = null }) {
  const { id: placeId, name, address, latitude, longitude, categories } = place
  return request(`${tripPath(id)}/activities`, {
    method: 'POST',
    tripId,
    body: {
      place: { id: placeId, name, address, latitude, longitude, categories: categories ?? [] },
      day_id: dayId,
      note,
    },
  })
}

/** POST .../days/{dayId}/regenerate: fresh automatic suggestions for one day. */
export function regenerateDay(tripId, id, dayId) {
  return request(`${tripPath(id)}/days/${dayId}/regenerate`, {
    method: 'POST',
    tripId,
    timeoutMs: GENERATE_TIMEOUT_MS,
  })
}
