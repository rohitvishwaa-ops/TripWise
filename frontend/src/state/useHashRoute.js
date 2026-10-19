import { useSyncExternalStore } from 'react'

// Deep-linkable, back-button friendly views:
//   #explore, #trip (saved places), #plan, #plan/<trip id>
// #plan also takes a prefill query from the landing page, e.g.
//   #plan?city=Kyoto&pace=packed&interests=food,history
//   #plan?city=Kyoto&city=Lisbon&city=Cusco   (a route, in travel order)
// Cities repeat the parameter instead of using commas, because a name like
// "Porto, Portugal" contains one.
const VIEWS = ['landing', 'explore', 'trip', 'plan', 'login', 'register', 'verify', 'recover', 'account']

function read() {
  return window.location.hash.replace(/^#\/?/, '')
}

function subscribe(callback) {
  window.addEventListener('hashchange', callback)
  return () => window.removeEventListener('hashchange', callback)
}

export function parseRoute(hash) {
  const [path, query = ''] = hash.split('?')
  const [view, param = null] = path.split('/')
  if (!VIEWS.includes(view)) return { view: 'landing', param: null, query: '' }
  return { view, param: view === 'plan' ? param : null, query: view === 'plan' ? query : '' }
}

/** Build a #plan link that opens the form already filled in. */
export function planLink({ cities = [], pace, interests = [] } = {}) {
  const params = new URLSearchParams()
  for (const city of cities) params.append('city', city)
  if (pace) params.set('pace', pace)
  if (interests.length) params.set('interests', interests.join(','))
  const query = params.toString()
  return query ? `#plan?${query}` : '#plan'
}

export function useHashRoute() {
  // Subscribe to the raw hash string (stable between renders), then parse.
  return parseRoute(useSyncExternalStore(subscribe, read, () => ''))
}
