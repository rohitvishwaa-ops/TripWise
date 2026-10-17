/*
  Pointer-following spotlight for cards.

  Adapted from SpotlightCard by React Bits (https://reactbits.dev, free JS + CSS
  variant). Copyright (c) 2026 David Haz. MIT + Commons Clause License
  Condition v1.0; see https://github.com/DavidHDev/react-bits/blob/main/LICENSE.md

  Changes for TripWise: instead of wrapping children in extra elements, the hook
  only writes CSS custom properties (--spot-x, --spot-y, --spot-o) on the
  existing card, and the light is painted by CSS. This keeps the card markup,
  roles and test selectors unchanged. The smoothing, presence fade, proximity
  falloff, keyboard-focus tracking and reduced-motion behaviour follow the
  original. Effects run only for fine pointers or keyboard focus.
*/
import { useEffect } from 'react'

const clamp = (v, min, max) => Math.min(max, Math.max(min, v))

/** Attach the spotlight to one element; returns a cleanup function. */
export function attachSpotlight(root, { proximity = 64, smoothing = 0.3 } = {}) {
  if (!root || typeof window === 'undefined' || !window.matchMedia) return () => {}

  const fine = window.matchMedia('(hover: hover) and (pointer: fine)').matches
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const state = { x: 0, y: 0, presence: 0 }
  const pointer = { x: 0, y: 0, active: false }
  let focus = null
  let raf = 0
  let last = 0
  let alive = true

  const paint = () => {
    root.style.setProperty('--spot-x', `${state.x.toFixed(1)}px`)
    root.style.setProperty('--spot-y', `${state.y.toFixed(1)}px`)
    root.style.setProperty('--spot-o', state.presence.toFixed(3))
  }

  const tick = (now) => {
    raf = 0
    if (!alive) return
    const dt = clamp((now - last) / 1000, 0.001, 0.05)
    last = now
    const rect = root.getBoundingClientRect()
    let tx = state.x
    let ty = state.y
    let target = 0
    if (focus && root.contains(focus)) {
      const box = focus.getBoundingClientRect()
      tx = box.left + box.width / 2 - rect.left
      ty = box.top + box.height / 2 - rect.top
      target = 1
    } else if (pointer.active) {
      tx = pointer.x - rect.left
      ty = pointer.y - rect.top
      const gap = Math.hypot(
        Math.max(0, -tx, tx - rect.width),
        Math.max(0, -ty, ty - rect.height),
      )
      if (gap === 0) target = 1
      else if (proximity > 0) target = Math.max(0, 1 - gap / proximity) ** 2
    }
    if (state.presence < 0.02 && target > 0) {
      state.x = tx
      state.y = ty
    }
    const follow = reduce ? 1 : 1 - Math.exp(-dt / (0.015 + smoothing * 0.22))
    state.x += (tx - state.x) * follow
    state.y += (ty - state.y) * follow
    const fade = reduce ? 1 : 1 - Math.exp(-dt / (target > state.presence ? 0.1 : 0.32))
    state.presence += (target - state.presence) * fade
    if (Math.abs(target - state.presence) < 0.002) state.presence = target
    paint()
    const moving = Math.abs(tx - state.x) > 0.1 || Math.abs(ty - state.y) > 0.1
    if (moving || state.presence !== target) raf = requestAnimationFrame(tick)
  }

  const wake = () => {
    if (raf || !alive) return
    last = performance.now()
    raf = requestAnimationFrame(tick)
  }

  const onMove = (event) => {
    pointer.x = event.clientX
    pointer.y = event.clientY
    pointer.active = true
    if (state.presence > 0 || root.contains(event.target)) wake()
    else {
      // Cheap proximity check before waking the loop.
      const r = root.getBoundingClientRect()
      const gx = Math.max(0, r.left - event.clientX, event.clientX - r.right)
      const gy = Math.max(0, r.top - event.clientY, event.clientY - r.bottom)
      if (gx < proximity && gy < proximity) wake()
    }
  }
  const onOut = (event) => {
    if (event.relatedTarget) return
    pointer.active = false
    wake()
  }
  const onFocusIn = (event) => {
    if (!(event.target instanceof Element) || !event.target.matches(':focus-visible')) return
    focus = event.target
    wake()
  }
  const onFocusOut = (event) => {
    if (root.contains(event.relatedTarget)) return
    focus = null
    wake()
  }
  const onScroll = () => {
    if (pointer.active || state.presence > 0) wake()
  }

  if (fine) {
    window.addEventListener('pointermove', onMove, { passive: true })
    window.addEventListener('scroll', onScroll, { capture: true, passive: true })
    document.addEventListener('pointerout', onOut)
  }
  root.addEventListener('focusin', onFocusIn)
  root.addEventListener('focusout', onFocusOut)

  return () => {
    alive = false
    cancelAnimationFrame(raf)
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('scroll', onScroll, { capture: true })
    document.removeEventListener('pointerout', onOut)
    root.removeEventListener('focusin', onFocusIn)
    root.removeEventListener('focusout', onFocusOut)
    root.style.removeProperty('--spot-x')
    root.style.removeProperty('--spot-y')
    root.style.removeProperty('--spot-o')
  }
}

/** Spotlight on the element in `ref`. */
export function useSpotlight(ref, options) {
  const proximity = options?.proximity
  const smoothing = options?.smoothing
  useEffect(() => attachSpotlight(ref.current, { proximity, smoothing }), [ref, proximity, smoothing])
}

/** Spotlight on every element matching `selector` inside `ref`; re-attached when `key` changes. */
export function useSpotlightAll(ref, selector, key) {
  useEffect(() => {
    const cleanups = [...(ref.current?.querySelectorAll(selector) ?? [])].map((el) => attachSpotlight(el))
    return () => cleanups.forEach((fn) => fn())
  }, [ref, selector, key])
}
