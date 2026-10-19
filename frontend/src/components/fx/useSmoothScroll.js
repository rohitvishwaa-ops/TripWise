/*
  Lenis smooth scrolling (https://lenis.darkroom.engineering, MIT) for the
  landing page only: the app views keep native scrolling so the Leaflet map,
  dialogs and long forms behave as before. Lenis drives the real window
  scroll, so Motion's useScroll and the ScrollExpand section follow it.
  Skipped entirely when the visitor prefers reduced motion.
*/
import { useEffect } from 'react'
import Lenis from 'lenis'
import 'lenis/dist/lenis.css'

export function useSmoothScroll() {
  useEffect(() => {
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return undefined
    const lenis = new Lenis({ lerp: 0.1, anchors: false, autoRaf: true })
    return () => lenis.destroy()
  }, [])
}
