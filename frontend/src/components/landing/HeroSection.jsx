/*
  Landing hero: copy, the "Where to?" search and the interactive globe.

  Two globe modes share one selection model:
  - Sample day: the globe tours example cities (until the visitor interacts)
    and the ticket shows a sample day for the focused city.
  - Build a route: clicking pins or city buttons adds cities in travel order;
    the globe draws the flight path and "Plan this route" opens the planner
    with those cities filled in.

  The search turns the globe to the typed city (looked up with the same
  /api/geocode the planner uses), then opens the planner with it filled in.
  If the lookup is slow, fails or is ambiguous, it opens the planner straight
  away and the form handles it, so the search never blocks on the network.
*/
import { lazy, Suspense, useEffect, useId, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { ArrowRight, MagnifyingGlass, X } from '@phosphor-icons/react'
import DestinationImage from '../plan/DestinationImage.jsx'
import { geocodeLocation } from '../../lib/api.js'
import { planLink } from '../../state/useHashRoute.js'
import { HERO_CITIES } from './cities.js'
import { Reveal, RevealHeadline } from './motionKit.jsx'

const HeroGlobe = lazy(() => import('./HeroGlobe.jsx'))

const HEADLINE = [
  { text: 'Go somewhere' },
  { text: 'worth remembering.', className: 'reveal-line--em' },
]
const STOP_TIMES = ['Morning', 'Afternoon', 'Evening']
const ADVANCE_MS = 5200
const FLY_MS = 1300
const LOOKUP_TIMEOUT_MS = 2500
const MAX_ROUTE = 6
const EASE = [0.16, 1, 0.3, 1]

const normalize = (text) => text.trim().replace(/\s+/g, ' ')

export default function HeroSection() {
  const uid = useId()
  const reduce = useReducedMotion()
  const [mode, setMode] = useState('sample') // 'sample' | 'route'
  const [focus, setFocus] = useState({ index: 0, previous: null })
  const [route, setRoute] = useState([])
  const [extra, setExtra] = useState(null) // a searched city that is not in HERO_CITIES
  const [userDriven, setUserDriven] = useState(false)
  const [query, setQuery] = useState('')
  const [searchError, setSearchError] = useState(null)
  const [flying, setFlying] = useState(false)
  const lookup = useRef(null)
  const navTimer = useRef(0)

  const cities = useMemo(() => (extra ? [...HERO_CITIES, extra] : HERO_CITIES), [extra])
  const focusedCity = cities[focus.index]
  const isExtra = extra && focus.index === cities.length - 1

  useEffect(
    () => () => {
      lookup.current?.abort()
      window.clearTimeout(navTimer.current)
    },
    [],
  )

  // The tour: sample mode only, until the visitor does anything.
  useEffect(() => {
    if (reduce || userDriven || mode !== 'sample') return undefined
    const timer = window.setInterval(() => {
      if (document.hidden) return
      setFocus((current) => ({ index: (current.index + 1) % HERO_CITIES.length, previous: current.index }))
    }, ADVANCE_MS)
    return () => window.clearInterval(timer)
  }, [reduce, userDriven, mode])

  const focusOn = (index) =>
    setFocus((current) => (current.index === index ? current : { index, previous: current.index }))

  const toggleRouteCity = (index) => {
    setRoute((current) => {
      if (current.includes(index)) return current.filter((i) => i !== index)
      if (current.length >= MAX_ROUTE) return current
      return [...current, index]
    })
    focusOn(index)
  }

  const selectCity = (index) => {
    setUserDriven(true)
    if (mode === 'route') toggleRouteCity(index)
    else focusOn(index)
  }

  const switchMode = (next) => {
    if (next === mode) return
    setUserDriven(true)
    setMode(next)
  }

  async function handleSearch(event) {
    event.preventDefault()
    if (flying) return
    const text = normalize(query)
    if (text.length < 2) {
      setSearchError('Enter a city, for example Kyoto or Porto, Portugal.')
      return
    }
    setSearchError(null)
    setUserDriven(true)
    const go = (name) => {
      window.location.hash = planLink({ cities: [name] })
    }
    if (reduce) return go(text)

    setFlying(true)
    setMode('sample')
    const flyTo = (index, name) => {
      focusOn(index)
      navTimer.current = window.setTimeout(() => go(name), FLY_MS)
    }

    const known = HERO_CITIES.findIndex((c) => c.name.toLowerCase() === text.toLowerCase())
    if (known !== -1) return flyTo(known, HERO_CITIES[known].name)

    lookup.current?.abort()
    const ctrl = new AbortController()
    lookup.current = ctrl
    const timeout = window.setTimeout(() => ctrl.abort(), LOOKUP_TIMEOUT_MS)
    try {
      const data = await geocodeLocation(text, { signal: ctrl.signal })
      window.clearTimeout(timeout)
      const top = data.confident ? data.results[0] : null
      if (!top) return go(text)
      const same = HERO_CITIES.findIndex((c) => c.name.toLowerCase() === top.name.toLowerCase())
      if (same !== -1) return flyTo(same, text)
      const country = top.address?.split(',').at(-1)?.trim()
      setExtra({ name: top.name, country: country && country !== top.name ? country : '', lat: top.latitude, lon: top.longitude })
      // Keep the typed text: the planner looks it up again and shows the same place.
      flyTo(HERO_CITIES.length, text)
    } catch {
      window.clearTimeout(timeout)
      go(text)
    }
  }

  const arcs =
    mode === 'route'
      ? route.slice(1).map((to, i) => ({ from: route[i], to, key: `r-${route[i]}-${to}` }))
      : focus.previous !== null && focus.previous !== focus.index
        ? [{ from: focus.previous, to: focus.index, key: `s-${focus.previous}-${focus.index}` }]
        : []

  const routeNames = route.map((i) => cities[i].name)

  return (
    <section className="home-hero" aria-labelledby="home-title">
      <div className="home-hero__copy">
        <p className="eyebrow">Smart travel planner</p>
        <RevealHeadline id="home-title" className="home-hero__title" lines={HEADLINE} />
        <Reveal as="p" className="home-hero__lede" delay={0.45} y={16}>
          Find real places, save the ones you like, and turn a city or a whole route into a day-by-day plan.
        </Reveal>

        <Reveal delay={0.55} y={16}>
          <form className="where-to" onSubmit={handleSearch} noValidate role="search">
            <label className="where-to__label" htmlFor={`${uid}-where`}>
              Where to?
            </label>
            <div className="where-to__field" data-invalid={searchError ? '' : undefined}>
              <MagnifyingGlass className="where-to__icon" size={20} weight="bold" aria-hidden="true" />
              <input
                id={`${uid}-where`}
                className="where-to__input"
                type="text"
                autoComplete="off"
                enterKeyHint="go"
                maxLength={200}
                placeholder="Kyoto, Lisbon, Cusco..."
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value)
                  if (searchError) setSearchError(null)
                }}
                aria-invalid={searchError ? 'true' : undefined}
                aria-describedby={searchError ? `${uid}-where-error` : undefined}
              />
              <motion.button
                type="submit"
                className="btn btn--primary where-to__submit"
                whileTap={reduce ? undefined : { scale: 0.97 }}
                aria-busy={flying || undefined}
              >
                {flying ? 'Taking you there' : 'Plan a trip'}
                <ArrowRight aria-hidden="true" size={18} weight="bold" />
              </motion.button>
            </div>
            {searchError && (
              <p className="field-error where-to__error" id={`${uid}-where-error`} role="alert">
                {searchError}
              </p>
            )}
          </form>
          <a className="where-to__alt" href="#explore">
            Or explore places near you
          </a>
        </Reveal>
      </div>

      <Reveal className="home-hero__visual" delay={0.2} y={24}>
        <div className="hero-planner">
          <div className="globe-modes" role="group" aria-label="Globe mode">
            {[
              { value: 'sample', label: 'Sample day' },
              { value: 'route', label: 'Build a route' },
            ].map((m) => (
              <button
                key={m.value}
                type="button"
                className="globe-modes__btn"
                aria-pressed={mode === m.value}
                onClick={() => switchMode(m.value)}
              >
                {mode === m.value && (
                  <motion.span
                    layoutId="globe-mode-pill"
                    className="globe-modes__pill"
                    transition={reduce ? { duration: 0 } : { type: 'spring', stiffness: 420, damping: 34 }}
                  />
                )}
                <span className="globe-modes__label">{m.label}</span>
              </button>
            ))}
          </div>

          <div className="hero-planner__stage">
            <Suspense fallback={<div className="hero-globe hero-globe--placeholder" aria-hidden="true" />}>
              <HeroGlobe
                cities={cities}
                focus={focus.index}
                arcs={arcs}
                routeLines={mode === 'sample'}
                marked={mode === 'route' ? route : []}
                onSelect={selectCity}
                onInteract={() => setUserDriven(true)}
                reduce={reduce}
              />
            </Suspense>

            {/* Announce only changes the visitor asked for, not the tour. */}
            <div className="trip-ticket" aria-live={userDriven ? 'polite' : 'off'}>
              <AnimatePresence mode="wait" initial={false}>
                {mode === 'sample' ? (
                  <motion.div
                    key={`sample-${focusedCity.name}`}
                    initial={reduce ? false : { opacity: 0, y: 14, filter: 'blur(4px)' }}
                    animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
                    exit={reduce ? undefined : { opacity: 0, y: -10, filter: 'blur(4px)' }}
                    transition={{ duration: 0.45, ease: EASE }}
                  >
                    <div className="trip-ticket__head">
                      <DestinationImage city={focusedCity.name} className="trip-ticket__photo" alt="" />
                      <div>
                        <p className="trip-ticket__city">{focusedCity.name}</p>
                        <p className="trip-ticket__meta">
                          {isExtra
                            ? 'Opening the planner'
                            : `${focusedCity.country}, sample day 1`}
                        </p>
                      </div>
                    </div>
                    {isExtra ? (
                      <p className="trip-ticket__note">TripWise will find real places here and arrange your days.</p>
                    ) : (
                      <ol className="trip-ticket__stops">
                        {focusedCity.stops.map((stop, i) => (
                          <motion.li
                            key={stop}
                            initial={reduce ? false : { opacity: 0, x: -8 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ duration: 0.4, delay: 0.12 + i * 0.07, ease: EASE }}
                          >
                            <span className="trip-ticket__time">{STOP_TIMES[i]}</span>
                            {stop}
                          </motion.li>
                        ))}
                      </ol>
                    )}
                  </motion.div>
                ) : (
                  <motion.div
                    key="route"
                    initial={reduce ? false : { opacity: 0, y: 14 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={reduce ? undefined : { opacity: 0, y: -10 }}
                    transition={{ duration: 0.4, ease: EASE }}
                  >
                    <p className="trip-ticket__city">Your route</p>
                    {route.length === 0 ? (
                      <p className="trip-ticket__note">Pick cities on the globe or below, in the order you will travel.</p>
                    ) : (
                      <ol className="route-list">
                        <AnimatePresence initial={false}>
                          {route.map((index, n) => (
                            <motion.li
                              key={cities[index].name}
                              layout={!reduce}
                              initial={reduce ? false : { opacity: 0, x: -8 }}
                              animate={{ opacity: 1, x: 0 }}
                              exit={reduce ? undefined : { opacity: 0, x: 8 }}
                              transition={{ duration: 0.3, ease: EASE }}
                              className="route-list__item"
                            >
                              <span className="route-list__num" aria-hidden="true">{n + 1}</span>
                              <span className="route-list__name">{cities[index].name}</span>
                              <button
                                type="button"
                                className="route-list__remove"
                                onClick={() => toggleRouteCity(index)}
                                aria-label={`Remove ${cities[index].name} from the route`}
                              >
                                <X size={14} weight="bold" aria-hidden="true" />
                              </button>
                            </motion.li>
                          ))}
                        </AnimatePresence>
                      </ol>
                    )}
                    {route.length > 1 ? (
                      <a className="btn btn--primary route-cta" href={planLink({ cities: routeNames })}>
                        Plan this route <ArrowRight aria-hidden="true" size={16} weight="bold" />
                      </a>
                    ) : (
                      route.length === 1 && <p className="trip-ticket__note">Add one more city to plan the route.</p>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>

          <div className="hero-cities" role="group" aria-label={mode === 'route' ? 'Add cities to your route' : 'Sample destinations'}>
            {HERO_CITIES.map((c, i) => {
              const pressed = mode === 'route' ? route.includes(i) : i === focus.index
              return (
                <button
                  key={c.name}
                  type="button"
                  className="hero-cities__chip"
                  aria-pressed={pressed}
                  onClick={() => selectCity(i)}
                >
                  {mode === 'sample' && pressed && (
                    <motion.span
                      layoutId="hero-city-pill"
                      className="hero-cities__pill"
                      transition={reduce ? { duration: 0 } : { type: 'spring', stiffness: 420, damping: 34 }}
                    />
                  )}
                  <span className="hero-cities__label">
                    {mode === 'route' && pressed && <span className="hero-cities__order">{route.indexOf(i) + 1}</span>}
                    {c.name}
                  </span>
                </button>
              )
            })}
          </div>
        </div>
      </Reveal>
    </section>
  )
}
