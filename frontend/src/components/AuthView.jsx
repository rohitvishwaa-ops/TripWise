import { useState } from 'react'
import { getSession, isFirebaseConfigured, registerWithEmail, sendEmailVerification, sendPasswordReset, signInWithEmail } from '../lib/firebaseAuth.js'

const copy = {
  login: ['Welcome back', 'Sign in to continue planning.'],
  register: ['Create your travel desk', 'Save your plans across visits.'],
  recover: ['Reset your password', 'We will send a recovery link if the address is registered.'],
  verify: ['Check your inbox', 'Verify your email to keep your account secure.'],
  account: ['Your account', 'Your signed-in workspace is ready.'],
}

export default function AuthView({ view, session }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [configured] = useState(isFirebaseConfigured())
  const currentSession = session || getSession()
  const [title, lede] = copy[view]

  async function submit(event) {
    event.preventDefault(); setBusy(true); setError(''); setMessage('')
    try {
      if (!configured) throw new Error('Firebase authentication is not configured yet. Add the VITE_FIREBASE values to enable accounts.')
      if (view === 'login') { await signInWithEmail(email, password); window.location.hash = 'explore' }
      else if (view === 'register') { await registerWithEmail(email, password); window.location.hash = 'verify' }
      else { await sendPasswordReset(email); setMessage('If that email is registered, a reset link is on its way.') }
    } catch (err) { setError(err.message || 'Something went wrong. Please try again.') }
    finally { setBusy(false) }
  }

  async function verify() {
    setBusy(true); setError(''); setMessage('')
    try { await sendEmailVerification(currentSession?.idToken); setMessage('Verification email sent. Check your inbox.') }
    catch (err) { setError(err.message || 'Could not send verification email.') }
    finally { setBusy(false) }
  }

  if (view === 'account') return <section className="auth-panel" aria-labelledby="auth-title"><p className="eyebrow">Account</p><h1 id="auth-title">{title}</h1><p>{lede}</p><p className="auth-panel__identity">{currentSession?.email || 'Guest workspace'}</p><a className="button button--primary" href="#explore">Continue exploring</a></section>
  if (view === 'verify') return <section className="auth-panel" aria-labelledby="auth-title"><p className="eyebrow">Almost there</p><h1 id="auth-title">{title}</h1><p>{lede}</p><button className="button button--primary" type="button" onClick={verify} disabled={busy}>{busy ? 'Sending…' : 'Resend verification email'}</button>{message && <p className="form-message">{message}</p>}{error && <p className="form-error" role="alert">{error}</p>}<p className="auth-panel__switch"><a href="#login">Back to sign in</a></p></section>
  return <section className="auth-panel" aria-labelledby="auth-title"><p className="eyebrow">TripWise account</p><h1 id="auth-title">{title}</h1><p>{lede}</p>{!configured && <p className="form-message">Guest mode is available now. Accounts activate when Firebase is configured.</p>}<form onSubmit={submit} className="auth-form"><label htmlFor="auth-email">Email</label><input id="auth-email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required /><>{view !== 'recover' && <><label htmlFor="auth-password">Password</label><input id="auth-password" type="password" autoComplete={view === 'login' ? 'current-password' : 'new-password'} minLength="8" value={password} onChange={(e) => setPassword(e.target.value)} required /></>}</><button className="button button--primary" type="submit" disabled={busy}>{busy ? 'Working…' : view === 'login' ? 'Sign in' : view === 'register' ? 'Create account' : 'Send reset link'}</button></form>{message && <p className="form-message">{message}</p>}{error && <p className="form-error" role="alert">{error}</p>}<p className="auth-panel__switch">{view === 'login' ? <>New here? <a href="#register">Create an account</a> · <a href="#recover">Forgot password?</a></> : <>Prefer no account? <a href="#explore">Continue as guest</a> · <a href="#login">Sign in</a></>}</p></section>
}
