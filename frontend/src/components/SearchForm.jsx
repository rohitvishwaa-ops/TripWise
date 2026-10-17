import { useEffect, useId, useRef, useState } from 'react'
import { Crosshair, MagnifyingGlass, MapPin } from '@phosphor-icons/react'
import { geocodeLocation } from '../lib/api.js'
import { formatDistanceKm } from '../lib/format.js'

// Geoapify category keys accepted by GET /api/places.
const CATEGORIES = [
  { value: 'tourism.sights', label: 'Sights' },
  { value: 'tourism.attraction', label: 'Attractions' },
  { value: 'entertainment.museum', label: 'Museums' },
  { value: 'heritage', label: 'Heritage' },
  { value: 'tourism.attraction.viewpoint', label: 'Viewpoints' },
  { value: 'leisure.park', label: 'Parks' },
  { value: 'natural', label: 'Nature' },
  { value: 'beach', label: 'Beaches' },
  { value: 'catering.restaurant', label: 'Restaurants' },
  { value: 'catering.cafe', label: 'Cafés' },
  { value: 'accommodation.hotel', label: 'Hotels' },
]

const LIMITS = [20, 50, 100]
const MIN_NAME_LENGTH = 2

function normalizeName(text) {
  return text.trim().replace(/\s+/g, ' ')
}
const RADIUS = { min: 500, max: 50000, step: 500, initial: 5000 }

// `badInput`: the number field holds unparseable text (e.g. just "-"), which
// browsers report as an empty value.
function validateCoordinate(raw, min, max, name, badInput) {
  const text = raw.trim()
  if (badInput) return `${name[0].toUpperCase()}${name.slice(1)} must be a number.`
  if (!text) return `Enter a ${name}.`
  const value = Number(text)
  if (!Number.isFinite(value)) return `${name[0].toUpperCase()}${name.slice(1)} must be a number.`
  if (value < min || value > max) return `Use a value from ${min} to ${max}.`
  return null
}

function validate(fields, badInput = {}) {
  const errors = {}
  const lat = validateCoordinate(fields.latitude, -90, 90, 'latitude', badInput.latitude)
  const lon = validateCoordinate(fields.longitude, -180, 180, 'longitude', badInput.longitude)
  if (lat) errors.latitude = lat
  if (lon) errors.longitude = lon
  return errors
}

const GEO_ERRORS = {
  1: 'Location access was blocked. Allow it in your browser settings or enter coordinates.',
  2: "Your location isn't available right now. Enter coordinates instead.",
  3: 'Finding your location took too long. Try again or enter coordinates.',
}

