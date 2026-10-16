// Anonymous trip identity: a UUID generated once per browser and kept in
// localStorage. The backend requires the canonical 8-4-4-4-12 form.

const STORAGE_KEY = 'tripwise.tripId'
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/

function newUuid() {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  // crypto.randomUUID needs a secure context (https or localhost). Fall back
  // to an RFC 4122 v4 UUID built from getRandomValues, e.g. on a LAN IP.
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

let cached = null

export function getTripId() {
  if (cached) return cached
  try {
    const stored = localStorage.getItem(STORAGE_KEY)?.toLowerCase()
    if (stored && UUID_RE.test(stored)) {
      cached = stored
      return cached
    }
  } catch {
    // Storage blocked: fall through and use an in-memory ID for this session.
  }
  cached = newUuid()
  try {
    localStorage.setItem(STORAGE_KEY, cached)
  } catch {
    // Not persisted; the trip lasts for this page session only.
  }
  return cached
}
