import { ArrowRight } from '@phosphor-icons/react'
import { MotionConfig } from 'motion/react'
import ScrollExpand from './reactbits/ScrollExpand.jsx'
import CountUp from './reactbits/CountUp.jsx'
import HeroSection from './landing/HeroSection.jsx'
import Journey from './landing/Journey.jsx'
import PacePreview from './landing/PacePreview.jsx'
import DestinationRail from './landing/DestinationRail.jsx'
import { MagneticLink, Reveal } from './landing/motionKit.jsx'
import { useDestinationImage } from '../lib/destinationImage.js'
import { useSmoothScroll } from './fx/useSmoothScroll.js'
import './landing.css'

const STATS = [
  { value: 10, label: 'cities in one route' },
  { value: 30, label: 'days per trip' },
  { value: 9, label: 'place categories' },
  { value: 50, suffix: 'km', label: 'search radius' },
]

function PlanTripLink({ className = '' }) {
  return (
    <MagneticLink className={`btn btn--primary home-btn ${className}`} href="#plan">
      Plan a trip <ArrowRight aria-hidden="true" size={18} weight="bold" />
    </MagneticLink>
  )
}

export default function LandingView() {
  const expandImage = useDestinationImage('Cinque Terre')
  useSmoothScroll()

  return (
    <MotionConfig reducedMotion="user">
      <div className="home">
        <HeroSection />

        <section className="home-expand" aria-labelledby="home-route-title">
          <ScrollExpand
            useWindowScroll
            src={expandImage?.xlarge || expandImage?.large || undefined}
            alt=""
            title={<span className="home-expand__title">One city, or ten.</span>}
            startWidth={46}
            startHeight={56}
            startRadius={20}
            endRadius={0}
            mediaZoom={1.25}
            scrollDistance={1}
            holdDistance={0.3}
            overlayScrim={0.6}
            smoothing={0}
          >
            <div className="home-expand__overlay">
              <h2 id="home-route-title" className="home-expand__heading">Plan the whole route in one go.</h2>
              <p className="home-expand__body">
                Line up to ten cities in travel order, give each its days, and TripWise adds a travel step between them.
              </p>
              <PlanTripLink />
            </div>
            {expandImage?.pageUrl && (
              <a className="image-credit home-expand__credit" href={expandImage.pageUrl} target="_blank" rel="noopener noreferrer">
                {expandImage.creditLabel ?? 'Photo: Wikipedia'}
                <span className="visually-hidden"> (opens in a new tab)</span>
              </a>
            )}
          </ScrollExpand>
        </section>

        <Journey />

        <PacePreview />

        <DestinationRail />

        <section className="home-section" aria-label="TripWise in numbers">
          <Reveal as="dl" className="home-stats">
            {STATS.map((stat) => (
              <div key={stat.label} className="home-stat">
                <dt className="home-stat__label">{stat.label}</dt>
                <dd className="home-stat__value">
                  <span className="visually-hidden">{stat.value} {stat.suffix ?? ''}</span>
                  <span aria-hidden="true">
                    <CountUp to={stat.value} duration={1.6} />
                    {stat.suffix && <span className="home-stat__unit">{stat.suffix}</span>}
                  </span>
                </dd>
              </div>
            ))}
          </Reveal>
        </section>

        <Reveal as="section" className="home-section home-cta" aria-labelledby="home-cta-title">
          <h2 id="home-cta-title" className="home-cta__title">Start with a city. Leave with a plan.</h2>
          <div className="home-actions home-cta__actions">
            <PlanTripLink />
            <a className="btn btn--ghost home-btn" href="#explore">Explore places</a>
          </div>
        </Reveal>
      </div>
    </MotionConfig>
  )
}
