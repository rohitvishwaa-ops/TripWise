import { useEffect, useId, useRef, useState } from 'react'
import {
  ArrowDown,
  ArrowSquareOut,
  ArrowUp,
  ArrowsLeftRight,
  MoonStars,
  NotePencil,
  Path,
  Sun,
  SunHorizon,
  Trash,
} from '@phosphor-icons/react'
import { categoryLabels, formatKm, osmUrl, straightLineKm } from '../../lib/format.js'

const SLOT = {
  morning: { label: 'Morning', Icon: Sun },
  afternoon: { label: 'Afternoon', Icon: SunHorizon },
  evening: { label: 'Evening', Icon: MoonStars },
}

const NOTE_MAX = 500

/**
 * One stop with its editing controls. Only one inline panel (note, move,
 * remove) is open at a time. All actions are disabled while any edit for
 * this trip is being saved, so changes never race each other.
 */
export default function StopItem({ activity, next, index, count, day, days, busy, onAction }) {
  const uid = useId()
  const [panel, setPanel] = useState(null) // 'note' | 'move' | 'remove'
  const [note, setNote] = useState(activity.note ?? '')
  const [target, setTarget] = useState('')
  const panelRef = useRef(null)
  const name = activity.name
  const isTravel = activity.kind === 'transfer'
  const slot = SLOT[activity.slot]
  const tags = categoryLabels(activity.categories, 2)
  const hasCoords = activity.latitude != null && activity.longitude != null
  const gap =
    hasCoords && next?.latitude != null
      ? straightLineKm(activity.latitude, activity.longitude, next.latitude, next.longitude)
      : null
  const otherDays = days.filter((d) => d.id !== day.id)

  useEffect(() => {
    if (panel) panelRef.current?.querySelector('textarea, select, button')?.focus()
  }, [panel])

  function toggle(which) {
    setPanel((p) => (p === which ? null : which))
    if (which === 'note') setNote(activity.note ?? '')
    if (which === 'move') setTarget(otherDays[0] ? String(otherDays[0].id) : '')
  }

  async function run(action) {
    const ok = await onAction(action)
    if (ok) setPanel(null)
  }

  return (
    <li className={`stop ${isTravel ? 'stop--travel' : ''}`} data-activity-id={activity.id}>
      <div className="stop__rail" aria-hidden="true">
        <span className="stop__dot" />
      </div>
      <div className="stop__body">
        <div className="stop__top">
          {isTravel && (
            <span className="slot slot--travel">
              <Path aria-hidden="true" size={14} weight="bold" />
              Travel
            </span>
          )}
          {slot && (
            <span className={`slot slot--${activity.slot}`}>
              <slot.Icon aria-hidden="true" size={14} weight="bold" />
              {slot.label}
            </span>
          )}
          {activity.source === 'user' && <span className="stop__badge">Added by you</span>}
        </div>
        <h4 className="stop__name">{name}</h4>
        {isTravel ? (
          <p className="stop__address">
            Arrange your own transport to {activity.address || 'the next city'}. TripWise does not suggest
            how to travel, when, or what it costs.
          </p>
        ) : (
          activity.address && <p className="stop__address">{activity.address}</p>
        )}
        {activity.note && (
          <p className="stop__note">
            <NotePencil aria-hidden="true" size={15} />
            <span>
              <span className="visually-hidden">Your note: </span>
              {activity.note}
            </span>
          </p>
        )}
        <div className="stop__meta">
          {tags.length > 0 && (
            <ul className="tags" role="list" aria-label="Categories">
              {tags.map((t) => (
                <li key={t} className="tag">
                  {t}
                </li>
              ))}
            </ul>
          )}
          {hasCoords && (
            <a
              className="text-link stop__map"
              href={osmUrl(activity.latitude, activity.longitude)}
              target="_blank"
              rel="noopener noreferrer"
            >
              Map
              <ArrowSquareOut aria-hidden="true" size={14} />
              <span className="visually-hidden"> of {name} (opens in a new tab)</span>
            </a>
          )}
        </div>

        <div className="stop__actions" role="group" aria-label={`Edit ${name}`}>
          <button
            type="button"
            className="icon-action"
            data-action="up"
            onClick={() => run({ type: 'up', activity, day })}
            disabled={busy || index === 0}
            aria-label={`Move ${name} up`}
            title="Move up"
          >
            <ArrowUp aria-hidden="true" size={16} weight="bold" />
          </button>
          <button
            type="button"
            className="icon-action"
            data-action="down"
            onClick={() => run({ type: 'down', activity, day })}
            disabled={busy || index === count - 1}
            aria-label={`Move ${name} down`}
            title="Move down"
          >
            <ArrowDown aria-hidden="true" size={16} weight="bold" />
          </button>
          <button
            type="button"
            className="text-action"
            data-action="note"
            onClick={() => toggle('note')}
            disabled={busy}
            aria-expanded={panel === 'note'}
            aria-controls={`${uid}-panel`}
          >
            <NotePencil aria-hidden="true" size={16} />
            {activity.note ? 'Edit note' : 'Add note'}
            <span className="visually-hidden"> for {name}</span>
          </button>
          {otherDays.length > 0 && !isTravel && (
            <button
              type="button"
              className="text-action"
              data-action="move"
              onClick={() => toggle('move')}
              disabled={busy}
              aria-expanded={panel === 'move'}
              aria-controls={`${uid}-panel`}
            >
              <ArrowsLeftRight aria-hidden="true" size={16} />
              Move to day
              <span className="visually-hidden">: {name}</span>
            </button>
          )}
          <button
            type="button"
            className="text-action text-action--danger"
            data-action="remove"
            onClick={() => toggle('remove')}
            disabled={busy}
            aria-expanded={panel === 'remove'}
            aria-controls={`${uid}-panel`}
          >
            <Trash aria-hidden="true" size={16} />
            Remove
            <span className="visually-hidden"> {name}</span>
          </button>
        </div>

        <div id={`${uid}-panel`} ref={panelRef} hidden={!panel}>
          {panel === 'note' && (
            <form
              className="stop-panel"
              onSubmit={(e) => {
                e.preventDefault()
                run({ type: 'note', activity, day, note })
              }}
            >
              <label htmlFor={`${uid}-note`}>Your note</label>
              <textarea
                id={`${uid}-note`}
                rows={2}
                maxLength={NOTE_MAX}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                aria-describedby={`${uid}-note-count`}
              />
              <p className="hint" id={`${uid}-note-count`}>
                {note.length}/{NOTE_MAX}. Leave empty to remove the note.
              </p>
              <div className="stop-panel__buttons">
                <button type="submit" className="btn btn--primary btn--sm" disabled={busy}>
                  Save note
                </button>
                <button type="button" className="btn btn--ghost btn--sm" onClick={() => setPanel(null)}>
                  Cancel
                </button>
              </div>
            </form>
          )}

          {panel === 'move' && (
            <form
              className="stop-panel"
              onSubmit={(e) => {
                e.preventDefault()
                run({ type: 'move', activity, day, targetDayId: Number(target) })
              }}
            >
              <label htmlFor={`${uid}-target`}>Move {name} to</label>
              <select
                id={`${uid}-target`}
                className="select"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
              >
                {otherDays.map((d) => (
                  <option key={d.id} value={d.id}>
                    Day {d.day_index + 1}
                    {d.theme ? `: ${d.theme}` : ''}
                  </option>
                ))}
              </select>
              <div className="stop-panel__buttons">
                <button type="submit" className="btn btn--primary btn--sm" disabled={busy || !target}>
                  Move
                </button>
                <button type="button" className="btn btn--ghost btn--sm" onClick={() => setPanel(null)}>
                  Cancel
                </button>
              </div>
            </form>
          )}

          {panel === 'remove' && (
            <div className="stop-panel stop-panel--danger" role="group" aria-labelledby={`${uid}-confirm`}>
              <p id={`${uid}-confirm`}>
                Remove <strong>{name}</strong> from Day {day.day_index + 1}?
                {activity.note ? ' Your note on it will be deleted too.' : ''}
              </p>
              <div className="stop-panel__buttons">
                <button
                  type="button"
                  className="btn btn--danger-solid btn--sm"
                  onClick={() => run({ type: 'remove', activity, day })}
                  disabled={busy}
                >
                  Remove stop
                </button>
                <button type="button" className="btn btn--ghost btn--sm" onClick={() => setPanel(null)}>
                  Keep it
                </button>
              </div>
            </div>
          )}
        </div>

        {gap !== null && <p className="stop__gap">Next stop {formatKm(gap)} away in a straight line</p>}
      </div>
    </li>
  )
}
