// Display helpers for Geoapify-derived place data.

function titleCase(text) {
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/**
 * Geoapify returns hierarchical categories, e.g.
 * ["tourism", "tourism.sights", "tourism.sights.memorial"].
 * Show only the most specific ones, as readable labels.
 */
// Geoapify attribute groups (amenities, building type, diet, access) rather
// than "what kind of place is this"; they make poor tags.
const ATTRIBUTE_GROUPS = new Set([
  'access',
  'access_limited',
  'building',
  'dogs',
  'no_dogs',
  'fee',
  'no_fee',
  'internet_access',
  'wheelchair',
  'vegetarian',
  'vegan',
  'halal',
  'kosher',
  'organic',
  'gluten_free',
  'sugar_free',
  'egg_free',
  'soy_free',
  'low_emission_zone',
  'populated_place',
  'political',
])
const UNINFORMATIVE_LEAVES = new Set(['yes', 'no', 'limited', 'other'])

export function categoryLabels(categories = [], max = 3) {
  const relevant = categories.filter((c) => !ATTRIBUTE_GROUPS.has(c.split('.')[0]))
  const leaves = relevant.filter(
    (c) => !relevant.some((other) => other !== c && other.startsWith(`${c}.`)),
  )
  const labels = leaves
    .map((c) => c.split('.').pop())
    .filter((leaf) => !UNINFORMATIVE_LEAVES.has(leaf))
    .map((leaf) => titleCase(leaf.replaceAll('_', ' ')))
  return [...new Set(labels)].slice(0, max)
}

export function placeName(place) {
  const name = place.name?.trim()
  if (name) return name
  // Many OpenStreetMap features have no name; describe them by type instead.
  const [kind] = categoryLabels(place.categories, 1)
  return kind ? `Unnamed ${kind.toLowerCase()}` : 'Unnamed place'
}

export function formatCoordinate(value, axis) {
  const hemisphere = axis === 'lat' ? (value >= 0 ? 'N' : 'S') : value >= 0 ? 'E' : 'W'
  return `${Math.abs(value).toFixed(4)}° ${hemisphere}`
}

export function formatCoordinates(lat, lon) {
  return `${formatCoordinate(lat, 'lat')}, ${formatCoordinate(lon, 'lon')}`
}

export function formatDistanceKm(meters) {
  const km = meters / 1000
  return `${Number.isInteger(km) ? km : km.toFixed(1)} km`
}

export function osmUrl(lat, lon) {
  return `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=17/${lat}/${lon}`
}

const dateFormatter = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' })

export function formatDate(iso) {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? '' : dateFormatter.format(date)
}

// Trip dates are calendar dates ("2026-11-03"). Parse them as local dates:
// new Date("2026-11-03") would be UTC midnight and can show the previous day.
function parseCalendarDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso ?? '')
  return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : null
}

const dayFormatter = new Intl.DateTimeFormat(undefined, { weekday: 'short', day: 'numeric', month: 'short' })
const longDayFormatter = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', year: 'numeric' })

export function formatTripDay(iso) {
  const d = parseCalendarDate(iso)
  return d ? dayFormatter.format(d) : ''
}

export function formatTripRange(startIso, endIso) {
  const start = parseCalendarDate(startIso)
  const end = parseCalendarDate(endIso)
  if (!start) return ''
  if (!end || end.getTime() === start.getTime()) return longDayFormatter.format(start)
  return `${longDayFormatter.format(start)} to ${longDayFormatter.format(end)}`
}

export function formatKm(km) {
  return km < 1 ? `${Math.round(km * 1000 / 10) * 10} m` : `${km.toFixed(1)} km`
}

/** Great-circle distance in km (straight line, not a travel distance). */
export function straightLineKm(aLat, aLon, bLat, bLon) {
  const toRad = (x) => (x * Math.PI) / 180
  const dLat = toRad(bLat - aLat)
  const dLon = toRad(bLon - aLon)
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(aLat)) * Math.cos(toRad(bLat)) * Math.sin(dLon / 2) ** 2
  return 2 * 6371.0088 * Math.asin(Math.min(1, Math.sqrt(h)))
}
