/*
  "How it works" as a route: a line draws down the page with scroll (Motion
  useScroll) and each step lights up as the line reaches it. The heading stays
  pinned beside the steps on wide screens.
*/
import { useRef } from 'react'
import { motion, useReducedMotion, useScroll, useSpring } from 'motion/react'
import { BookmarkSimple, MagnifyingGlass, NotePencil, Path } from '@phosphor-icons/react'

const STEPS = [
  {
    icon: MagnifyingGlass,
    title: 'Explore',
    body: 'Search a city, coordinates or your location. Filter real places by category, radius and count.',
  },
  {
    icon: BookmarkSimple,
    title: 'Save',
    body: 'Keep the places you like in My Trip. The list is stored, so it survives a refresh.',
  },
  {
    icon: Path,
    title: 'Plan',
    body: 'Pick one city or a route, the days, a pace and your interests. Nearby stops become days.',
  },
  {
    icon: NotePencil,
    title: 'Edit',
    body: 'Reorder stops, move them between days, add notes or regenerate one day. Changes save at once.',
  },
]

export default function Journey() {
  const ref = useRef(null)
  const reduce = useReducedMotion()
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start 75%', 'end 55%'] })
  const progress = useSpring(scrollYProgress, { stiffness: 120, damping: 26, mass: 0.4 })

  return (
    <section className="home-section journey" aria-labelledby="journey-title">
      <div className="journey__head">
        <h2 id="journey-title" className="home-section__title">From a city name to a plan you can change.</h2>
      </div>
      <div ref={ref} className="journey__route">
        <span className="journey__track" aria-hidden="true">
          <motion.span className="journey__fill" style={{ scaleY: reduce ? 1 : progress }} />
        </span>
        <ol className="journey__steps">
        {STEPS.map(({ icon: Icon, title, body }) => (
          <motion.li
            key={title}
            className="journey__step"
            initial={reduce ? false : { opacity: 0.25 }}
            whileInView={{ opacity: 1 }}
            viewport={{ amount: 0.9, margin: '0px 0px -20% 0px' }}
            transition={{ duration: 0.5 }}
          >
            <span className="journey__marker" aria-hidden="true">
              <Icon size={20} weight="duotone" />
            </span>
            <h3 className="journey__title">{title}</h3>
            <p className="journey__body">{body}</p>
          </motion.li>
        ))}
        </ol>
      </div>
    </section>
  )
}
