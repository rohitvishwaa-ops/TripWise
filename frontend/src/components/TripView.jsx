import { useEffect, useId, useRef, useState } from 'react'
import { ArrowClockwise, MapPin, Suitcase, Trash, WarningCircle } from '@phosphor-icons/react'
import { useTrip } from '../state/TripContext.jsx'
import { useAnnounce } from '../state/Announcer.jsx'
import { categoryLabels, formatCoordinates, formatDate, placeName } from '../lib/format.js'
import DestinationImage from './plan/DestinationImage.jsx'

export default function TripView({ headingRef, onOpenPlace }) {
  const uid = useId()
  const { items, status, error, pending, remove, reload } = useTrip()
  const announce = useAnnounce()
  const [rowError, setRowError] = useState(null) // { id, message }
  const pendingFocus = useRef(null)
  const titleRefs = useRef(new Map())
  const listRef = useRef(null)

  // After a removal, move focus to a neighbouring item (or the heading) so
  // keyboard users aren't dropped at the top of the document.
  useEffect(() => {
    const focusId = pendingFocus.current
    if (focusId === null) return
    pendingFocus.current = null
    const target = focusId === 'heading' ? headingRef.current : titleRefs.current.get(focusId)
    target?.focus()
  }, [items, headingRef])

  async function handleRemove(place, index) {
    setRowError(null)
    const name = placeName(place)
    // Decide the focus target before the list re-renders without this item.
    const neighbour = items[index + 1] ?? items[index - 1]
    pendingFocus.current = neighbour ? neighbour.id : 'heading'
    const result = await remove(place.id)
    if (result.ok) {
      announce(`Removed ${name} from My Trip.`)
    } else {
      pendingFocus.current = null
      setRowError({ id: place.id, message: `Couldn't remove ${name}. ${result.error.message}` })
    }
  }

  const count = items.length

  return (
    <section className="trip" aria-labelledby={`${uid}-h1`}>
      <header className="trip__head">
        <p className="eyebrow" aria-hidden="true">
          Saved places
        </p>
        <h1 id={`${uid}-h1`} ref={headingRef} tabIndex={-1} className="display">
          My Trip
        </h1>
        {status === 'ready' && (
          <p className="lede">
            {count === 0
              ? 'Nothing saved yet.'
              : `${count} saved ${count === 1 ? 'place' : 'places'}, in the order you added them.`}
          </p>
        )}
      </header>

      {status === 'loading' && (
        <ol className="trip-list" role="list" aria-busy="true">
          {Array.from({ length: 3 }, (_, i) => (
            <li key={i} className="trip-item trip-item--skeleton" aria-hidden="true">
              <span className="trip-item__index sk" />
              <div className="trip-item__main">
                <span className="sk sk--title" />
                <span className="sk sk--line" />
              </div>
            </li>
          ))}
        </ol>
      )}

      {status === 'error' && (
        <div className="notice notice--error" role="alert">
          <WarningCircle aria-hidden="true" size={22} weight="fill" />
          <div>
            <p className="notice__title">Couldn't load your trip</p>
            <p>{error.message}</p>
          </div>
          <button type="button" className="btn btn--ghost" onClick={() => reload()}>
            <ArrowClockwise aria-hidden="true" size={18} />
            Try again
          </button>
        </div>
      )}

      {status === 'ready' && count === 0 && (
        <div className="empty empty--trip">
          <Suitcase aria-hidden="true" size={44} weight="duotone" />
          <h2>Your trip is empty</h2>
          <p>Find places on Explore and choose Add to My Trip to collect them here.</p>
          <a className="btn btn--primary" href="#explore">
            Explore places
          </a>
        </div>
      )}

      {status === 'ready' && count > 0 && (
        <ol className="trip-list" role="list" ref={listRef}>
          {items.map((place, index) => {
            const name = placeName(place)
            const busy = pending.has(place.id)
            const tags = categoryLabels(place.categories, 2)
            return (
              <li key={place.id} className="trip-item">
                <span className="trip-item__index" aria-hidden="true">
                  {String(index + 1).padStart(2, '0')}
                </span>
                <DestinationImage city={name} className="trip-item__media" />
                <div className="trip-item__main">
                  <h2 className="trip-item__title">
                    <button
                      type="button"
                      className="link-btn"
                      ref={(el) => {
                        if (el) titleRefs.current.set(place.id, el)
                        else titleRefs.current.delete(place.id)
                      }}
                      onClick={() => onOpenPlace(place)}
                    >
                      {name}
                    </button>
                  </h2>
                  {place.address && <p className="trip-item__address">{place.address}</p>}
                  <p className="trip-item__meta">
                    {tags.length > 0 && <span>{tags.join(', ')}</span>}
                    <span className="tabular">
                      <MapPin aria-hidden="true" size={14} weight="fill" />
                      {formatCoordinates(place.latitude, place.longitude)}
                    </span>
                    {place.added_at && <span>Added {formatDate(place.added_at)}</span>}
                  </p>
                  {rowError?.id === place.id && (
                    <p className="field-error" role="alert">
                      {rowError.message}
                    </p>
                  )}
                </div>
                <button
                  type="button"
                  className="btn btn--ghost btn--danger"
                  onClick={() => handleRemove(place, index)}
                  disabled={busy}
                  aria-label={`Remove ${name} from My Trip`}
                >
                  <Trash aria-hidden="true" size={18} />
                  <span aria-hidden="true">{busy ? 'Removing…' : 'Remove'}</span>
                </button>
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}
