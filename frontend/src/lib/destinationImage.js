import { useEffect, useState } from 'react'

// Real destination photos from Wikipedia's public REST API (no key, CORS
// enabled). Only the lead image of the city's own article is used; if the
// name is ambiguous (disambiguation page), has no image, or the request
// fails, callers show a styled placeholder instead. Cached per page session.

const SUMMARY_URL = 'https://en.wikipedia.org/api/rest_v1/page/summary/'
const results = new Map() // name -> image | null
const pending = new Map() // name -> Promise
const STORAGE_KEY = 'tripwise.destination-images.v1'

function readStored() {
  try {
    return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '{}')
  } catch {
    return {}
  }
}

function storeResult(name, image) {
  try {
    const stored = readStored()
    stored[name] = image
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(stored))
  } catch {
    // Storage can be unavailable in private browsing; memory caching still works.
  }
}

// Wikimedia only serves thumbnails at standard widths (others return 400).
const STANDARD_WIDTHS = [250, 330, 500, 960, 1280, 1920]

function sizedUrl(summary, width) {
  const thumb = summary.thumbnail?.source
  if (!thumb) return null
  const original = summary.originalimage?.width ?? 0
  // Thumbnail URLs embed their width ("/330px-"). Pick a standard width that
  // is smaller than the original (Wikimedia does not upscale).
  const target = STANDARD_WIDTHS.filter((w) => w <= width && (!original || w < original)).pop()
  return target ? thumb.replace(/\/\d+px-/, `/${target}px-`) : thumb
}

async function fetchImage(name) {
  const res = await fetch(SUMMARY_URL + encodeURIComponent(name.replaceAll(' ', '_')), {
    headers: { Accept: 'application/json' },
  })
  if (!res.ok) return null
  const summary = await res.json()
  if (summary.type !== 'standard' || !summary.thumbnail) return null
  return {
    large: sizedUrl(summary, 1280),
    small: sizedUrl(summary, 500),
    pageUrl: summary.content_urls?.desktop?.page ?? null,
    title: summary.title,
  }
}

function load(name) {
  if (results.has(name)) return Promise.resolve(results.get(name))
  const stored = readStored()
  if (Object.hasOwn(stored, name)) {
    results.set(name, stored[name])
    return Promise.resolve(stored[name])
  }
  if (!pending.has(name)) {
    pending.set(
      name,
      fetchImage(name)
        .catch(() => null)
        .then((image) => {
          results.set(name, image)
          storeResult(name, image)
          pending.delete(name)
          return image
        }),
    )
  }
  return pending.get(name)
}

export function useDestinationImage(name) {
  const key = name?.trim() || ''
  const [loaded, setLoaded] = useState({ key: '', image: null })

  useEffect(() => {
    if (!key || results.has(key)) return undefined
    let cancelled = false
    load(key).then((image) => {
      if (!cancelled) setLoaded({ key, image })
    })
    return () => {
      cancelled = true
    }
  }, [key])

  if (!key) return null
  if (results.has(key)) return results.get(key)
  return loaded.key === key ? loaded.image : null
}
