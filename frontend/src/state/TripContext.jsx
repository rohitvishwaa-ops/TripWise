import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { addToItinerary, getItinerary, removeFromItinerary } from '../lib/api.js'
import { getTripId } from '../lib/tripId.js'

const TripContext = createContext(null)

export function TripProvider({ children }) {
  const tripId = useMemo(() => getTripId(), [])
  const [items, setItems] = useState([])
  const [status, setStatus] = useState('loading') // 'loading' | 'ready' | 'error'
  const [error, setError] = useState(null)
  const [pending, setPending] = useState(() => new Set())
  const loadController = useRef(null)

  const fetchTrip = useCallback(
    async ({ quiet = false } = {}) => {
      loadController.current?.abort()
      const controller = new AbortController()
      loadController.current = controller
      try {
        const data = await getItinerary(tripId, { signal: controller.signal })
        setItems(data.places)
        setStatus('ready')
        setError(null)
      } catch (err) {
        if (controller.signal.aborted) return
        if (!quiet) {
          setError(err)
          setStatus('error')
        }
      }
    },
    [tripId],
  )

  // Initial load: state already starts as 'loading'.
  useEffect(() => {
    // State is only set after the awaited fetch resolves, not synchronously.
    // eslint-disable-next-line react/set-state-in-effect
    fetchTrip()
    return () => loadController.current?.abort()
  }, [fetchTrip])

  // Manual retry shows the loading state; quiet syncs keep the current view.
  const reload = useCallback(
    ({ quiet = false } = {}) => {
      if (!quiet) {
        setStatus('loading')
        setError(null)
      }
      return fetchTrip({ quiet })
    },
    [fetchTrip],
  )

  const markPending = useCallback((id, on) => {
    setPending((prev) => {
      const next = new Set(prev)
      if (on) next.add(id)
      else next.delete(id)
      return next
    })
  }, [])

  const add = useCallback(
    async (place) => {
      markPending(place.id, true)
      try {
        const saved = await addToItinerary(tripId, place)
        setItems((prev) => (prev.some((p) => p.id === saved.id) ? prev : [...prev, saved]))
        return { ok: true }
      } catch (err) {
        if (err.status === 409) {
          // Saved earlier (e.g. in another tab). Sync so the UI reflects it.
          await reload({ quiet: true })
          return { ok: true, duplicate: true }
        }
        return { ok: false, error: err }
      } finally {
        markPending(place.id, false)
      }
    },
    [tripId, reload, markPending],
  )

  const remove = useCallback(
    async (placeId) => {
      markPending(placeId, true)
      try {
        await removeFromItinerary(tripId, placeId)
        setItems((prev) => prev.filter((p) => p.id !== placeId))
        return { ok: true }
      } catch (err) {
        if (err.status === 404) {
          // Already gone on the server; drop it locally too.
          setItems((prev) => prev.filter((p) => p.id !== placeId))
          return { ok: true }
        }
        return { ok: false, error: err }
      } finally {
        markPending(placeId, false)
      }
    },
    [tripId, markPending],
  )

  const savedIds = useMemo(() => new Set(items.map((p) => p.id)), [items])

  const value = useMemo(
    () => ({ tripId, items, savedIds, status, error, pending, add, remove, reload }),
    [tripId, items, savedIds, status, error, pending, add, remove, reload],
  )

  return <TripContext.Provider value={value}>{children}</TripContext.Provider>
}

// eslint-disable-next-line react/only-export-components
export function useTrip() {
  const ctx = useContext(TripContext)
  if (!ctx) throw new Error('useTrip must be used inside <TripProvider>')
  return ctx
}
