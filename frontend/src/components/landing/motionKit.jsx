/*
  Small Motion (motion/react) building blocks for the landing page. Pointer
  physics run on motion values, outside React state, so moving the cursor
  never re-renders the tree. Every effect collapses to static when the visitor
  prefers reduced motion (MotionConfig reducedMotion="user" in LandingView,
  plus explicit checks for the pointer effects).
*/
import { motion, useMotionValue, useReducedMotion, useSpring, useTransform } from 'motion/react'

const EASE = [0.16, 1, 0.3, 1]

/** Headline whose words rise out of a mask, one after another. */
export function RevealHeadline({ lines, className, id }) {
  const reduce = useReducedMotion()
  let index = 0
  return (
    <h1 id={id} className={className}>
      <span className="visually-hidden">{lines.map((l) => l.text).join(' ')}</span>
      <span aria-hidden="true">
        {lines.map((line) => (
          <span key={line.text} className={`reveal-line ${line.className ?? ''}`}>
            {line.text.split(' ').map((word, w) => {
              const delay = 0.12 + index++ * 0.08
              return (
                <span key={word + delay}>
                {w > 0 && ' '}
                <span className="reveal-word">
                  <motion.span
                    className="reveal-word__inner"
                    initial={reduce ? false : { y: '110%' }}
                    animate={{ y: '0%' }}
                    transition={{ duration: 0.9, delay, ease: EASE }}
                  >
                    {word}
                  </motion.span>
                </span>
                </span>
              )
            })}
          </span>
        ))}
      </span>
    </h1>
  )
}

/** Fades and lifts its children in once they enter the viewport. */
export function Reveal({ as = 'div', delay = 0, y = 28, className, children, ...rest }) {
  const reduce = useReducedMotion()
  const Tag = motion[as]
  return (
    <Tag
      className={className}
      initial={reduce ? false : { opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.25 }}
      transition={{ duration: 0.8, delay, ease: EASE }}
      {...rest}
    >
      {children}
    </Tag>
  )
}

/** Link that leans toward the cursor and springs back; presses in on tap. */
export function MagneticLink({ className, children, strength = 0.28, ...rest }) {
  const reduce = useReducedMotion()
  const x = useMotionValue(0)
  const y = useMotionValue(0)
  const sx = useSpring(x, { stiffness: 220, damping: 18, mass: 0.4 })
  const sy = useSpring(y, { stiffness: 220, damping: 18, mass: 0.4 })

  const onPointerMove = (event) => {
    if (reduce || event.pointerType !== 'mouse') return
    const box = event.currentTarget.getBoundingClientRect()
    x.set((event.clientX - (box.left + box.width / 2)) * strength)
    y.set((event.clientY - (box.top + box.height / 2)) * strength)
  }
  const reset = () => {
    x.set(0)
    y.set(0)
  }

  return (
    <motion.a
      className={className}
      style={{ x: sx, y: sy }}
      onPointerMove={onPointerMove}
      onPointerLeave={reset}
      whileTap={reduce ? undefined : { scale: 0.97 }}
      {...rest}
    >
      {children}
    </motion.a>
  )
}

/** Card that tilts in 3D toward the cursor, with a soft moving glare. */
export function TiltCard({ className, children, max = 9, ...rest }) {
  const reduce = useReducedMotion()
  const px = useMotionValue(0.5)
  const py = useMotionValue(0.5)
  const spring = { stiffness: 160, damping: 18, mass: 0.5 }
  const rotateX = useSpring(useTransform(py, [0, 1], [max, -max]), spring)
  const rotateY = useSpring(useTransform(px, [0, 1], [-max, max]), spring)
  const glareX = useTransform(px, [0, 1], ['0%', '100%'])
  const glareY = useTransform(py, [0, 1], ['0%', '100%'])

  const onPointerMove = (event) => {
    if (reduce || event.pointerType !== 'mouse') return
    const box = event.currentTarget.getBoundingClientRect()
    px.set((event.clientX - box.left) / box.width)
    py.set((event.clientY - box.top) / box.height)
  }
  const reset = () => {
    px.set(0.5)
    py.set(0.5)
  }

  return (
    <motion.a
      className={className}
      style={{ rotateX, rotateY, transformPerspective: 900, '--glare-x': glareX, '--glare-y': glareY }}
      onPointerMove={onPointerMove}
      onPointerLeave={reset}
      whileTap={reduce ? undefined : { scale: 0.98 }}
      {...rest}
    >
      {children}
    </motion.a>
  )
}
