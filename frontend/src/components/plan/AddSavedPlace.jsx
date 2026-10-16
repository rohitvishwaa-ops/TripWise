import { useId, useState } from 'react'
import { Plus, Suitcase } from '@phosphor-icons/react'
import { useTrip } from '../../state/TripContext.jsx'
import { placeName } from '../../lib/format.js'

/**
 * Add a place saved in My Trip to this itinerary: to a chosen day, or by
 * default to the day whose stops are closest (decided by the backend).
 */
export default function AddSavedPlace({ trip, busy, onAction }) {
  const uid = useId()
  const { items, status } = useTrip()
  const [open, setOpen] = useState(false)
  const [dayId, setDayId] = useState('')
  const inTrip = new Set(trip.days.flatMap((d) => d.activities.map((a) => a.place_id)).filter(Boolean))
  const available = items.filter((p) => !inTrip.has(p.id))

  return (
    <section className="add-saved" aria-labelledby={`${uid}-title`}>
      <div className="add-saved__head">
        <h2 id={`${uid}-title`} className="add-saved__title">
          <Suitcase aria-hidden="true" size={20} />
          Add from My Trip
        </h2>
        <button
          type="button"
          className="text-action"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-controls={`${uid}-panel`}
        >
          {open ? 'Hide saved places' : `Show saved places${status === 'ready' ? ` (${available.length})` : ''}`}
        </button>
      </div>

      <div id={`${uid}-panel`} hidden={!open}>
        {open && status === 'loading' && <p className="hint">Loading your saved places…</p>}
        {open && status === 'error' && (
          <p className="field-error">Your saved places couldn't be loaded. Open My Trip to try again.</p>
        )}
        {open && status === 'ready' && available.length === 0 && (
          <p className="add-saved__empty">
            {items.length === 0
              ? 'My Trip is empty. Save places from Explore, then add them here.'
              : 'Every place in My Trip is already in this itinerary.'}{' '}
            <a href="#explore">Go to Explore</a>
          </p>
        )}
        {open && status === 'ready' && available.length > 0 && (
          <>
            <div className="field field--inline add-saved__day">
              <label htmlFor={`${uid}-day`}>Add to</label>
              <select id={`${uid}-day`} className="select" value={dayId} onChange={(e) => setDayId(e.target.value)}>
                <option value="">Closest day (by location)</option>
                {trip.days.map((d) => (
                  <option key={d.id} value={d.id}>
                    Day {d.day_index + 1}
                    {d.theme ? `: ${d.theme}` : ''}
                  </option>
                ))}
              </select>
            </div>
            <ul className="add-saved__list" role="list">
              {available.map((p) => (
                <li key={p.id} className="add-saved__item">
                  <span className="add-saved__text">
                    <span className="add-saved__name">{placeName(p)}</span>
                    {p.address && <span className="add-saved__address">{p.address}</span>}
                  </span>
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm"
                    onClick={() => onAction({ type: 'add', place: p, dayId: dayId ? Number(dayId) : null })}
                    disabled={busy}
                  >
                    <Plus aria-hidden="true" size={16} weight="bold" />
                    Add
                    <span className="visually-hidden"> {placeName(p)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </section>
  )
}
