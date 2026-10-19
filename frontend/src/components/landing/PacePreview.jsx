/*
  "Your pace, your interests" as a working preview. Picking a pace and
  interests rebuilds a sample Lisbon day with the same rules the planner uses:
  stops per day from the pace (2 / 3 / up to 5), interests taken in the order
  chosen, and the backend's Morning / Afternoon / Evening spread
  (planner.slot_labels). The button opens the real planner with these choices.
*/
import { useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { ArrowRight } from '@phosphor-icons/react'
import { INTERESTS, PACES } from '../../lib/planOptions.js'
import { planLink } from '../../state/useHashRoute.js'
import { PREVIEW_CITY, PREVIEW_POOL } from './cities.js'
import { Reveal } from './motionKit.jsx'

const STOPS = { relaxed: 2, balanced: 3, packed: 5 }
const SLOTS = ['Morning', 'Afternoon', 'Evening']
// With no interests the planner falls back to general sightseeing.
const DEFAULT_ORDER = ['history', 'culture', 'food', 'nature']
const EASE = [0.16, 1, 0.3, 1]

// Mirrors backend planner.slot_labels(count).
function slotLabel(i, count) {
  return SLOTS[Math.min(2, Math.floor((i * 3) / count))]
}

// Round-robin over the interests so a mixed choice gives a mixed day.
function pickStops(pace, interests) {
  const order = interests.length ? interests : DEFAULT_ORDER
  const count = STOPS[pace]
  const picked = []
  const used = new Set()
  for (let round = 0; picked.length < count && round < PREVIEW_POOL.length; round++) {
    for (const interest of order) {
      if (picked.length >= count) break
      const stop = PREVIEW_POOL.find((p) => !used.has(p.name) && p.tags.includes(interest))
      if (stop) {
        used.add(stop.name)
        picked.push({ ...stop, interest })
      }
    }
  }
  for (const stop of PREVIEW_POOL) {
    if (picked.length >= count) break
    if (!used.has(stop.name)) picked.push({ ...stop, interest: stop.tags[0] })
  }
  return picked
}

const interestLabel = (value) => INTERESTS.find((i) => i.value === value)?.label ?? value

export default function PacePreview() {
  const reduce = useReducedMotion()
  const [pace, setPace] = useState('balanced')
  const [interests, setInterests] = useState(['food', 'history'])
  const stops = pickStops(pace, interests)

  const toggle = (value) =>
    setInterests((current) => (current.includes(value) ? current.filter((i) => i !== value) : [...current, value]))

  return (
    <section className="home-section home-tune" aria-labelledby="home-tune-title">
      <Reveal className="home-tune__copy">
        <p className="eyebrow">Your pace, your interests</p>
        <h2 id="home-tune-title" className="home-section__title">Days that fit the way you travel.</h2>
        <p className="home-section__lede">
          Try it here. Choose how full a day should be and what you care about, and the sample day changes the way your
          plan would.
        </p>

        <fieldset className="tune-group">
          <legend className="tune-group__legend">Pace</legend>
          <div className="tune-paces">
            {PACES.map((p) => (
              <button
                key={p.value}
                type="button"
                className="tune-pace"
                aria-pressed={pace === p.value}
                onClick={() => setPace(p.value)}
              >
                <span className="tune-pace__name">{p.label}</span>
                <span className="tune-pace__detail">{p.detail}</span>
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset className="tune-group">
          <legend className="tune-group__legend">Interests</legend>
          <div className="home-chips">
            {INTERESTS.map((i) => (
              <button
                key={i.value}
                type="button"
                className="home-chip"
                aria-pressed={interests.includes(i.value)}
                onClick={() => toggle(i.value)}
              >
                {i.label}
              </button>
            ))}
          </div>
        </fieldset>
      </Reveal>

      <Reveal className="home-tune__panel" delay={0.1}>
        <div className="tune-day__head">
          <p className="tune-day__title">{PREVIEW_CITY}, day 1</p>
          <p className="tune-day__meta">
            {stops.length} stops{interests.length ? `, ${interests.map(interestLabel).join(' and ')}` : ', general sightseeing'}
          </p>
        </div>
        <ol className="tune-day" aria-live="polite">
          <AnimatePresence initial={false} mode="popLayout">
            {stops.map((stop, i) => (
              <motion.li
                key={stop.name}
                layout={!reduce}
                className="tune-day__stop"
                initial={reduce ? false : { opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={reduce ? undefined : { opacity: 0, scale: 0.96 }}
                transition={{ duration: 0.35, ease: EASE }}
              >
                <span className="tune-day__slot">{slotLabel(i, stops.length)}</span>
                <span className="tune-day__name">{stop.name}</span>
                <span className="tune-day__tag">{interestLabel(stop.interest)}</span>
              </motion.li>
            ))}
          </AnimatePresence>
        </ol>
        <a className="btn btn--primary home-btn tune-cta" href={planLink({ cities: [PREVIEW_CITY], pace, interests })}>
          Plan {PREVIEW_CITY} like this <ArrowRight aria-hidden="true" size={18} weight="bold" />
        </a>
        <p className="tune-day__note">A preview. Your real plan uses live places near each other.</p>
      </Reveal>
    </section>
  )
}
