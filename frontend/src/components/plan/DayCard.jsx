import { useEffect, useId, useRef, useState } from 'react'
import { ArrowsClockwise } from '@phosphor-icons/react'
import StopItem from './StopItem.jsx'
import { formatTripDay } from '../../lib/format.js'

export default function DayCard({ day, days, cityName, showCity, busy, regenerating, onAction }) {
  const uid = useId()
  const [confirming, setConfirming] = useState(false)
  const confirmRef = useRef(null)
  const date = formatTripDay(day.date)
  const count = day.activities.filter((a) => a.kind === 'place').length
  const notes = day.activities.filter((a) => a.note && a.kind === 'place').length

  useEffect(() => {
    if (confirming) confirmRef.current?.querySelector('button')?.focus()
  }, [confirming])

  async function regenerate() {
    const ok = await onAction({ type: 'regenerate', day })
    if (ok) setConfirming(false)
  }

  return (
    <li className="day-card" data-day-id={day.id} aria-busy={regenerating || undefined}>
      <header className="day-card__head">
        <div className="day-card__label">
          <span className="day-card__number">Day {day.day_index + 1}</span>
          {date && <span className="day-card__date">{date}</span>}
          {showCity && <span className="day-card__city">{cityName}</span>}
        </div>
        <h3 className="day-card__theme" tabIndex={-1}>
          {day.theme || cityName}
        </h3>
        <div className="day-card__side">
          <p className="day-card__count">
            {count} {count === 1 ? 'stop' : 'stops'}
          </p>
          <button
            type="button"
            className="text-action"
            data-action="regenerate"
            onClick={() => setConfirming((c) => !c)}
            disabled={busy}
            aria-expanded={confirming}
            aria-controls={`${uid}-regen`}
          >
            <ArrowsClockwise aria-hidden="true" size={16} weight="bold" />
            {regenerating ? 'Regenerating…' : 'Regenerate day'}
            <span className="visually-hidden"> {day.day_index + 1}</span>
          </button>
        </div>
      </header>

      <div id={`${uid}-regen`} ref={confirmRef} hidden={!confirming}>
        {confirming && (
          <div className="stop-panel stop-panel--wide" role="group" aria-labelledby={`${uid}-regen-text`}>
            <p id={`${uid}-regen-text`}>
              Replace {count === 0 ? 'this empty day' : `the ${count} ${count === 1 ? 'stop' : 'stops'} on Day ${day.day_index + 1}`} with
              new suggestions near {cityName}? Places planned on other days are never reused, and other days
              stay exactly as they are. Travel steps are kept.
              {notes > 0 ? ` ${notes === 1 ? 'The note' : `The ${notes} notes`} on this day will be lost.` : ''}
            </p>
            <div className="stop-panel__buttons">
              <button type="button" className="btn btn--primary btn--sm" onClick={regenerate} disabled={busy}>
                {regenerating ? 'Regenerating…' : 'Regenerate'}
              </button>
              <button type="button" className="btn btn--ghost btn--sm" onClick={() => setConfirming(false)} disabled={regenerating}>
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      {regenerating ? (
        <div className="day-card__loading" role="status">
          Finding new places for Day {day.day_index + 1}…
        </div>
      ) : day.activities.length === 0 ? (
        <p className="day-card__empty">No stops planned for this day. Regenerate it, move a stop here, or add a saved place.</p>
      ) : (
        <ol className="stops" role="list">
          {day.activities.map((a, i) => (
            <StopItem
              key={a.id}
              activity={a}
              next={day.activities[i + 1]}
              index={i}
              count={day.activities.length}
              day={day}
              days={days}
              busy={busy}
              onAction={onAction}
            />
          ))}
        </ol>
      )}
    </li>
  )
}