export default function SearchForm({ onSearch, busy }) {
  const uid = useId()
  const ids = {
    lat: `${uid}-lat`,
    lon: `${uid}-lon`,
    radius: `${uid}-radius`,
    limit: `${uid}-limit`,
    name: `${uid}-name`,
    matches: `${uid}-matches`,
  }
  const [mode, setMode] = useState('name') // 'name' | 'coords'
  const [nameText, setNameText] = useState('')
  const [nameError, setNameError] = useState(null)
  const [geocoding, setGeocoding] = useState(false)
  const [matches, setMatches] = useState(null) // { query, results } awaiting a choice
  const [resolved, setResolved] = useState(null) // chosen location + the text it answers
  const nameRef = useRef(null)
  const matchesRef = useRef(null)
  const geocodeController = useRef(null)
  const [fields, setFields] = useState({ latitude: '', longitude: '' })
  const [errors, setErrors] = useState({})
  const [radius, setRadius] = useState(RADIUS.initial)
  const [categories, setCategories] = useState([])
  const [limit, setLimit] = useState(LIMITS[0])
  const [geo, setGeo] = useState({ state: 'idle', message: '' })
  const latRef = useRef(null)
  const lonRef = useRef(null)

  const geoSupported = typeof navigator !== 'undefined' && 'geolocation' in navigator

  useEffect(() => () => geocodeController.current?.abort(), [])

  // When several locations match, move focus to the choices so keyboard and
  // screen-reader users land on them.
  useEffect(() => {
    if (matches) matchesRef.current?.focus()
  }, [matches])

  function updateName(value) {
    setNameText(value)
    if (nameError) setNameError(null)
    if (matches) setMatches(null)
  }

  function switchMode(next) {
    setMode(next)
    setNameError(null)
    setMatches(null)
    setErrors({})
  }

  function updateField(name, value) {
    setFields((prev) => ({ ...prev, [name]: value }))
    // Clear an error as soon as the user starts correcting it.
    if (errors[name]) setErrors((prev) => ({ ...prev, [name]: undefined }))
  }

  function readBadInput() {
    return {
      latitude: latRef.current?.validity.badInput ?? false,
      longitude: lonRef.current?.validity.badInput ?? false,
    }
  }

  function validateOnBlur(name, event) {
    // Moving focus to Search: submit validates everything. Showing the error
    // here would shift the button mid-click and swallow the submit.
    if (event?.relatedTarget?.type === 'submit') return
    const badInput = readBadInput()
    if (!fields[name].trim() && !badInput[name]) return
    const next = validate(fields, badInput)
    setErrors((prev) => ({ ...prev, [name]: next[name] }))
  }

  function toggleCategory(value) {
    setCategories((prev) =>
      prev.includes(value) ? prev.filter((c) => c !== value) : [...prev, value],
    )
  }

  function locateMe() {
    setGeo({ state: 'locating', message: 'Finding your location…' })
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const latitude = pos.coords.latitude.toFixed(5)
        const longitude = pos.coords.longitude.toFixed(5)
        setFields({ latitude, longitude })
        switchMode('coords')
        setGeo({ state: 'done', message: 'Location filled in. Adjust filters, then search.' })
      },
      (err) => {
        setGeo({ state: 'error', message: GEO_ERRORS[err.code] ?? GEO_ERRORS[2] })
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 },
    )
  }

  function searchAt(location) {
    onSearch({
      latitude: location.latitude,
      longitude: location.longitude,
      label: location.address || location.name,
      radius,
      categories,
      limit,
    })
  }

  function chooseLocation(location, query) {
    setResolved({ ...location, query })
    setMatches(null)
    searchAt(location)
  }

  async function submitName() {
    const query = normalizeName(nameText)
    if (query.length < MIN_NAME_LENGTH) {
      setNameError(
        query ? `Enter at least ${MIN_NAME_LENGTH} characters.` : 'Enter a city or place name.',
      )
      return nameRef.current?.focus()
    }
    // Same text as the location already chosen: reuse it (e.g. new filters).
    if (resolved && resolved.query === query) return searchAt(resolved)

    geocodeController.current?.abort()
    const controller = new AbortController()
    geocodeController.current = controller
    setGeocoding(true)
    setNameError(null)
    setMatches(null)
    try {
      const data = await geocodeLocation(query, { signal: controller.signal })
      if (data.count === 0) {
        setResolved(null)
        setNameError(
          `No location found for "${query}". Check the spelling or add a country, like "Porto, Portugal".`,
        )
        nameRef.current?.focus()
      } else if (data.confident) {
        chooseLocation(data.results[0], query)
      } else {
        // Never guess between candidates: let the user pick.
        setResolved(null)
        setMatches({ query, results: data.results })
      }
    } catch (err) {
      if (controller.signal.aborted) return
      setResolved(null)
      setNameError(`Couldn't look up that location. ${err.message}`)
    } finally {
      if (geocodeController.current === controller) setGeocoding(false)
    }
  }

  function handleSubmit(event) {
    event.preventDefault()
    if (mode === 'name') return submitName()
    const nextErrors = validate(fields, readBadInput())
    setErrors(nextErrors)
    if (nextErrors.latitude) return latRef.current?.focus()
    if (nextErrors.longitude) return lonRef.current?.focus()
    onSearch({
      latitude: Number(fields.latitude),
      longitude: Number(fields.longitude),
      label: null,
      radius,
      categories,
      limit,
    })
  }

  return (
    <form className="search-form" onSubmit={handleSubmit} noValidate aria-label="Search places">
      <fieldset className="field-group">
        <legend className="field-group__legend">Location</legend>

        <fieldset className="segmented segmented--block">
          <legend className="visually-hidden">Search by</legend>
          {[
            { value: 'name', label: 'Place name' },
            { value: 'coords', label: 'Coordinates' },
          ].map((opt) => (
            <label key={opt.value} className="segmented__option">
              <input
                type="radio"
                className="sr-input"
                name={`${uid}-mode`}
                value={opt.value}
                checked={mode === opt.value}
                onChange={() => switchMode(opt.value)}
              />
              <span>{opt.label}</span>
            </label>
          ))}
        </fieldset>

        {mode === 'name' && (
          <div className="field">
            <label htmlFor={ids.name}>City or place</label>
            <span className="hint" id={`${ids.name}-hint`}>
              A city, landmark or address. Add a country if the name is common.
            </span>
            <input
              ref={nameRef}
              id={ids.name}
              name="location"
              type="search"
              autoComplete="off"
              enterKeyHint="search"
              maxLength={200}
              value={nameText}
              onChange={(e) => updateName(e.target.value)}
              aria-invalid={nameError ? 'true' : undefined}
              aria-describedby={`${ids.name}-hint${nameError ? ` ${ids.name}-error` : ''}`}
              required
            />
            {nameError && (
              <p className="field-error" id={`${ids.name}-error`} role="alert">
                {nameError}
              </p>
            )}
            {resolved && !matches && !nameError && resolved.query === normalizeName(nameText) && (
              <p className="hint resolved">
                <MapPin aria-hidden="true" size={14} weight="fill" />
                Using {resolved.address || resolved.name}
              </p>
            )}
            {matches && (
              <div
                className="matches"
                ref={matchesRef}
                tabIndex={-1}
                role="group"
                aria-labelledby={ids.matches}
              >
                <p id={ids.matches} className="matches__title">
                  {matches.results.length} places match "{matches.query}". Choose one:
                </p>
                <ul className="matches__list" role="list">
                  {matches.results.map((loc, i) => (
                    <li key={loc.id ?? i}>
                      <button
                        type="button"
                        className="match"
                        onClick={() => chooseLocation(loc, matches.query)}
                        disabled={busy}
                      >
                        <span className="match__name">{loc.name}</span>
                        {loc.address && loc.address !== loc.name && (
                          <span className="match__address">{loc.address}</span>
                        )}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {geoSupported && (
          <div className="geo">
            <button
              type="button"
              className="btn btn--ghost"
              onClick={locateMe}
              disabled={geo.state === 'locating'}
            >
              <Crosshair aria-hidden="true" size={18} weight="bold" />
              {geo.state === 'locating' ? 'Locating…' : 'Use my location'}
            </button>
            {geo.message && (
              <p
                className={`hint ${geo.state === 'error' ? 'hint--error' : ''}`}
                role={geo.state === 'error' ? 'alert' : 'status'}
              >
                {geo.message}
              </p>
            )}
          </div>
        )}

        {mode === 'coords' && (
        <div className="coords">
          <div className="field">
            <label htmlFor={ids.lat}>Latitude</label>
            <span className="hint" id={`${ids.lat}-hint`}>
              -90 to 90
            </span>
            <input
              ref={latRef}
              id={ids.lat}
              name="latitude"
              type="number"
              step="any"
              min="-90"
              max="90"
              inputMode="decimal"
              enterKeyHint="next"
              value={fields.latitude}
              onChange={(e) => updateField('latitude', e.target.value)}
              onBlur={(e) => validateOnBlur('latitude', e)}
              aria-invalid={errors.latitude ? 'true' : undefined}
              aria-describedby={`${ids.lat}-hint${errors.latitude ? ` ${ids.lat}-error` : ''}`}
              required
            />
            {errors.latitude && (
              <p className="field-error" id={`${ids.lat}-error`}>
                {errors.latitude}
              </p>
            )}
          </div>
          <div className="field">
            <label htmlFor={ids.lon}>Longitude</label>
            <span className="hint" id={`${ids.lon}-hint`}>
              -180 to 180
            </span>
            <input
              ref={lonRef}
              id={ids.lon}
              name="longitude"
              type="number"
              step="any"
              min="-180"
              max="180"
              inputMode="decimal"
              enterKeyHint="search"
              value={fields.longitude}
              onChange={(e) => updateField('longitude', e.target.value)}
              onBlur={(e) => validateOnBlur('longitude', e)}
              aria-invalid={errors.longitude ? 'true' : undefined}
              aria-describedby={`${ids.lon}-hint${errors.longitude ? ` ${ids.lon}-error` : ''}`}
              required
            />
            {errors.longitude && (
              <p className="field-error" id={`${ids.lon}-error`}>
                {errors.longitude}
              </p>
            )}
          </div>
        </div>
        )}

        <div className="field">
          <div className="field__row">
            <label htmlFor={ids.radius}>Search radius</label>
            <output htmlFor={ids.radius} className="radius-value">
              {formatDistanceKm(radius)}
            </output>
          </div>
          <input
            id={ids.radius}
            name="radius"
            type="range"
            className="range"
            min={RADIUS.min}
            max={RADIUS.max}
            step={RADIUS.step}
            value={radius}
            onChange={(e) => setRadius(Number(e.target.value))}
            aria-valuetext={formatDistanceKm(radius)}
          />
        </div>
      </fieldset>

      <fieldset className="field-group">
        <legend className="field-group__legend">Categories</legend>
        <p className="hint" id={`${uid}-cat-hint`}>
          Pick any. Leave all off to see general tourism spots.
        </p>
        <div className="chips" aria-describedby={`${uid}-cat-hint`}>
          {CATEGORIES.map((cat) => (
            <label key={cat.value} className="chip">
              <input
                type="checkbox"
                className="sr-input"
                name="categories"
                value={cat.value}
                checked={categories.includes(cat.value)}
                onChange={() => toggleCategory(cat.value)}
              />
              <span>{cat.label}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="field field--inline">
        <label htmlFor={ids.limit}>Show up to</label>
        <select
          id={ids.limit}
          name="limit"
          className="select"
          value={limit}
          onChange={(e) => setLimit(Number(e.target.value))}
        >
          {LIMITS.map((n) => (
            <option key={n} value={n}>
              {n} places
            </option>
          ))}
        </select>
      </div>

      <button type="submit" className="btn btn--primary btn--block" disabled={busy || geocoding}>
        <MagnifyingGlass aria-hidden="true" size={18} weight="bold" />
        {geocoding ? 'Finding location…' : busy ? 'Searching…' : 'Search places'}
      </button>
    </form>
  )
}
