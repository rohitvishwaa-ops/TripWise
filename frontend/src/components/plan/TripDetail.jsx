import { useEffect, useRef, useState } from 'react'
import {
  ArrowClockwise,
  ArrowLeft,
  CalendarBlank,
  CheckCircle,
  Info,
  MapPin,
  WarningCircle,
  X,
} from '@phosphor-icons/react'
import DestinationImage from './DestinationImage.jsx'
import DataCredit from '../DataCredit.jsx'
import DayCard from './DayCard.jsx'
import AddSavedPlace from './AddSavedPlace.jsx'
import { INTERESTS, PACES } from '../../lib/planOptions.js'
import { formatTripRange } from '../../lib/format.js'
import {
  addTripActivity,
  deleteActivity,
  regenerateDay,
  reorderDay,
  updateActivity,
} from '../../lib/api.js'
import { useTrip } from '../../state/TripContext.jsx'
import { useAnnounce } from '../../state/Announcer.jsx'

const paceLabel = (v) => PACES.find((p) => p.value === v)?.label ?? v
const interestLabel = (v) => INTERESTS.find((i) => i.value === v)?.label ?? v

export function TripDetailSkeleton({ label }) {
  return (
    <div className="trip-detail" aria-busy="true">
      <div className="trip-hero trip-hero--skeleton">
        <div className="trip-hero__content">
          <p className="trip-hero__status" role="status">
            {label}
          </p>
        </div>
      </div>
      <ol className="day-list" role="list" aria-hidden="true">
        {[0, 1].map((d) => (
          <li key={d} className="day-card">
            <div className="day-card__head">
              <span className="sk sk--title" />
            </div>
            {[0, 1, 2].map((s) => (
              <div key={s} className="stop stop--skeleton">
                <span className="sk sk--tag" />
                <span className="sk sk--line" />
              </div>
            ))}
          </li>
        ))}
      </ol>
    </div>
  )
}

export function TripDetailError({ error, onRetry }) {
  // 404: unknown or another browser's trip; 422: malformed trip link.
  const missing = error.status === 404 || error.status === 422
  return (
    <div className="trip-detail">
      <a className="back-link" href="#plan">
        <ArrowLeft aria-hidden="true" size={16} weight="bold" />
        All trips
      </a>
      <div className="notice notice--error" role="alert">
        <WarningCircle aria-hidden="true" size={22} weight="fill" />
        <div>
          <p className="notice__title">{missing ? 'Trip not found' : "Couldn't open this trip"}</p>
          <p>
            {missing
              ? 'It may have been deleted, or it was created in a different browser.'
              : error.message}
          </p>
        </div>
        {!missing && (
          <button type="button" className="btn btn--ghost" onClick={onRetry}>
            <ArrowClockwise aria-hidden="true" size={18} />
            Try again
          </button>
        )}
      </div>
    </div>
  )
}

// Editing actions. Each one calls the API, then replaces the whole trip with
// the server's answer (the database is the source of truth). Returns true on
// success so inline panels can close.
function describe(action) {
  const name = action.activity?.name ?? action.place?.name ?? ''
  switch (action.type) {
    case 'up':
      return `Moved ${name} up.`
    case 'down':
      return `Moved ${name} down.`
    case 'note':
      return action.note.trim() ? `Saved your note on ${name}.` : `Removed your note on ${name}.`
    case 'remove':
      return `Removed ${name} from Day ${action.day.day_index + 1}.`
    default:
      return ''
  }
}

