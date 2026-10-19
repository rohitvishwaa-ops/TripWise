import { useEffect, useRef, useState } from 'react'
import { Compass, MagnifyingGlass, Moon, Path, Sun, Suitcase } from '@phosphor-icons/react'
import ExploreView from './components/ExploreView.jsx'
import TripView from './components/TripView.jsx'
import PlanView from './components/plan/PlanView.jsx'
import PlaceDialog from './components/PlaceDialog.jsx'
import DataCredit from './components/DataCredit.jsx'
import AddToDayDialog from './components/AddToDayDialog.jsx'
import LandingView from './components/LandingView.jsx'
import AuthView from './components/AuthView.jsx'
import { getSession, onAuthStateChanged, signOut } from './lib/firebaseAuth.js'
import { useGlide } from './components/fx/useGlide.js'
import { TripProvider, useTrip } from './state/TripContext.jsx'
import { AnnouncerProvider } from './state/Announcer.jsx'
import { useHashRoute } from './state/useHashRoute.js'
import './app.css'

const TITLES = { landing: 'TripWise | Plan the journey', explore: 'Explore | TripWise', trip: 'My Trip | TripWise', plan: 'Plan | TripWise', login: 'Sign in | TripWise', register: 'Create account | TripWise', verify: 'Verify email | TripWise', recover: 'Recover account | TripWise', account: 'Account | TripWise' }
const THEME_KEY = 'tripwise-theme'

function readTheme() {
  if (typeof document !== 'undefined' && document.documentElement.dataset.theme) {
    return document.documentElement.dataset.theme
  }
  try {
    const saved = localStorage.getItem(THEME_KEY)
    return saved === 'dark' ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

function Shell() {
  const { view, param } = useHashRoute()
  const { items, status } = useTrip()
  const [selected, setSelected] = useState(null)
  const [dayPlace, setDayPlace] = useState(null)
  const exploreHeading = useRef(null)
  const tripHeading = useRef(null)
  const planHeading = useRef(null)
  const routeKey = param ? `${view}/${param}` : view
  const lastRoute = useRef(routeKey)
  const navRef = useRef(null)
  const [theme, setTheme] = useState(readTheme)
  const [session, setSession] = useState(getSession)
  useGlide(navRef, view)

  useEffect(() => onAuthStateChanged(setSession), [])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.querySelector('meta[name="color-scheme"]')?.setAttribute('content', theme)
    try {
      localStorage.setItem(THEME_KEY, theme)
    } catch {
      // Private browsing can deny storage; the in-memory theme still works.
    }
  }, [theme])

  // SPA navigation: update the title and move focus to the new view's heading
  // (skipped on first load so the page doesn't steal focus). An opened trip
  // sets its own title; while it loads, focus goes to the main region.
  useEffect(() => {
    if (!(view === 'plan' && param)) document.title = TITLES[view]
    // Only move focus when the route really changed (not on first load, and
    // not when React re-runs effects in development StrictMode).
    if (lastRoute.current === routeKey) return
    lastRoute.current = routeKey
    const heading = { explore: exploreHeading, trip: tripHeading, plan: planHeading }[view]?.current
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
          <a href="#landing" className="brand">
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
          <div className="auth-nav">
            {session ? (
              <>
                <a className="auth-nav__link" href="#account">{session.email || 'Account'}</a>
                <button type="button" className="auth-nav__button" onClick={() => { signOut(); window.location.hash = 'landing' }}>Sign out</button>
              </>
            ) : (
              <a className="auth-nav__link" href="#login">Sign in</a>
            )}
          </div>
          <button
            type="button"
            className="theme-toggle"
            aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}
            aria-pressed={theme === 'dark'}
            title={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}
            onClick={() => setTheme((current) => (current === 'light' ? 'dark' : 'light'))}
          >
            {theme === 'light' ? <Moon aria-hidden="true" size={18} weight="bold" /> : <Sun aria-hidden="true" size={18} weight="bold" />}
            <span className="visually-hidden">{theme === 'light' ? 'Dark mode' : 'Light mode'}</span>
          </button>
        </div>
      </header>

      <main id="content" tabIndex={-1} className="page">
        {view === 'landing' && <LandingView />}
        {['login', 'register', 'verify', 'recover', 'account'].includes(view) && <AuthView view={view} session={session} />}
        {view === 'explore' && <ExploreView headingRef={exploreHeading} onOpenPlace={setSelected} onAddToDay={setDayPlace} />}
        {view === 'plan' && <PlanView tripParam={param} headingRef={planHeading} active />}
        {view === 'trip' && <TripView headingRef={tripHeading} onOpenPlace={setSelected} />}
      </main>

      <footer className="site-footer">
        <DataCredit />
      </footer>

      <PlaceDialog
        place={selected}
        onClose={() => setSelected(null)}
        onGoToTrip={view === 'trip' ? null : goToTrip}
        onAddToDay={(place) => { setSelected(null); setDayPlace(place) }}
      />
      <AddToDayDialog place={dayPlace} onClose={() => setDayPlace(null)} />
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
