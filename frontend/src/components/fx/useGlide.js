/*
  Sliding active-item highlight for the main navigation.

  Adapted from PillNav by React Bits (https://reactbits.dev, free JS + CSS
  variant). Copyright (c) 2026 David Haz. MIT + Commons Clause License
  Condition v1.0; see https://github.com/DavidHDev/react-bits/blob/main/LICENSE.md

  Changes for TripWise: only the "glide" indicator is used. Each edge of the
  pill follows its own damped spring (the leading edge is stiffer, so the pill
  stretches toward the new item and settles), exactly as in PillNav. The pill
  is drawn by CSS from custom properties on the existing <ul>, so the links,
  aria-current and the saved-count badge are untouched. Without JavaScript, or
  until the first measurement, the active link keeps its own CSS highlight.
*/
import { useEffect, useRef } from 'react'

// `enabled` re-attaches the indicator when the nav mounts (e.g. after sign-in).
export function useGlide(listRef, activeKey, { bounce = 0.3, stretch = 0.5, enabled = true } = {}) {
  const api = useRef(null)

  useEffect(() => {
    const list = listRef.current
    if (!list || typeof window === 'undefined') return undefined
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
    const state = { x0: 0, x1: 0, v0: 0, v1: 0, ready: false }
    let target = null
    let raf = 0
    let last = 0

    const measure = () => {
      const active = list.querySelector('[aria-current="page"]')
      if (!active) {
        target = null
        list.removeAttribute('data-glide')
        return
      }
      const box = active.getBoundingClientRect()
      const base = list.getBoundingClientRect()
      target = { t0: box.left - base.left, t1: box.right - base.left, top: box.top - base.top, h: box.height }
      list.style.setProperty('--glide-top', `${target.top}px`)
      list.style.setProperty('--glide-h', `${target.h}px`)
    }

    const render = () => {
      list.style.setProperty('--glide-x', `${state.x0.toFixed(2)}px`)
      list.style.setProperty('--glide-w', `${Math.max(0, state.x1 - state.x0).toFixed(2)}px`)
    }

    const tick = (now) => {
      raf = 0
      if (!target) return
      const { t0, t1 } = target
      const dt = last ? Math.min(0.05, (now - last) / 1000) : 1 / 60
      last = now
      if (!state.ready || reduce) {
        state.x0 = t0
        state.x1 = t1
        state.v0 = 0
        state.v1 = 0
        state.ready = true
        list.setAttribute('data-glide', '')
        render()
        return
      }
      const zeta = 1 - 0.55 * bounce
      const k = 520
      const direction = Math.sign((t0 + t1) / 2 - (state.x0 + state.x1) / 2)
      const lead = k * (1 + 0.9 * stretch)
      const trail = k * (1 - 0.5 * stretch)
      const k0 = direction < 0 ? lead : direction > 0 ? trail : k
      const k1 = direction > 0 ? lead : direction < 0 ? trail : k
      const steps = Math.ceil(dt / (1 / 240))
      const h = dt / steps
      for (let i = 0; i < steps; i++) {
        state.v0 += (-k0 * (state.x0 - t0) - 2 * zeta * Math.sqrt(k0) * state.v0) * h
        state.x0 += state.v0 * h
        state.v1 += (-k1 * (state.x1 - t1) - 2 * zeta * Math.sqrt(k1) * state.v1) * h
        state.x1 += state.v1 * h
      }
      render()
      const busy =
        Math.abs(state.x0 - t0) > 0.05 ||
        Math.abs(state.x1 - t1) > 0.05 ||
        Math.abs(state.v0) > 0.5 ||
        Math.abs(state.v1) > 0.5
      if (busy) raf = requestAnimationFrame(tick)
      else {
        state.x0 = t0
        state.x1 = t1
        render()
      }
    }

    const update = (animate = true) => {
      measure()
      if (!animate) state.ready = false
      if (!raf) {
        last = 0
        raf = requestAnimationFrame(tick)
      }
    }
    api.current = update

    // Layout changes (resize, web font swap, the My Trip count badge) snap
    // the pill to the new geometry instead of animating.
    const resize = new ResizeObserver(() => update(false))
    resize.observe(list)
    list.querySelectorAll('a').forEach((a) => resize.observe(a))
    document.fonts?.ready.then(() => update(false)).catch(() => {})
    update(false)

    return () => {
      cancelAnimationFrame(raf)
      resize.disconnect()
      api.current = null
    }
  }, [listRef, bounce, stretch, enabled])

  useEffect(() => {
    api.current?.(true)
  }, [activeKey])
}