export default function TripDetail({ trip, warnings, headingRef, onTripChange }) {
  const { tripId } = useTrip()
  const announce = useAnnounce()
  const [pending, setPending] = useState(null) // the action being saved
  const [feedback, setFeedback] = useState(null) // { tone: 'ok'|'warn'|'error', text }
  const pendingFocus = useRef(null) // selector to focus after the next update
  const city = trip.cities[0]
  const cityName = city?.name ?? trip.city_names[0] ?? ''
  const multiCity = trip.cities.length > 1
  const cityById = Object.fromEntries(trip.cities.map((c) => [c.id, c]))
  const range = formatTripRange(trip.start_date, trip.end_date)
  const totalStops = trip.days.reduce((n, d) => n + d.activities.filter((a) => a.kind === 'place').length, 0)

  useEffect(() => {
    document.title = `${trip.title} | TripWise`
  }, [trip.title])

  // Success/warning messages clear themselves; errors stay until dismissed.
  useEffect(() => {
    if (!feedback || feedback.tone === 'error') return undefined
    const timer = setTimeout(() => setFeedback(null), feedback.tone === 'warn' ? 10000 : 5000)
    return () => clearTimeout(timer)
  }, [feedback])

  // Keep keyboard focus on the thing the user just acted on.
  useEffect(() => {
    if (!pendingFocus.current) return
    const target = document.querySelector(pendingFocus.current)
    pendingFocus.current = null
    target?.focus()
  }, [trip])

  async function onAction(action) {
    if (pending) return false
    setPending(action)
    setFeedback(null)
    const { activity, day } = action
    try {
      let updated
      let message = describe(action)
      if (action.type === 'up' || action.type === 'down') {
        const ids = day.activities.map((a) => a.id)
        const i = ids.indexOf(activity.id)
        const j = action.type === 'up' ? i - 1 : i + 1
        ;[ids[i], ids[j]] = [ids[j], ids[i]]
        updated = await reorderDay(tripId, trip.id, day.id, ids)
        // Stay on the same button; at the edge, switch to the other direction.
        const edge = (action.type === 'up' && j === 0) || (action.type === 'down' && j === ids.length - 1)
        const btn = edge ? (action.type === 'up' ? 'down' : 'up') : action.type
        pendingFocus.current = `[data-activity-id="${activity.id}"] [data-action="${btn}"]`
      } else if (action.type === 'note') {
        updated = await updateActivity(tripId, trip.id, activity.id, { note: action.note })
        pendingFocus.current = `[data-activity-id="${activity.id}"] [data-action="note"]`
      } else if (action.type === 'move') {
        updated = await updateActivity(tripId, trip.id, activity.id, { day_id: action.targetDayId })
        const target = updated.days.find((d) => d.id === action.targetDayId)
        message = `Moved ${activity.name} to Day ${target.day_index + 1}.`
        pendingFocus.current = `[data-activity-id="${activity.id}"] [data-action="move"]`
      } else if (action.type === 'remove') {
        const idx = day.activities.findIndex((a) => a.id === activity.id)
        const neighbour = day.activities[idx + 1] ?? day.activities[idx - 1]
        updated = await deleteActivity(tripId, trip.id, activity.id)
        pendingFocus.current = neighbour
          ? `[data-activity-id="${neighbour.id}"] [data-action="remove"]`
          : `[data-day-id="${day.id}"] .day-card__theme`
      } else if (action.type === 'add') {
        updated = await addTripActivity(tripId, trip.id, { place: action.place, dayId: action.dayId })
        const added = updated.days
          .flatMap((d) => d.activities.map((a) => ({ a, d })))
          .find(({ a }) => a.place_id === action.place.id)
        message = `Added ${action.place.name ?? 'the place'} to Day ${added.d.day_index + 1}.`
        pendingFocus.current = `[data-activity-id="${added.a.id}"] [data-action="note"]`
      } else if (action.type === 'regenerate') {
        updated = await regenerateDay(tripId, trip.id, day.id)
        message = `Day ${day.day_index + 1} has new suggestions.`
        pendingFocus.current = `[data-day-id="${day.id}"] .day-card__theme`
      }
      const warn = updated.warnings?.length ? updated.warnings.join(' ') : null
      onTripChange(updated)
      setFeedback(warn ? { tone: 'warn', text: `${message} ${warn}` } : { tone: 'ok', text: message })
      announce(warn ? `${message} ${warn}` : message)
      return true
    } catch (err) {
      setFeedback({ tone: 'error', text: `That change wasn't saved. ${err.message}` })
      return false
    } finally {
      setPending(null)
    }
  }

  const busy = pending !== null

  return (
    <article className="trip-detail" aria-labelledby={`trip-${trip.id}`}>
      <a className="back-link" href="#plan">
        <ArrowLeft aria-hidden="true" size={16} weight="bold" />
        All trips
      </a>

      <header className="trip-hero">
        <DestinationImage
          city={cityName}
          size="large"
          className="trip-hero__media"
          priority
          credit
          alt={`Photo of ${cityName}`}
        />
        <div className="trip-hero__content">
          {multiCity ? (
            <p className="trip-hero__city trip-hero__route">
              <MapPin aria-hidden="true" size={16} weight="fill" />
              {/* aria-label is not allowed on <p>; give screen readers real text instead. */}
              <span className="visually-hidden">Route: {trip.cities.map((c) => c.name).join(', then ')}</span>
              {trip.cities.map((c, i) => (
                <span key={c.id} aria-hidden="true">
                  {i > 0 && <span className="trip-hero__arrow">→</span>}
                  {c.name}
                </span>
              ))}
            </p>
          ) : (
            <p className="trip-hero__city">
              <MapPin aria-hidden="true" size={16} weight="fill" />
              {city?.address || cityName}
            </p>
          )}
          <h1 id={`trip-${trip.id}`} ref={headingRef} tabIndex={-1} className="trip-hero__title">
            {trip.title}
          </h1>
          <ul className="trip-hero__facts" role="list">
            <li>
              <CalendarBlank aria-hidden="true" size={16} />
              {range || `${trip.num_days} ${trip.num_days === 1 ? 'day' : 'days'}`}
            </li>
            {range && <li>{`${trip.num_days} ${trip.num_days === 1 ? 'day' : 'days'}`}</li>}
            {multiCity && <li>{trip.cities.length} cities</li>}
            <li>{paceLabel(trip.pace)} pace</li>
            <li>
              {totalStops} {totalStops === 1 ? 'stop' : 'stops'}
            </li>
          </ul>
          {trip.interests.length > 0 && (
            <ul className="trip-hero__interests" role="list" aria-label="Interests">
              {trip.interests.map((i) => (
                <li key={i}>{interestLabel(i)}</li>
              ))}
            </ul>
          )}
        </div>
      </header>

      {warnings?.length > 0 && (
        <div className="notice notice--warn" role="status">
          <WarningCircle aria-hidden="true" size={22} weight="fill" />
          <div>
            <p className="notice__title">Fewer stops than requested</p>
            {warnings.map((w) => (
              <p key={w}>{w}</p>
            ))}
          </div>
        </div>
      )}

      <AddSavedPlace trip={trip} busy={busy} onAction={onAction} />

      {/* Result of the last edit, as a toast at the bottom of the screen.
          Success is announced politely (Announcer); errors use role="alert". */}
      <div className="edit-status">
        {busy && (
          <p className="edit-status__msg edit-status__msg--saving">
            {pending.type === 'regenerate' ? 'Finding new places…' : 'Saving…'}
          </p>
        )}
        {!busy && feedback && (
          <div
            className={`edit-status__msg edit-status__msg--${feedback.tone}`}
            role={feedback.tone === 'error' ? 'alert' : undefined}
          >
            {feedback.tone === 'error' ? (
              <WarningCircle aria-hidden="true" size={18} weight="fill" />
            ) : (
              <CheckCircle aria-hidden="true" size={18} weight="fill" />
            )}
            <span>{feedback.text}</span>
            <button
              type="button"
              className="edit-status__close"
              onClick={() => setFeedback(null)}
              aria-label="Dismiss message"
            >
              <X aria-hidden="true" size={16} weight="bold" />
            </button>
          </div>
        )}
      </div>

      <ol className="day-list" role="list">
        {trip.days.map((day) => (
          <DayCard
            key={day.id}
            day={day}
            days={trip.days}
            cityName={cityById[day.city_id]?.name ?? cityName}
            showCity={multiCity}
            busy={busy}
            regenerating={pending?.type === 'regenerate' && pending.day.id === day.id}
            onAction={onAction}
          />
        ))}
      </ol>

      <p className="plan-disclaimer">
        <Info aria-hidden="true" size={16} />
        Morning, Afternoon and Evening suggest an order, not a schedule. Opening hours, prices and travel
        times are not checked, so confirm them before you go.
      </p>
      <DataCredit className="data-credit--inline" />
    </article>
  )
}
