import { useEffect, useId, useRef, useState } from 'react'
import { ArrowSquareOut, CheckCircle, Plus, Trash, X } from '@phosphor-icons/react'
import { useTrip } from '../state/TripContext.jsx'
import { useAnnounce } from '../state/Announcer.jsx'
import {
  categoryLabels,
  formatCoordinates,
  formatDate,
  osmUrl,
  placeName,
} from '../lib/format.js'
import DestinationImage from './plan/DestinationImage.jsx'

const supportsClosedBy =
  typeof HTMLDialogElement !== 'undefined' && 'closedBy' in HTMLDialogElement.prototype

/**
 * Destination details in a native modal <dialog>: focus containment, Esc and
 * inert background come from the platform. closedby="any" adds light dismiss
 * where supported, with a click-outside fallback elsewhere (Safari).
 */
export default function PlaceDialog({ place, onClose, onGoToTrip }) {
  const dialogRef = useRef(null)
  const titleId = useId()
  const { savedIds, items, pending, add, remove, status: tripStatus } = useTrip()
  const announce = useAnnounce()
  const [feedback, setFeedback] = useState(null) // { tone: 'ok' | 'error', text }

  // Keep the last place rendered while the dialog animates closed.
  const [shown, setShown] = useState(place)
  if (place && place !== shown) {
    setShown(place)
    setFeedback(null)
  }

  useEffect(() => {
    const dialog = dialogRef.current
    if (place && !dialog.open) dialog.showModal()
    if (!place && dialog.open) dialog.close()
  }, [place])

  function handleBackdropClick(event) {
    if (supportsClosedBy) return
    const dialog = dialogRef.current
    if (event.target !== dialog) return
    const r = dialog.getBoundingClientRect()
    const inside =
      r.top <= event.clientY &&
      event.clientY <= r.bottom &&
      r.left <= event.clientX &&
      event.clientX <= r.right
    if (!inside) dialog.close()
  }

  const current = shown
  const saved = current ? savedIds.has(current.id) : false
  const savedItem = saved ? items.find((p) => p.id === current.id) : null
  const busy = current ? pending.has(current.id) : false
  const name = current ? placeName(current) : ''

  async function handleAdd() {
    setFeedback(null)
    const result = await add(current)
    if (result.ok) {
      const text = result.duplicate
        ? `${name} was already in My Trip.`
        : `Added ${name} to My Trip.`
      setFeedback({ tone: 'ok', text })
      announce(text)
    } else {
      setFeedback({ tone: 'error', text: `Couldn't add this place. ${result.error.message}` })
    }
  }

  async function handleRemove() {
    setFeedback(null)
    const result = await remove(current.id)
    if (result.ok) {
      const text = `Removed ${name} from My Trip.`
      setFeedback({ tone: 'ok', text })
      announce(text)
    } else {
      setFeedback({ tone: 'error', text: `Couldn't remove this place. ${result.error.message}` })
    }
  }

  const tags = current ? categoryLabels(current.categories, 6) : []

  return (
    <dialog
      ref={dialogRef}
      className="place-dialog"
      aria-labelledby={titleId}
      closedby="any"
      onClose={onClose}
      onClick={handleBackdropClick}
    >
      {current && (
        <div className="place-dialog__body">
          <div className="place-dialog__top">
            {tags.length > 0 ? (
              <ul className="tags" role="list" aria-label="Categories">
                {tags.map((tag) => (
                  <li key={tag} className="tag">
                    {tag}
                  </li>
                ))}
              </ul>
            ) : (
              <span />
            )}
            <button
              type="button"
              className="icon-btn"
              onClick={() => dialogRef.current.close()}
              aria-label="Close details"
            >
              <X aria-hidden="true" size={20} weight="bold" />
            </button>
          </div>

          <h2 id={titleId} className="place-dialog__title">
            {name}
          </h2>

          <DestinationImage city={name} className="place-dialog__media" credit />

          <dl className="facts">
            <div>
              <dt>Address</dt>
              <dd>{current.address || 'No address listed'}</dd>
            </div>
            <div>
              <dt>Coordinates</dt>
              <dd className="tabular">{formatCoordinates(current.latitude, current.longitude)}</dd>
            </div>
            {savedItem?.added_at && (
              <div>
                <dt>Added to My Trip</dt>
                <dd>{formatDate(savedItem.added_at)}</dd>
              </div>
            )}
          </dl>

          <a
            className="text-link"
            href={osmUrl(current.latitude, current.longitude)}
            target="_blank"
            rel="noopener noreferrer"
          >
            View on OpenStreetMap
            <ArrowSquareOut aria-hidden="true" size={16} />
            <span className="visually-hidden"> (opens in a new tab)</span>
          </a>

          {feedback && (
            <p
              className={`feedback feedback--${feedback.tone}`}
              role={feedback.tone === 'error' ? 'alert' : undefined}
            >
              {feedback.text}
            </p>
          )}

          <div className="place-dialog__actions">
            {saved ? (
              <>
                <p className="saved-badge saved-badge--lg">
                  <CheckCircle aria-hidden="true" size={20} weight="fill" />
                  In My Trip
                </p>
                <div className="place-dialog__buttons">
                  <button
                    type="button"
                    className="btn btn--ghost"
                    onClick={handleRemove}
                    disabled={busy}
                  >
                    <Trash aria-hidden="true" size={18} />
                    {busy ? 'Removing…' : 'Remove'}
                  </button>
                  {onGoToTrip && (
                    <button type="button" className="btn btn--primary" onClick={onGoToTrip}>
                      View My Trip
                    </button>
                  )}
                </div>
              </>
            ) : (
              <button
                type="button"
                className="btn btn--primary btn--block"
                onClick={handleAdd}
                disabled={busy || tripStatus === 'loading'}
              >
                <Plus aria-hidden="true" size={18} weight="bold" />
                {busy ? 'Adding…' : 'Add to My Trip'}
              </button>
            )}
          </div>
        </div>
      )}
    </dialog>
  )
}
