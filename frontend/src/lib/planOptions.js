// Options accepted by POST /api/trips (see backend trips.py).

export const INTERESTS = [
  { value: 'culture', label: 'Culture' },
  { value: 'history', label: 'History' },
  { value: 'nature', label: 'Nature' },
  { value: 'food', label: 'Food' },
  { value: 'shopping', label: 'Shopping' },
  { value: 'nightlife', label: 'Nightlife' },
  { value: 'beaches', label: 'Beaches' },
  { value: 'entertainment', label: 'Entertainment' },
]

export const PACES = [
  { value: 'relaxed', label: 'Relaxed', detail: '2 stops a day' },
  { value: 'balanced', label: 'Balanced', detail: '3 stops a day' },
  { value: 'packed', label: 'Packed', detail: 'Up to 5 stops a day' },
]

export const MAX_ROUTE_CITIES = 10

/**
 * Read a #plan?... prefill (see planLink in useHashRoute.js). Anything that is
 * not a known pace or interest is dropped; city names are only text for the
 * form, which still geocodes them and asks when a name is ambiguous.
 */
export function parsePlanPrefill(query) {
  if (!query) return null
  const params = new URLSearchParams(query)
  const clean = (text) => text.trim().replace(/\s+/g, ' ').slice(0, 200)
  const list = (key) => (params.get(key) ?? '').split(',').map(clean).filter(Boolean)
  // One `city` parameter per city; names may contain commas ("Porto, Portugal").
  const cities = params.getAll('city').map(clean).filter(Boolean).slice(0, MAX_ROUTE_CITIES)
  const pace = PACES.some((p) => p.value === params.get('pace')) ? params.get('pace') : null
  const interests = [...new Set(list('interests'))].filter((i) => INTERESTS.some((o) => o.value === i))
  if (!cities.length && !pace && !interests.length) return null
  return { cities, pace, interests }
}
