import { createContext, useCallback, useContext, useRef, useState } from 'react'

// One polite live region for the whole page (modern-web-guidance: centralize
// announcements instead of scattering aria-live regions).
const AnnouncerContext = createContext(() => {})

export function AnnouncerProvider({ children }) {
  const [message, setMessage] = useState('')
  const timer = useRef(null)

  const announce = useCallback((text) => {
    clearTimeout(timer.current)
    setMessage('')
    // Small delay so repeated identical messages are still announced and
    // don't collide with focus changes.
    timer.current = setTimeout(() => setMessage(text), 120)
  }, [])

  return (
    <AnnouncerContext.Provider value={announce}>
      {children}
      <div className="visually-hidden" aria-live="polite" aria-atomic="true">
        {message}
      </div>
    </AnnouncerContext.Provider>
  )
}

// eslint-disable-next-line react/only-export-components
export function useAnnounce() {
  return useContext(AnnouncerContext)
}
