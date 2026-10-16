import { useSyncExternalStore } from 'react'

// Deep-linkable, back-button friendly views:
//   #explore, #trip (saved places), #plan, #plan/<trip id>
const VIEWS = ['explore', 'trip', 'plan']

function read() {
  return window.location.hash.replace(/^#\/?/, '')
}

function subscribe(callback) {
  window.addEventListener('hashchange', callback)
  return () => window.removeEventListener('hashchange', callback)
}

export function parseRoute(hash) {
  const [view, param = null] = hash.split('/')
  return VIEWS.includes(view) ? { view, param: view === 'plan' ? param : null } : { view: 'explore', param: null }
}

export function useHashRoute() {
  // Subscribe to the raw hash string (stable between renders), then parse.
  return parseRoute(useSyncExternalStore(subscribe, read, () => ''))
}
