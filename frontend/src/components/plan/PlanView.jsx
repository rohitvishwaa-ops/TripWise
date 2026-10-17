import { useCallback, useEffect, useId, useState } from 'react'
import PlanForm from './PlanForm.jsx'
import TripList from './TripList.jsx'
import TripDetail, { TripDetailError, TripDetailSkeleton } from './TripDetail.jsx'
import { getTrip, listTrips } from '../../lib/api.js'
import { useTrip } from '../../state/TripContext.jsx'
import { useAnnounce } from '../../state/Announcer.jsx'
import './plan.css'

// Generation warnings are returned only by POST /api/trips (not stored), so
// keep them per trip for this browser session to survive a refresh.
const WARNINGS_KEY = (id) => `tripwise.warnings.${id}`

function readWarnings(id) {
  try {
    return JSON.parse(sessionStorage.getItem(WARNINGS_KEY(id)) ?? '[]')
  } catch {
    return []
  }
}

function saveWarnings(id, warnings) {
  try {
    if (warnings?.length) sessionStorage.setItem(WARNINGS_KEY(id), JSON.stringify(warnings))
  } catch {
    // Storage blocked: warnings are still shown until the page is reloaded.
  }
}

function toSummary(trip) {
  const { cities: _c, days: _d, warnings: _w, ...summary } = trip
  return summary
}

export default function PlanView({ tripParam: rawParam, headingRef, active }) {
  const uid = useId()
  const tripParam = rawParam ? rawParam.toLowerCase() : null
  const { tripId } = useTrip()
  const announce = useAnnounce()
  const [list, setList] = useState({ status: 'loading', trips: [], error: null })
  const [tripsById, setTripsById] = useState({}) // opened or just-generated trips
  const [detailError, setDetailError] = useState(null) // { id, error }
  const [busy, setBusy] = useState(null) // { phase, label } while the form works
  const [listNonce, setListNonce] = useState(0)
  const [detailNonce, setDetailNonce] = useState(0)

  // Saved trips (refetched when returning to the overview).
  useEffect(() => {
    if (!active || tripParam) return undefined
    const ctrl = new AbortController()
    listTrips(tripId, { signal: ctrl.signal })
      .then((data) => setList({ status: 'ready', trips: data.trips, error: null }))
      .catch((error) => {
        if (!ctrl.signal.aborted) setList((prev) => ({ ...prev, status: 'error', error }))
      })
    return () => ctrl.abort()
  }, [tripId, active, tripParam, listNonce])

  // One trip via GET /api/trips/{id}, unless it is already in memory.
  const loaded = tripParam ? tripsById[tripParam] : null
  useEffect(() => {
    if (!active || !tripParam || loaded) return undefined
    const ctrl = new AbortController()
    getTrip(tripId, tripParam, { signal: ctrl.signal })
      .then((trip) => setTripsById((prev) => ({ ...prev, [tripParam]: trip })))
      .catch((error) => {
        if (!ctrl.signal.aborted) setDetailError({ id: tripParam, error })
      })
    return () => ctrl.abort()
  }, [tripId, tripParam, active, loaded, detailNonce])

  const handleCreated = useCallback(
    (trip) => {
      setTripsById((prev) => ({ ...prev, [trip.id]: trip }))
      saveWarnings(trip.id, trip.warnings)
      setList((prev) => ({
        status: 'ready',
        error: null,
        trips: [toSummary(trip), ...prev.trips.filter((t) => t.id !== trip.id)],
      }))
      announce(`Your ${trip.num_days}-day plan for ${trip.city_names.join(', ')} is ready.`)
      window.location.hash = `plan/${trip.id}`
    },
    [announce],
  )

  // After an edit the server returns the full trip; keep it as the source of truth.
  const handleTripChange = useCallback((trip) => {
    const { warnings: _w, ...stored } = trip
    setTripsById((prev) => ({ ...prev, [trip.id]: stored }))
    setList((prev) => ({
      ...prev,
      trips: [toSummary(stored), ...prev.trips.filter((t) => t.id !== trip.id)],
    }))
  }, [])

  function retryList() {
    setList((prev) => ({ ...prev, status: 'loading', error: null }))
    setListNonce((n) => n + 1)
  }

  function retryDetail() {
    setDetailError(null)
    setDetailNonce((n) => n + 1)
  }

  if (tripParam) {
    if (loaded) {
      return (
        <TripDetail
          trip={loaded}
          warnings={readWarnings(loaded.id)}
          headingRef={headingRef}
          onTripChange={handleTripChange}
        />
      )
    }
    if (detailError?.id === tripParam) {
      return <TripDetailError error={detailError.error} onRetry={retryDetail} />
    }
    return <TripDetailSkeleton label="Opening your trip…" />
  }

  return (
    <div className="plan">
      <section className="plan-intro" aria-labelledby={`${uid}-h1`}>
        <p className="eyebrow" aria-hidden="true">
          Plan a trip
        </p>
        <h1 id={`${uid}-h1`} ref={headingRef} tabIndex={-1} className="display">
          Plan your days, not your tabs.
        </h1>
        <p className="editorial-script" aria-hidden="true">route notes, thoughtfully arranged</p>
        <p className="lede">
          Pick a city, how long you have and what you enjoy. TripWise arranges real nearby places into a
          day-by-day plan you can come back to.
        </p>
      </section>

      <div className="plan__layout">
        <div className="plan__form">
          <PlanForm onCreated={handleCreated} onBusyChange={setBusy} />
        </div>
        <div className="plan__side">
          {busy?.phase === 'generating' ? (
            <TripDetailSkeleton label={`Finding real places in ${busy.label} and arranging your days…`} />
          ) : (
            <TripList state={list} onRetry={retryList} headingId={`${uid}-trips`} />
          )}
        </div>
      </div>
    </div>
  )
}
