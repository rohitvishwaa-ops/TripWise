import { ArrowClockwise, ArrowRight, CalendarBlank, WarningCircle } from '@phosphor-icons/react'
import DestinationImage from './DestinationImage.jsx'
import { formatTripRange } from '../../lib/format.js'
import { PACES } from '../../lib/planOptions.js'

const paceLabel = (value) => PACES.find((p) => p.value === value)?.label ?? value

export default function TripList({ state, onRetry, headingId }) {
  const { status, trips, error } = state
  return (
    <section className="trip-list-panel" aria-labelledby={headingId} aria-busy={status === 'loading'}>
      <h2 id={headingId} className="section-title">
        Your trips
      </h2>

      {status === 'loading' && (
        <ul className="saved-trips" role="list" aria-hidden="true">
          {[0, 1].map((i) => (
            <li key={i} className="saved-trip saved-trip--skeleton">
              <span className="saved-trip__media sk" />
              <span className="saved-trip__body">
                <span className="sk sk--title" />
                <span className="sk sk--line sk--short" />
              </span>
            </li>
          ))}
        </ul>
      )}

      {status === 'error' && (
        <div className="notice notice--error" role="alert">
          <WarningCircle aria-hidden="true" size={22} weight="fill" />
          <div>
            <p className="notice__title">Couldn't load your trips</p>
            <p>{error.message}</p>
          </div>
          <button type="button" className="btn btn--ghost" onClick={onRetry}>
            <ArrowClockwise aria-hidden="true" size={18} />
            Try again
          </button>
        </div>
      )}

      {status === 'ready' && trips.length === 0 && (
        <p className="saved-trips__empty">
          No trips yet. Plans you generate are saved here, so you can come back to them any time.
        </p>
      )}

      {status === 'ready' && trips.length > 0 && (
        <ul className="saved-trips" role="list">
          {trips.map((trip) => {
            const city = trip.city_names[0] ?? ''
            const places = trip.city_names.join(', ')
            const range = formatTripRange(trip.start_date, trip.end_date)
            return (
              <li key={trip.id}>
                <a className="saved-trip" href={`#plan/${trip.id}`}>
                  <DestinationImage city={city} className="saved-trip__media" alt={`Photo of ${city}`} />
                  <span className="saved-trip__body">
                    <span className="saved-trip__title">{trip.title}</span>
                    <span className="saved-trip__meta">
                      {places}, {trip.num_days} {trip.num_days === 1 ? 'day' : 'days'}, {paceLabel(trip.pace).toLowerCase()} pace
                    </span>
                    {range && (
                      <span className="saved-trip__dates">
                        <CalendarBlank aria-hidden="true" size={14} />
                        {range}
                      </span>
                    )}
                  </span>
                  <ArrowRight className="saved-trip__arrow" aria-hidden="true" size={18} />
                </a>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
