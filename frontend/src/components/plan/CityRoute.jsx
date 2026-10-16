import { useEffect, useRef } from 'react'
import { ArrowDown, ArrowUp, MapPin, Minus, Plus, Trash } from '@phosphor-icons/react'

export const MAX_CITIES = 10
export const MAX_TRIP_DAYS = 30

/**
 * Ordered list of cities for a multi-city trip, each with its own days.
 * Each row is resolved with /api/geocode by the parent form; when several
 * places match, the row shows the choices and nothing is generated until the
 * user picks one.
 */
export default function CityRoute({ uid, rows, busy, total, totalError, onChange, onChoose, focusRowKey }) {
  const matchRefs = useRef(new Map())

  useEffect(() => {
    if (focusRowKey) matchRefs.current.get(focusRowKey)?.focus()
  }, [focusRowKey, rows])

  function update(key, patch) {
    onChange(rows.map((r) => (r.key === key ? { ...r, ...patch } : r)))
  }

  function move(index, delta) {
    const next = [...rows]
    ;[next[index], next[index + delta]] = [next[index + delta], next[index]]
    onChange(next)
  }

  function stepDays(row, delta) {
    const n = Number.parseInt(row.days, 10)
    const next = Math.min(MAX_TRIP_DAYS, Math.max(1, (Number.isNaN(n) ? 1 : n) + delta))
    update(row.key, { days: String(next), daysError: null })
  }

  return (
    <fieldset className="field-group city-route">
      <legend className="field-group__legend">Cities, in travel order</legend>
      <ol className="city-route__list" role="list">
        {rows.map((row, i) => {
          const label = row.resolved?.name || row.text.trim() || `City ${i + 1}`
          const inputId = `${uid}-city-${row.key}`
          const daysId = `${uid}-days-${row.key}`
          return (
            <li key={row.key} className="city-row">
              <div className="city-row__head">
                <span className="city-row__num" aria-hidden="true">
                  {i + 1}
                </span>
                <label htmlFor={inputId} className="city-row__label">
                  City {i + 1}
                </label>
                <div className="city-row__tools" role="group" aria-label={`Arrange ${label}`}>
                  <button
                    type="button"
                    className="icon-action"
                    onClick={() => move(i, -1)}
                    disabled={busy || i === 0}
                    aria-label={`Move ${label} earlier`}
                    title="Earlier"
                  >
                    <ArrowUp aria-hidden="true" size={16} weight="bold" />
                  </button>
                  <button
                    type="button"
                    className="icon-action"
                    onClick={() => move(i, 1)}
                    disabled={busy || i === rows.length - 1}
                    aria-label={`Move ${label} later`}
                    title="Later"
                  >
                    <ArrowDown aria-hidden="true" size={16} weight="bold" />
                  </button>
                  <button
                    type="button"
                    className="icon-action icon-action--danger"
                    onClick={() => onChange(rows.filter((r) => r.key !== row.key))}
                    disabled={busy || rows.length <= 2}
                    aria-label={`Remove ${label} from the route`}
                    title={rows.length <= 2 ? 'A multi-city trip needs at least 2 cities' : 'Remove'}
                  >
                    <Trash aria-hidden="true" size={16} />
                  </button>
                </div>
              </div>

              <div className="city-row__fields">
                <div className="field">
                  <input
                    id={inputId}
                    name={`city-${i + 1}`}
                    type="text"
                    autoComplete="off"
                    maxLength={200}
                    value={row.text}
                    onChange={(e) =>
                      update(row.key, { text: e.target.value, resolved: null, matches: null, error: null })
                    }
                    aria-invalid={row.error ? 'true' : undefined}
                    aria-describedby={row.error ? `${inputId}-error` : undefined}
                  />
                </div>
                <div className="field city-row__days">
                  <label htmlFor={daysId} className="visually-hidden">
                    Days in {label}
                  </label>
                  <div className="stepper stepper--compact">
                    <button
                      type="button"
                      className="stepper__btn"
                      onClick={() => stepDays(row, -1)}
                      disabled={busy || Number(row.days) <= 1}
                      aria-label={`One day fewer in ${label}`}
                    >
                      <Minus aria-hidden="true" size={14} weight="bold" />
                    </button>
                    <input
                      id={daysId}
                      name={`days-${i + 1}`}
                      type="number"
                      inputMode="numeric"
                      min={1}
                      max={MAX_TRIP_DAYS}
                      value={row.days}
                      onChange={(e) => update(row.key, { days: e.target.value, daysError: null })}
                      aria-invalid={row.daysError ? 'true' : undefined}
                      aria-describedby={`${daysId}-unit${row.daysError ? ` ${daysId}-error` : ''}`}
                    />
                    <button
                      type="button"
                      className="stepper__btn"
                      onClick={() => stepDays(row, 1)}
                      disabled={busy || Number(row.days) >= MAX_TRIP_DAYS}
                      aria-label={`One day more in ${label}`}
                    >
                      <Plus aria-hidden="true" size={14} weight="bold" />
                    </button>
                  </div>
                  <span className="hint city-row__unit" id={`${daysId}-unit`}>
                    {Number(row.days) === 1 ? 'day' : 'days'}
                  </span>
                </div>
              </div>

              {row.error && (
                <p className="field-error" id={`${inputId}-error`} role="alert">
                  {row.error}
                </p>
              )}
              {row.daysError && (
                <p className="field-error" id={`${daysId}-error`}>
                  {row.daysError}
                </p>
              )}
              {row.resolved && !row.matches && !row.error && (
                <p className="hint resolved">
                  <MapPin aria-hidden="true" size={14} weight="fill" />
                  {row.resolved.address || row.resolved.name}
                </p>
              )}
              {row.matches && (
                <div
                  className="matches"
                  ref={(el) => {
                    if (el) matchRefs.current.set(row.key, el)
                    else matchRefs.current.delete(row.key)
                  }}
                  tabIndex={-1}
                  role="group"
                  aria-labelledby={`${inputId}-matches`}
                >
                  <p id={`${inputId}-matches`} className="matches__title">
                    {row.matches.results.length} places match "{row.matches.query}". Which one?
                  </p>
                  <ul className="matches__list" role="list">
                    {row.matches.results.map((loc, j) => (
                      <li key={loc.id ?? j}>
                        <button
                          type="button"
                          className="match"
                          onClick={() => onChoose(row.key, loc)}
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
            </li>
          )
        })}
      </ol>

      <div className="city-route__footer">
        <button
          type="button"
          className="text-action"
          onClick={() =>
            onChange([...rows, { key: `${Date.now()}-${rows.length}`, text: '', days: '1', resolved: null, matches: null, error: null }])
          }
          disabled={busy || rows.length >= MAX_CITIES}
        >
          <Plus aria-hidden="true" size={16} weight="bold" />
          Add city
        </button>
        <p className={`city-route__total ${totalError ? 'field-error' : ''}`} role="status">
          {total} {total === 1 ? 'day' : 'days'} across {rows.length} cities
          {totalError ? `. ${totalError}` : ''}
        </p>
      </div>
    </fieldset>
  )
}
