// Attribution required by Geoapify (free plan) and OpenStreetMap, shown next
// to the place information it applies to and in the site footer.
export default function DataCredit({ className = '' }) {
  return (
    <p className={`data-credit ${className}`}>
      Powered by{' '}
      <a href="https://www.geoapify.com/" target="_blank" rel="noopener noreferrer">
        Geoapify
        <span className="visually-hidden"> (opens in a new tab)</span>
      </a>
      . Map data ©{' '}
      <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">
        OpenStreetMap contributors
        <span className="visually-hidden"> (opens in a new tab)</span>
      </a>
      .
    </p>
  )
}
