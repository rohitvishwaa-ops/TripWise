import { useEffect, useRef, useState } from 'react'
import { Compass, MagnifyingGlass, Path, Suitcase } from '@phosphor-icons/react'
import ExploreView from './components/ExploreView.jsx'
import TripView from './components/TripView.jsx'
import PlanView from './components/plan/PlanView.jsx'
import PlaceDialog from './components/PlaceDialog.jsx'
import DataCredit from './components/DataCredit.jsx'
import { useGlide } from './components/fx/useGlide.js'
import { TripProvider, useTrip } from './state/TripContext.jsx'
import { AnnouncerProvider } from './state/Announcer.jsx'
import { useHashRoute } from './state/useHashRoute.js'
import './app.css'

const TITLES = { explore: 'Explore | TripWise', trip: 'My Trip | TripWise', plan: 'Plan | TripWise' }

function Shell() {
  const { view, param } = useHashRoute()
  const { items, status } = useTrip()
  const [selected, setSelected] = useState(null)
  const exploreHeading = useRef(null)
  const tripHeading = useRef(null)
  const planHeading = useRef(null)
  const routeKey = param ? `${view}/${param}` : view
  const lastRoute = useRef(routeKey)
  const navRef = useRef(null)
  useGlide(navRef, view)

  // SPA navigation: update the title and move focus to the new view's heading
  // (skipped on first load so the page doesn't steal focus). An opened trip
  // sets its own title; while it loads, focus goes to the main region.
  useEffect(() => {
    if (!(view === 'plan' && param)) document.title = TITLES[view]
    // Only move focus when the route really changed (not on first load, and
    // not when React re-runs effects in development StrictMode).
    if (lastRoute.current === routeKey) return
    lastRoute.current = routeKey
    const heading = { explore: exploreHeading, trip: tripHeading, plan: planHeading }[view].current
    ;(heading ?? document.getElementById('content'))?.focus()
  }, [routeKey, view, param])

  function goToTrip() {
    setSelected(null)
    window.location.hash = 'trip'
  }

  const tripCount = status === 'ready' ? items.length : null

  return (
    <>
      <a href="#content" className="skip-link">
        Skip to content
      </a>
      <header className="site-header">
        <div className="site-header__inner">
          <a href="#explore" className="brand">
            <span className="brand__mark" aria-hidden="true">
              <Compass size={22} weight="duotone" />
            </span>
            <span className="brand__name">TripWise</span>
          </a>
          <nav aria-label="Main">
            <ul className="nav" ref={navRef}>
              <li>
                <a
                  href="#explore"
                  className="nav__link"
                  aria-current={view === 'explore' ? 'page' : undefined}
                >
                  <MagnifyingGlass aria-hidden="true" size={18} weight="bold" />
                  Explore
                </a>
              </li>
              <li>
                <a
                  href="#plan"
                  className="nav__link"
                  aria-current={view === 'plan' ? 'page' : undefined}
                >
                  <Path aria-hidden="true" size={18} weight="bold" />
                  Plan
                </a>
              </li>
              <li>
                <a
                  href="#trip"
                  className="nav__link"
                  aria-current={view === 'trip' ? 'page' : undefined}
                >
                  <Suitcase aria-hidden="true" size={18} weight="bold" />
                  My Trip
                  {tripCount !== null && tripCount > 0 && (
                    <span className="nav__count">
                      <span aria-hidden="true">{tripCount}</span>
                      <span className="visually-hidden">
                        ({tripCount} saved)
                      </span>
                    </span>
                  )}
                </a>
              </li>
            </ul>
          </nav>
        </div>
      </header>

      <main id="content" tabIndex={-1} className="page">
        <div hidden={view !== 'explore'}>
          <ExploreView headingRef={exploreHeading} onOpenPlace={setSelected} />
        </div>
        <div hidden={view !== 'plan'}>
          <PlanView tripParam={param} headingRef={planHeading} active={view === 'plan'} />
        </div>
        <div hidden={view !== 'trip'}>
          <TripView headingRef={tripHeading} onOpenPlace={setSelected} />
        </div>
      </main>

      <footer className="site-footer">
        <DataCredit />
      </footer>

      <PlaceDialog
        place={selected}
        onClose={() => setSelected(null)}
        onGoToTrip={view === 'trip' ? null : goToTrip}
      />
    </>
  )
}

export default function App() {
  return (
    <AnnouncerProvider>
      <TripProvider>
        <Shell />
      </TripProvider>
    </AnnouncerProvider>
  )
}
