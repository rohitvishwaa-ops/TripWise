import { useEffect, useId, useRef, useState } from 'react'
import { ArrowClockwise, MapTrifold, WarningCircle } from '@phosphor-icons/react'
import SearchForm from './SearchForm.jsx'
import PlaceCard, { PlaceCardSkeleton } from './PlaceCard.jsx'
import DataCredit from './DataCredit.jsx'
import { searchPlaces } from '../lib/api.js'
import { formatCoordinates, formatDistanceKm } from '../lib/format.js'
import { useTrip } from '../state/TripContext.jsx'
import { useAnnounce } from '../state/Announcer.jsx'

const SORTS = [
  { value: 'relevance', label: 'Relevance' },
  { value: 'name', label: 'Name A to Z' },
  { value: 'name_desc', label: 'Name Z to A' },
]

export default function ExploreView({ headingRef, onOpenPlace }) {
  const uid = useId()
  const { savedIds } = useTrip()
  const announce = useAnnounce()
  const [query, setQuery] = useState(null) // last submitted search params
  const [sort, setSort] = useState('relevance')
  const [result, setResult] = useState({ status: 'idle', data: null, error: null })
  const controller = useRef(null)

  useEffect(() => () => controller.current?.abort(), [])

  async function run(params, nextSort) {
    controller.current?.abort()
    const ctrl = new AbortController()
    controller.current = ctrl
    setQuery(params)
    setResult((prev) => ({ status: 'loading', data: prev.data, error: null }))
    try {
      const data = await searchPlaces({ ...params, sort: nextSort }, { signal: ctrl.signal })
      if (ctrl.signal.aborted) return
      setResult({ status: 'success', data, error: null })
      announce(
        data.count === 0
          ? 'No places found.'
          : `Found ${data.count} ${data.count === 1 ? 'place' : 'places'}.`,
      )
    } catch (err) {
      if (ctrl.signal.aborted) return
      setResult({ status: 'error', data: null, error: err })
    }
  }

  function changeSort(value) {
    setSort(value)
    if (query) run(query, value)
  }

  const { status, data, error } = result
  const loading = status === 'loading'

  return (
    <div className="explore">
      <section className="explore__intro" aria-labelledby={`${uid}-h1`}>
        <h1 id={`${uid}-h1`} ref={headingRef} tabIndex={-1} className="display">
          Find places worth the trip.
        </h1>
        <p className="lede">
          Search any city or place, filter by what you love, and save favorites to My Trip.
        </p>
      </section>

      <div className="explore__layout">
        <div className="explore__panel">
          <SearchForm onSearch={(params) => run(params, sort)} busy={loading} />
        </div>

        <section className="results" aria-labelledby={`${uid}-results`} aria-busy={loading}>
          <div className="results__head">
            <div>
              <h2 id={`${uid}-results`} className="section-title">
                Results
              </h2>
              {query && (
                <p className="results__summary">
                  {status === 'success' && (
                    <>
                      <strong>{data.count}</strong> {data.count === 1 ? 'place' : 'places'}{' '}
                    </>
                  )}
                  within {formatDistanceKm(query.radius)} of{' '}
                  {query.label ? (
                    <strong>{query.label}</strong>
                  ) : (
                    <span className="tabular">
                      {formatCoordinates(query.latitude, query.longitude)}
                    </span>
                  )}
                </p>
              )}
            </div>

            <fieldset className="segmented" disabled={!query}>
              <legend className="visually-hidden">Sort results</legend>
              {SORTS.map((s) => (
                <label key={s.value} className="segmented__option">
                  <input
                    type="radio"
                    className="sr-input"
                    name={`${uid}-sort`}
                    value={s.value}
                    checked={sort === s.value}
                    onChange={() => changeSort(s.value)}
                  />
                  <span>{s.label}</span>
                </label>
              ))}
            </fieldset>
          </div>

          {status === 'idle' && (
            <div className="empty">
              <MapTrifold aria-hidden="true" size={40} weight="duotone" />
              <h3>Start with a location</h3>
              <p>Search for a city or place, enter coordinates, or use your current location to see what's nearby.</p>
            </div>
          )}

          {status === 'error' && (
            <div className="notice notice--error" role="alert">
              <WarningCircle aria-hidden="true" size={22} weight="fill" />
              <div>
                <p className="notice__title">Search failed</p>
                <p>{error.message}</p>
              </div>
              <button type="button" className="btn btn--ghost" onClick={() => run(query, sort)}>
                <ArrowClockwise aria-hidden="true" size={18} />
                Try again
              </button>
            </div>
          )}

          {status === 'success' && data.count === 0 && (
            <div className="empty">
              <MapTrifold aria-hidden="true" size={40} weight="duotone" />
              <h3>No places found here</h3>
              <p>Try a wider radius, different categories, or another location.</p>
            </div>
          )}

          {(loading || (status === 'success' && data.count > 0)) && (
            <ul className="place-grid" role="list">
              {loading ? (
                <PlaceCardSkeleton count={6} />
              ) : (
                data.places.map((place, i) => (
                  <PlaceCard
                    key={place.id ?? `${place.latitude},${place.longitude},${i}`}
                    place={place}
                    index={i}
                    saved={place.id ? savedIds.has(place.id) : false}
                    onOpen={onOpenPlace}
                  />
                ))
              )}
            </ul>
          )}
          {status === 'success' && data.count > 0 && <DataCredit className="data-credit--inline" />}
        </section>
      </div>
    </div>
  )
}
