import DestinationImage from './plan/DestinationImage.jsx'

export default function LandingView() {
  return (
    <section className="landing" aria-labelledby="landing-title">
      <div className="landing__image"><DestinationImage city="Kyoto" size="large" priority alt="A destination view from Kyoto" /></div>
      <div className="landing__content">
        <p className="eyebrow">Travel, thoughtfully arranged</p>
        <h1 id="landing-title">Go somewhere<br /><em>worth remembering.</em></h1>
        <p className="landing__lede">Discover places with context, shape a day-by-day plan, and keep the whole journey close at hand.</p>
        <div className="landing__actions">
          <a className="button button--primary" href="#explore">Start exploring</a>
          <a className="button button--quiet" href="#plan">Plan a trip</a>
        </div>
        <p className="landing__note">No account required. Your guest trip stays in this browser.</p>
      </div>
    </section>
  )
}
