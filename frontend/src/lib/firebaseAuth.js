// Small Firebase Auth REST client used by the future auth UI. Keeping this
// module dependency-free lets the current guest app build without a remote
// SDK install. Firebase's Web API key is a client identifier, never a secret.

const API_KEY = import.meta.env.VITE_FIREBASE_API_KEY ?? ''
const PROJECT_ID = import.meta.env.VITE_FIREBASE_PROJECT_ID ?? ''
const AUTH_STORAGE_KEY = 'tripwise.firebase.session'
const AUTH_EVENT = 'tripwise:auth-change'

export class FirebaseAuthError extends Error {
  constructor(message, code = 'auth/unknown') {
    super(message)
    this.name = 'FirebaseAuthError'
    this.code = code
  }
}

function configured() {
  return Boolean(API_KEY && PROJECT_ID)
}

function requireConfig() {
  if (!configured()) throw new FirebaseAuthError('Firebase authentication is not configured.', 'auth/configuration-not-found')
}

function readSession() {
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY)
    if (!raw) return null
    const session = JSON.parse(raw)
    if (!session?.idToken || !session?.refreshToken || !session?.expiresAt) return null
    return session
  } catch {
    return null
  }
}

function writeSession(data) {
  const session = {
    idToken: data.idToken,
    refreshToken: data.refreshToken,
    uid: data.localId ?? data.user_id,
    email: data.email ?? null,
    expiresAt: Date.now() + Number(data.expiresIn ?? data.expires_in ?? 3600) * 1000,
  }
  localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(session))
  window.dispatchEvent(new Event(AUTH_EVENT))
  return session
}

function clearSession() {
  localStorage.removeItem(AUTH_STORAGE_KEY)
  window.dispatchEvent(new Event(AUTH_EVENT))
}

async function call(path, body, { form = false } = {}) {
  requireConfig()
  const response = await fetch(`https://${path}?key=${encodeURIComponent(API_KEY)}`, {
    method: 'POST',
    headers: form ? { 'Content-Type': 'application/x-www-form-urlencoded' } : { 'Content-Type': 'application/json' },
    body: form ? new URLSearchParams(body) : JSON.stringify(body),
  })
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const code = data?.error?.message ?? 'AUTH_ERROR'
    throw new FirebaseAuthError('Firebase authentication request failed.', `auth/${code.toLowerCase()}`)
  }
  return data
}

export async function registerWithEmail(email, password) {
  const data = await call('identitytoolkit.googleapis.com/v1/accounts:signUp', {
    email, password, returnSecureToken: true,
  })
  const session = writeSession(data)
  await sendEmailVerification(session.idToken)
  return session
}

export async function signInWithEmail(email, password) {
  return writeSession(await call('identitytoolkit.googleapis.com/v1/accounts:signInWithPassword', {
    email, password, returnSecureToken: true,
  }))
}

export async function sendEmailVerification(idToken = getSession()?.idToken) {
  if (!idToken) throw new FirebaseAuthError('Sign in before requesting verification.', 'auth/no-current-user')
  return call('identitytoolkit.googleapis.com/v1/accounts:sendOobCode', {
    requestType: 'VERIFY_EMAIL', idToken,
  })
}

export async function sendPasswordReset(email) {
  return call('identitytoolkit.googleapis.com/v1/accounts:sendOobCode', {
    requestType: 'PASSWORD_RESET', email,
  })
}

export async function refreshSession(refreshToken) {
  const data = await call('securetoken.googleapis.com/v1/token', {
    grant_type: 'refresh_token', refresh_token: refreshToken,
  }, { form: true })
  return writeSession(data)
}

export function getSession() {
  return readSession()
}

export async function getIdToken() {
  const session = readSession()
  if (!session) return null
  if (session.expiresAt > Date.now() + 60_000) return session.idToken
  try {
    return (await refreshSession(session.refreshToken)).idToken
  } catch (error) {
    clearSession()
    throw error
  }
}

export function signOut() {
  clearSession()
}

export function onAuthStateChanged(callback) {
  const listener = () => callback(readSession())
  window.addEventListener(AUTH_EVENT, listener)
  listener()
  return () => window.removeEventListener(AUTH_EVENT, listener)
}

export { configured as isFirebaseConfigured }
