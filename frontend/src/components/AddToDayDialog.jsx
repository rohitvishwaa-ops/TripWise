import { useEffect, useRef, useState } from 'react'
import { CheckCircle, Plus, WarningCircle, X } from '@phosphor-icons/react'
import { addTripActivity, getTrip, listTrips } from '../lib/api.js'
import { useTrip } from '../state/TripContext.jsx'

export default function AddToDayDialog({ place, onClose }) {
  const { tripId } = useTrip()
  const dialogRef = useRef(null)
  const [state, setState] = useState({ status: 'loading', trips: [], error: null })
  const [trip, setTrip] = useState(null)
  const [selectedTrip, setSelectedTrip] = useState('')
  const [selectedDay, setSelectedDay] = useState('')
  const [saving, setSaving] = useState(false)
  const [feedback, setFeedback] = useState(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (place && dialog && !dialog.open) dialog.showModal()
    return () => {
      if (dialog?.open) dialog.close()
    }
  }, [place])

  useEffect(() => {
    if (!place) return undefined
    const ctrl = new AbortController()
    listTrips(tripId, { signal: ctrl.signal })
      .then((data) => setState({ status: 'ready', trips: data.trips, error: null }))
      .catch((error) => {
        if (!ctrl.signal.aborted) setState({ status: 'error', trips: [], error })
      })
    return () => ctrl.abort()
  }, [place, tripId])

  useEffect(() => {
    if (!place || !selectedTrip) return undefined
    const ctrl = new AbortController()
    getTrip(tripId, selectedTrip, { signal: ctrl.signal }).then(setTrip).catch(() => setTrip(null))
    return () => ctrl.abort()
  }, [place, selectedTrip, tripId])

  if (!place) return null

  async function save() {
    if (!trip || !selectedDay) return
    setSaving(true)
    setFeedback(null)
    try {
      await addTripActivity(tripId, trip.id, { place, dayId: selectedDay })
      setFeedback({ ok: true, text: `Added ${place.name} to your itinerary.` })
    } catch (error) {
      setFeedback({ ok: false, text: error.message })
    } finally {
      setSaving(false)
    }
  }

  return (
    <dialog ref={dialogRef} className="place-dialog add-day-dialog" aria-labelledby="add-day-title" onClose={onClose}>
      <div className="place-dialog__body">
        <div className="place-dialog__top">
          <p className="eyebrow">Add to itinerary</p>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close add to day dialog"><X aria-hidden="true" size={20} weight="bold" /></button>
        </div>
        <h2 id="add-day-title" className="place-dialog__title">{place.name}</h2>
        {state.status === 'loading' && <p className="hint">Loading your saved itineraries…</p>}
        {state.status === 'error' && <div className="notice notice--error" role="alert"><WarningCircle aria-hidden="true" size={20} /><p>{state.error.message}</p></div>}
        {state.status === 'ready' && state.trips.length === 0 && <p className="hint">Create an itinerary first, then add places to a specific day.</p>}
        {state.status === 'ready' && state.trips.length > 0 && (
          <div className="add-day-fields">
            <label className="field">Trip
              <select className="select" value={selectedTrip} onChange={(event) => { setSelectedTrip(event.target.value); setSelectedDay('') }}>
                <option value="">Choose a trip</option>
                {state.trips.map((item) => <option key={item.id} value={item.id}>{item.title} · {item.city_names.join(' → ')}</option>)}
              </select>
            </label>
            {trip && <label className="field">Day
              <select className="select" value={selectedDay} onChange={(event) => setSelectedDay(event.target.value)}>
                <option value="">Choose a day</option>
                {trip.days.map((day) => <option key={day.id} value={day.id}>Day {day.day_index + 1} · {day.theme || 'Open day'}</option>)}
              </select>
            </label>}
          </div>
        )}
        {feedback && <p className={`feedback feedback--${feedback.ok ? 'ok' : 'error'}`} role={feedback.ok ? 'status' : 'alert'}>{feedback.ok && <CheckCircle aria-hidden="true" size={18} />} {feedback.text}</p>}
        <div className="place-dialog__actions">
          {feedback?.ok ? <button type="button" className="btn btn--primary" onClick={onClose}>Done</button> : <button type="button" className="btn btn--primary btn--block" disabled={saving || !selectedDay} onClick={save}><Plus aria-hidden="true" size={18} /> {saving ? 'Adding…' : 'Add to this day'}</button>}
        </div>
      </div>
    </dialog>
  )
}
