import { useState } from 'react'
import { useDestinationImage } from '../../lib/destinationImage.js'

/**
 * A real photo of the destination (Wikipedia lead image) or, when none is
 * available, a quiet placeholder with the city's initial. Decorative: the
 * city name is always shown as text next to or over it. With `credit`, a
 * "Photo: Wikipedia" link is shown, but only while a photo is visible.
 */
export default function DestinationImage({
  city,
  size = 'small',
  className = '',
  priority = false,
  credit = false,
  fallback,
  alt = '',
}) {
  const image = useDestinationImage(city, fallback)
  const [failed, setFailed] = useState(false)
  const src = image?.[size]
  const showing = Boolean(src) && !failed

  return (
    <>
      <div className={`dest-image ${className}`} data-has-image={showing ? 'true' : 'false'}>
        {showing ? (
          <img
            src={src}
            alt={alt}
            loading={priority ? 'eager' : 'lazy'}
            fetchPriority={priority ? 'high' : undefined}
            decoding="async"
            onError={() => setFailed(true)}
          />
        ) : (
          <span className="dest-image__initial" aria-hidden="true">
            {city?.trim()?.[0]?.toUpperCase() ?? ''}
          </span>
        )}
      </div>
      {credit && showing && image.pageUrl && (
        <a className="image-credit" href={image.pageUrl} target="_blank" rel="noopener noreferrer">
          {image.creditLabel ?? 'Photo: Wikipedia'}
          <span className="visually-hidden"> article about {image.title} (opens in a new tab)</span>
        </a>
      )}
    </>
  )
}
