/*
  Destination ideas as a horizontal scroll-snap rail (native scrolling, so
  touch, trackpad and keyboard all work) with 3D tilt cards and previous/next
  buttons for mouse users.
*/
import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight } from '@phosphor-icons/react'
import DestinationImage from '../plan/DestinationImage.jsx'
import { TiltCard } from './motionKit.jsx'
import { RAIL_CITIES } from './cities.js'

export default function DestinationRail() {
  const rail = useRef(null)
  const [edges, setEdges] = useState({ start: true, end: false })

  useEffect(() => {
    const el = rail.current
    const update = () => {
      setEdges({ start: el.scrollLeft < 8, end: el.scrollLeft + el.clientWidth > el.scrollWidth - 8 })
    }
    update()
    el.addEventListener('scroll', update, { passive: true })
    const observer = new ResizeObserver(update)
    observer.observe(el)
    return () => {
      el.removeEventListener('scroll', update)
      observer.disconnect()
    }
  }, [])

  const step = (direction) => {
    const el = rail.current
    const card = el.querySelector('.rail-card')
    const amount = card ? card.getBoundingClientRect().width + 16 : el.clientWidth * 0.8
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    el.scrollBy({ left: direction * amount, behavior: reduce ? 'auto' : 'smooth' })
  }

  return (
    <section className="home-section rail" aria-labelledby="rail-title">
      <div className="rail__head">
        <h2 id="rail-title" className="home-section__title">Somewhere to start.</h2>
        <div className="rail__controls">
          <button type="button" className="rail__btn" onClick={() => step(-1)} disabled={edges.start} aria-label="Previous destinations">
            <ArrowLeft size={18} weight="bold" aria-hidden="true" />
          </button>
          <button type="button" className="rail__btn" onClick={() => step(1)} disabled={edges.end} aria-label="Next destinations">
            <ArrowRight size={18} weight="bold" aria-hidden="true" />
          </button>
        </div>
      </div>
      <ul ref={rail} className="rail__track">
        {RAIL_CITIES.map(({ name, note }) => (
          <li key={name} className="rail__item">
            <TiltCard className="rail-card" href="#explore">
              <DestinationImage city={name} size="large" alt="" />
              <span className="rail-card__glare" aria-hidden="true" />
              <span className="rail-card__text">
                <span className="rail-card__city">{name}</span>
                <span className="rail-card__note">{note}</span>
              </span>
            </TiltCard>
          </li>
        ))}
      </ul>
    </section>
  )
}
