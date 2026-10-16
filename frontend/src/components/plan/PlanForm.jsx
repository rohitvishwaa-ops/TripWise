import { useEffect, useId, useRef, useState } from 'react'
import { ArrowClockwise, MapPin, Minus, Plus, WarningCircle } from '@phosphor-icons/react'
import { createTrip, geocodeLocation } from '../../lib/api.js'
import { useTrip } from '../../state/TripContext.jsx'
import { INTERESTS, PACES } from '../../lib/planOptions.js'
import CityRoute, { MAX_TRIP_DAYS } from './CityRoute.jsx'

const MIN_DAYS = 1
const MAX_DAYS = 30

function normalize(text) {
  return text.trim().replace(/\s+/g, ' ')
}

function validate({ cityText, days, startDate, startDateBad }) {
  const errors = {}
  const city = normalize(cityText)
  if (!city) errors.city = 'Enter a city to plan.'
  else if (city.length < 2) errors.city = 'Enter at least 2 characters.'
  const n = Number(days)
  if (days === '' || !Number.isInteger(n)) errors.days = 'Enter a whole number of days.'
  else if (n < MIN_DAYS || n > MAX_DAYS) errors.days = `Choose between ${MIN_DAYS} and ${MAX_DAYS} days.`
  if (startDateBad || (startDate && !/^\d{4}-\d{2}-\d{2}$/.test(startDate))) {
    errors.startDate = 'Enter a valid date, or leave it empty.'
  }
  return errors
}

function sameCity(a, b) {
  if (a.name.toLowerCase() === b.name.toLowerCase()) return true
  const dLat = (a.latitude - b.latitude) * 111
  const dLon = (a.longitude - b.longitude) * 111 * Math.cos((a.latitude * Math.PI) / 180)
  return Math.hypot(dLat, dLon) < 1
}

let rowSeq = 0
const newRow = (days) => ({ key: `row-${++rowSeq}`, text: '', days: String(days), resolved: null, matches: null, error: null })

/**
 * Plan a single-city or multi-city trip. Resolves the city with GET /api/geocode (asking
 * the user to choose when several places match), then POSTs to /api/trips
 * with generate=true. Calls onCreated(trip) with the saved, generated trip.
 */
