import { useRef } from 'react'
import { CheckCircle, MapPin } from '@phosphor-icons/react'
import { useSpotlight } from './fx/useSpotlight.js'
import { categoryLabels, formatCoordinates, placeName } from '../lib/format.js'

export default function PlaceCard({ place, index, saved, onOpen }) {
  const tags = categoryLabels(place.categories)
  const ref = useRef(null)
  useSpotlight(ref)
  return (
    <li ref={ref} className="place-card spot" style={{ '--i': Math.min(index, 12) }}>
      {tags.length > 0 && (
        <ul className="tags" role="list" aria-label="Categories">
          {tags.map((tag) => (
            <li key={tag} className="tag">
              {tag}
            </li>
          ))}
        </ul>
      )}
      <h3 className="place-card__title">
        <button type="button" className="stretched" onClick={() => onOpen(place)}>
          {placeName(place)}
        </button>
      </h3>
      {place.address && <p className="place-card__address">{place.address}</p>}
      <div className="place-card__foot">
        <span className="coords-text">
          <MapPin aria-hidden="true" size={14} weight="fill" />
          {formatCoordinates(place.latitude, place.longitude)}
        </span>
        {saved && (
          <span className="saved-badge">
            <CheckCircle aria-hidden="true" size={16} weight="fill" />
            In My Trip
          </span>
        )}
      </div>
    </li>
  )
}

export function PlaceCardSkeleton({ count = 6 }) {
  return Array.from({ length: count }, (_, i) => (
    <li key={i} className="place-card place-card--skeleton" aria-hidden="true">
      <span className="sk sk--tag" />
      <span className="sk sk--title" />
      <span className="sk sk--line" />
      <span className="sk sk--line sk--short" />
    </li>
  ))
}
