import { useEffect, useState } from 'react'

// Real destination photos from Wikipedia's public REST API (no key, CORS
// enabled). Only the lead image of the city's own article is used; if the
// name is ambiguous (disambiguation page), has no image, or the request
// fails, callers show a styled placeholder instead. Cached per page session.

const SUMMARY_URL = 'https://en.wikipedia.org/api/rest_v1/page/summary/'
const COMMONS_API = 'https://commons.wikimedia.org/w/api.php'
const results = new Map() // name -> image | null
const pending = new Map() // name -> Promise
// v2 adds the 1920px `xlarge` size used by full-bleed images.
const STORAGE_KEY = 'tripwise.destination-images.v2'

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

export function addressCity(address) {
  const parts = address
    ?.split(',')
    .map((part) => part.trim())
    .filter(Boolean)
  if (!parts?.length) return undefined
  // Geoapify addresses end with country and may include a postal code.
  // Prefer the named locality immediately before the country.
  const named = parts.filter((part) => /[A-Za-z]/.test(part) && !/^\d[\d -]*$/.test(part))
  const locality = named.length > 1 ? named.at(-2) : named.at(-1)
  return locality?.replace(/\s+\d[\d -]*$/, '').trim() || locality
}

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
  if (res.ok) {
    const summary = await res.json()
    if (summary.type === 'standard' && summary.thumbnail) {
      return {
        xlarge: sizedUrl(summary, 1920),
        large: sizedUrl(summary, 1280),
        small: sizedUrl(summary, 500),
        pageUrl: summary.content_urls?.desktop?.page ?? null,
        title: summary.title,
        creditLabel: 'Photo: Wikipedia',
      }
    }
  }

  // Generic place names often have no article. Search Commons for a real
  // destination image before showing the quiet initial fallback.
  const params = new URLSearchParams({
    action: 'query',
    generator: 'search',
    gsrsearch: name,
    gsrnamespace: '6',
    gsrlimit: '1',
    prop: 'imageinfo',
    iiprop: 'url|extmetadata',
    iiurlwidth: '960',
    format: 'json',
    origin: '*',
  })
  const commons = await fetch(`${COMMONS_API}?${params}`)
  if (!commons.ok) return null
  const data = await commons.json()
  const page = Object.values(data.query?.pages ?? {})[0]
  const info = page?.imageinfo?.[0]
  if (!info?.thumburl && !info?.url) return null
  return {
    large: info.thumburl ?? info.url,
    small: info.thumburl ?? info.url,
    pageUrl: info.descriptionurl ?? null,
    title: page.title,
    creditLabel: 'Photo: Wikimedia Commons',
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

export function useDestinationImage(name, fallbackName = '') {
  const key = name?.trim() || ''
  const fallbackKey = fallbackName?.trim() || ''
  const [loaded, setLoaded] = useState({ key: '', image: null })

  useEffect(() => {
    if (!key || (results.has(key) && results.get(key))) return undefined
    let cancelled = false
    load(key).then((image) => {
      if (image || !fallbackKey || fallbackKey === key) {
        if (!cancelled) setLoaded({ key, image })
        return
      }
      load(fallbackKey).then((fallbackImage) => {
        if (!cancelled) setLoaded({ key, image: fallbackImage })
      })
    })
    return () => {
      cancelled = true
    }
  }, [key, fallbackKey])

  if (!key) return null
  if (results.has(key) && results.get(key)) return results.get(key)
  return loaded.key === key ? loaded.image : null
}
