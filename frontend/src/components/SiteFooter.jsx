import { Compass } from '@phosphor-icons/react'
import DataCredit from './DataCredit.jsx'

const REPO_URL = 'https://github.com/rohitvishwaa-ops/TripWise'
const API_DOCS_URL = 'https://tripwise-backend-3w5x.onrender.com/docs'

function External({ href, children }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
      <span className="visually-hidden"> (opens in a new tab)</span>
    </a>
  )
}

export default function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="site-footer__inner">
        <div className="site-footer__brand">
          <a href="#landing" className="brand">
            <span className="brand__mark" aria-hidden="true">
              <Compass size={20} weight="duotone" />
            </span>
            <span className="brand__name">TripWise</span>
          </a>
          <p className="site-footer__tagline">Real places, arranged into days you can change.</p>
        </div>
        <nav className="site-footer__nav" aria-label="Footer">
          <ul>
            <li><a href="#explore">Explore</a></li>
            <li><a href="#plan">Plan a trip</a></li>
            <li><a href="#trip">My Trip</a></li>
          </ul>
          <ul>
            <li><External href={REPO_URL}>Source on GitHub</External></li>
            <li><External href={API_DOCS_URL}>API documentation</External></li>
          </ul>
        </nav>
      </div>
      <div className="site-footer__credits">
        <DataCredit />
        <p>
          Destination photos from <External href="https://www.wikipedia.org/">Wikipedia</External> and{' '}
          <External href="https://commons.wikimedia.org/">Wikimedia Commons</External>. Globe outline from{' '}
          <External href="https://www.naturalearthdata.com/">Natural Earth</External>.
        </p>
      </div>
    </footer>
  )
}