export default function PlanForm({ onCreated, onBusyChange }) {
  const uid = useId()
  const { tripId } = useTrip()
  const [cityText, setCityText] = useState('')
  const [days, setDays] = useState('3')
  const [startDate, setStartDate] = useState('')
  const [pace, setPace] = useState('balanced')
  const [interests, setInterests] = useState([])
  const [title, setTitle] = useState('')
  const [errors, setErrors] = useState({})
  const [phase, setPhase] = useState('idle') // idle | locating | generating
  const [matches, setMatches] = useState(null) // { query, results }
  const [resolved, setResolved] = useState(null) // { ...location, query }
  const [failure, setFailure] = useState(null) // { message, retryable }
  const [mode, setMode] = useState('single') // 'single' | 'multi'
  const [rows, setRows] = useState(() => [newRow(2), newRow(2)])
  const [focusRowKey, setFocusRowKey] = useState(null)
  const cityRef = useRef(null)
  const daysRef = useRef(null)
  const dateRef = useRef(null)
  const matchesRef = useRef(null)
  const controller = useRef(null)

  const busy = phase !== 'idle'

  useEffect(() => () => controller.current?.abort(), [])
  useEffect(() => {
    if (matches) matchesRef.current?.focus()
  }, [matches])

  function clearError(name) {
    if (errors[name]) setErrors((prev) => ({ ...prev, [name]: undefined }))
  }

  function updateCity(value) {
    setCityText(value)
    clearError('city')
    setMatches(null)
    setFailure(null)
  }

  function stepDays(delta) {
    const n = Number.parseInt(days, 10)
    const next = Math.min(MAX_DAYS, Math.max(MIN_DAYS, (Number.isNaN(n) ? 3 : n) + delta))
    setDays(String(next))
    clearError('days')
  }

  function toggleInterest(value) {
    setInterests((prev) => (prev.includes(value) ? prev.filter((i) => i !== value) : [...prev, value]))
  }

  function setBusy(next, label) {
    setPhase(next)
    onBusyChange?.(next === 'idle' ? null : { phase: next, label })
  }

  function cityPayload(location, cityDays) {
    return {
      name: location.name.slice(0, 200),
      address: location.address?.slice(0, 1000) ?? null,
      latitude: location.latitude,
      longitude: location.longitude,
      days: cityDays,
    }
  }

  async function generate(location, query) {
    setResolved({ ...location, query })
    setMatches(null)
    return generateTrip([cityPayload(location, Number(days))], location.name)
  }

  async function generateTrip(cities, label) {
    const ctrl = new AbortController()
    controller.current = ctrl
    setBusy('generating', label)
    try {
      const trip = await createTrip(
        tripId,
        {
          title: normalize(title) || null,
          start_date: startDate || null,
          pace,
          interests,
          generate: true,
          cities,
        },
        { signal: ctrl.signal },
      )
      setBusy('idle')
      onCreated(trip)
    } catch (err) {
      if (ctrl.signal.aborted) return
      setBusy('idle')
      // 422 from generation = no/too few places: changing inputs helps, retrying doesn't.
      setFailure({
        message: err.message,
        retryable: err.kind !== 'http' || err.status >= 500,
      })
    }
  }

  const multiTotal = rows.reduce((n, r) => n + (Number.parseInt(r.days, 10) || 0), 0)
  const multiTotalError =
    multiTotal > MAX_TRIP_DAYS ? `The whole trip can be at most ${MAX_TRIP_DAYS} days.` : null

  function focusRow(key, part = 'city') {
    document.getElementById(`${uid}-${part}-${key}`)?.focus()
  }

  /**
   * Multi-city: validate every row, then resolve unresolved cities one by one.
   * An ambiguous city stops the flow until the user picks a match; picking
   * calls this again with the updated rows, so it continues automatically.
   */
  async function submitMulti(snapshot = rows) {
    let current = snapshot.map((r) => ({ ...r, error: null, daysError: null }))
    let invalid = null
    current = current.map((r) => {
      const text = normalize(r.text)
      const n = Number(r.days)
      const next = { ...r }
      if (!text) next.error = 'Enter a city.'
      else if (text.length < 2) next.error = 'Enter at least 2 characters.'
      if (r.days === '' || !Number.isInteger(n) || n < 1 || n > MAX_TRIP_DAYS) {
        next.daysError = `Choose between 1 and ${MAX_TRIP_DAYS} days.`
      }
      if (!invalid && (next.error || next.daysError)) invalid = { key: r.key, part: next.error ? 'city' : 'days' }
      return next
    })
    const startDateBad = dateRef.current?.validity.badInput ?? false
    const dateError = startDateBad || (startDate && !/^\d{4}-\d{2}-\d{2}$/.test(startDate))
    setErrors(dateError ? { startDate: 'Enter a valid date, or leave it empty.' } : {})
    setRows(current)
    if (invalid) return focusRow(invalid.key, invalid.part)
    if (multiTotalError) return
    if (dateError) return dateRef.current?.focus()

    // Immutable updates: every change makes a new array and a new row object.
    const patch = (index, changes) => {
      current = current.map((r, j) => (j === index ? { ...r, ...changes } : r))
      setRows(current)
    }

    for (let i = 0; i < current.length; i++) {
      const row = current[i]
      const query = normalize(row.text)
      if (row.resolved && row.resolved.query === query) continue
      controller.current?.abort()
      const ctrl = new AbortController()
      controller.current = ctrl
      setBusy('locating', query)
      let data
      try {
        data = await geocodeLocation(query, { signal: ctrl.signal })
      } catch (err) {
        if (ctrl.signal.aborted) return
        setBusy('idle')
        setFailure({ message: `Couldn't look up ${query}. ${err.message}`, retryable: true })
        return
      }
      if (ctrl.signal.aborted) return
      setBusy('idle')
      if (data.count === 0) {
        patch(i, { error: `No place called "${query}" was found. Check the spelling or add a country.` })
        return focusRow(row.key)
      }
      if (!data.confident) {
        // Several plausible places: never guess, ask for this city.
        patch(i, { matches: { query, results: data.results } })
        setFocusRowKey(row.key)
        return
      }
      patch(i, { resolved: { ...data.results[0], query }, matches: null })
    }

    for (let i = 1; i < current.length; i++) {
      if (sameCity(current[i - 1].resolved, current[i].resolved)) {
        patch(i, { error: `${current[i].resolved.name} is listed twice in a row. Remove one of them.` })
        return focusRow(current[i].key)
      }
    }

    const cities = current.map((r) => cityPayload(r.resolved, Number(r.days)))
    return generateTrip(cities, current.map((r) => r.resolved.name).join(', '))
  }

  function chooseInRow(key, location) {
    const next = rows.map((r) =>
      r.key === key ? { ...r, resolved: { ...location, query: normalize(r.text) }, matches: null, error: null } : r,
    )
    setRows(next)
    setFocusRowKey(null)
    submitMulti(next)
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (busy) return
    setFailure(null)
    if (mode === 'multi') return submitMulti()
    const nextErrors = validate({
      cityText,
      days,
      startDate,
      startDateBad: dateRef.current?.validity.badInput ?? false,
    })
    setErrors(nextErrors)
    if (nextErrors.city) return cityRef.current?.focus()
    if (nextErrors.days) return daysRef.current?.focus()
    if (nextErrors.startDate) return dateRef.current?.focus()

    const query = normalize(cityText)
    if (resolved && resolved.query === query) return generate(resolved, query)

    controller.current?.abort()
    const ctrl = new AbortController()
    controller.current = ctrl
    setBusy('locating', query)
    setMatches(null)
    try {
      const data = await geocodeLocation(query, { signal: ctrl.signal })
      if (ctrl.signal.aborted) return
      setBusy('idle')
      if (data.count === 0) {
        setResolved(null)
        setErrors({ city: `No place called "${query}" was found. Check the spelling or add a country.` })
        cityRef.current?.focus()
      } else if (data.confident) {
        await generate(data.results[0], query)
      } else {
        // Several plausible places: the user must choose. Never guess.
        setResolved(null)
        setMatches({ query, results: data.results })
      }
    } catch (err) {
      if (ctrl.signal.aborted) return
      setBusy('idle')
      setFailure({ message: `Couldn't look up that city. ${err.message}`, retryable: true })
    }
  }

  const submitLabel =
    phase === 'locating'
      ? mode === 'multi'
        ? 'Finding the cities…'
        : 'Finding the city…'
      : phase === 'generating'
        ? 'Building your plan…'
        : 'Generate itinerary'

  return (
    <form className="plan-form" onSubmit={handleSubmit} noValidate aria-labelledby={`${uid}-title`}>
      <div className="plan-form__head">
        <h2 id={`${uid}-title`} className="plan-form__title">
          Plan a trip
        </h2>
        <p className="hint">One city or a route of several. Every stop is a real place from OpenStreetMap.</p>
      </div>

      <fieldset className="segmented segmented--block">
        <legend className="visually-hidden">Trip type</legend>
        {[
          { value: 'single', label: 'One city' },
          { value: 'multi', label: 'Several cities' },
        ].map((opt) => (
          <label key={opt.value} className="segmented__option">
            <input
              type="radio"
              className="sr-input"
              name={`${uid}-mode`}
              value={opt.value}
              checked={mode === opt.value}
              onChange={() => {
                setMode(opt.value)
                setFailure(null)
                setErrors({})
              }}
              disabled={busy}
            />
            <span>{opt.label}</span>
          </label>
        ))}
      </fieldset>

      {mode === 'multi' && (
        <CityRoute
          uid={uid}
          rows={rows}
          busy={busy}
          total={multiTotal}
          totalError={multiTotalError}
          onChange={(next) => {
            setRows(next)
            setFailure(null)
          }}
          onChoose={chooseInRow}
          focusRowKey={focusRowKey}
        />
      )}

      {/* Destination */}
      {mode === 'single' && (
      <div className="field">
        <label htmlFor={`${uid}-city`}>Destination city</label>
        <span className="hint" id={`${uid}-city-hint`}>
          For example Kyoto, Lisbon or Porto, Portugal.
        </span>
        <input
          ref={cityRef}
          id={`${uid}-city`}
          name="city"
          type="text"
          autoComplete="off"
          enterKeyHint="next"
          maxLength={200}
          value={cityText}
          onChange={(e) => updateCity(e.target.value)}
          aria-invalid={errors.city ? 'true' : undefined}
          aria-describedby={`${uid}-city-hint${errors.city ? ` ${uid}-city-error` : ''}`}
          required
        />
        {errors.city && (
          <p className="field-error" id={`${uid}-city-error`} role="alert">
            {errors.city}
          </p>
        )}
        {resolved && !matches && resolved.query === normalize(cityText) && !errors.city && (
          <p className="hint resolved">
            <MapPin aria-hidden="true" size={14} weight="fill" />
            {resolved.address || resolved.name}
          </p>
        )}
        {matches && (
          <div className="matches" ref={matchesRef} tabIndex={-1} role="group" aria-labelledby={`${uid}-matches`}>
            <p id={`${uid}-matches`} className="matches__title">
              {matches.results.length} places match "{matches.query}". Which one?
            </p>
            <ul className="matches__list" role="list">
              {matches.results.map((loc, i) => (
                <li key={loc.id ?? i}>
                  <button type="button" className="match" onClick={() => generate(loc, matches.query)} disabled={busy}>
                    <span className="match__name">{loc.name}</span>
                    {loc.address && loc.address !== loc.name && <span className="match__address">{loc.address}</span>}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      )}

      {/* Duration + start date */}
      <div className={`plan-form__row ${mode === 'multi' ? 'plan-form__row--date-only' : ''}`}>
        {mode === 'single' && (
        <div className="field">
          <label htmlFor={`${uid}-days`}>Days</label>
          <div className="stepper">
            <button
              type="button"
              className="stepper__btn"
              onClick={() => stepDays(-1)}
              disabled={Number(days) <= MIN_DAYS}
              aria-label="One day fewer"
            >
              <Minus aria-hidden="true" size={16} weight="bold" />
            </button>
            <input
              ref={daysRef}
              id={`${uid}-days`}
              name="days"
              type="number"
              inputMode="numeric"
              min={MIN_DAYS}
              max={MAX_DAYS}
              step={1}
              value={days}
              onChange={(e) => {
                setDays(e.target.value)
                clearError('days')
              }}
              aria-invalid={errors.days ? 'true' : undefined}
              aria-describedby={errors.days ? `${uid}-days-error` : undefined}
            />
            <button
              type="button"
              className="stepper__btn"
              onClick={() => stepDays(1)}
              disabled={Number(days) >= MAX_DAYS}
              aria-label="One day more"
            >
              <Plus aria-hidden="true" size={16} weight="bold" />
            </button>
          </div>
          {errors.days && (
            <p className="field-error" id={`${uid}-days-error`}>
              {errors.days}
            </p>
          )}
        </div>
        )}
        <div className="field">
          <label htmlFor={`${uid}-date`}>Start date (optional)</label>
          <input
            ref={dateRef}
            id={`${uid}-date`}
            name="start_date"
            type="date"
            value={startDate}
            onChange={(e) => {
              setStartDate(e.target.value)
              clearError('startDate')
            }}
            aria-invalid={errors.startDate ? 'true' : undefined}
            aria-describedby={errors.startDate ? `${uid}-date-error` : undefined}
          />
          {errors.startDate && (
            <p className="field-error" id={`${uid}-date-error`}>
              {errors.startDate}
            </p>
          )}
        </div>
      </div>

      {/* Pace */}
      <fieldset className="field-group">
        <legend className="field-group__legend">Pace</legend>
        <div className="pace-options">
          {PACES.map((p) => (
            <label key={p.value} className="pace-option">
              <input
                type="radio"
                className="sr-input"
                name={`${uid}-pace`}
                value={p.value}
                checked={pace === p.value}
                onChange={() => setPace(p.value)}
              />
              <span className="pace-option__body">
                <span className="pace-option__label">{p.label}</span>
                <span className="pace-option__detail">{p.detail}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      {/* Interests */}
      <fieldset className="field-group">
        <legend className="field-group__legend">Interests</legend>
        <p className="hint" id={`${uid}-interests-hint`}>
          Pick any. With none, you get general sightseeing.
        </p>
        <div className="chips" aria-describedby={`${uid}-interests-hint`}>
          {INTERESTS.map((i) => (
            <label key={i.value} className="chip">
              <input
                type="checkbox"
                className="sr-input"
                name="interests"
                value={i.value}
                checked={interests.includes(i.value)}
                onChange={() => toggleInterest(i.value)}
              />
              <span>{i.label}</span>
            </label>
          ))}
        </div>
      </fieldset>

      {/* Title */}
      <div className="field">
        <label htmlFor={`${uid}-name`}>Trip name (optional)</label>
        <span className="hint" id={`${uid}-name-hint`}>
          Leave empty for "Trip to {normalize(cityText) || 'your city'}".
        </span>
        <input
          id={`${uid}-name`}
          name="title"
          type="text"
          maxLength={120}
          autoComplete="off"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          aria-describedby={`${uid}-name-hint`}
        />
      </div>

      {failure && (
        <div className="notice notice--error" role="alert">
          <WarningCircle aria-hidden="true" size={22} weight="fill" />
          <div>
            <p className="notice__title">Couldn't create the plan</p>
            <p>{failure.message}</p>
          </div>
          {failure.retryable && (
            <button type="submit" className="btn btn--ghost">
              <ArrowClockwise aria-hidden="true" size={18} />
              Try again
            </button>
          )}
        </div>
      )}

      <button type="submit" className="btn btn--primary btn--block btn--lg" disabled={busy}>
        {submitLabel}
      </button>
    </form>
  )
}
