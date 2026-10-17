import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

// Leaflet stays isolated in this component so the rest of the app remains a
// normal React surface. Circle markers avoid fragile image assets while still
// giving keyboard users a labelled, focusable map companion through the list.
export default function MapView({ places, selectedId, onSelect }) {
  const hostRef = useRef(null)
  const mapRef = useRef(null)
  const markersRef = useRef(new Map())

  useEffect(() => {
    const host = hostRef.current
    if (!host || mapRef.current) return undefined
    const map = L.map(host, { zoomControl: false, scrollWheelZoom: true })
    L.control.zoom({ position: 'bottomright' }).addTo(map)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map)
    map.setView([20, 0], 2)
    mapRef.current = map
    const markers = markersRef.current
    return () => {
      map.remove()
      markers.clear()
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    markersRef.current.forEach((marker) => marker.remove())
    markersRef.current.clear()
    const valid = places.filter((place) => Number.isFinite(place.latitude) && Number.isFinite(place.longitude))
    valid.forEach((place) => {
      const marker = L.circleMarker([place.latitude, place.longitude], {
        radius: place.id === selectedId ? 10 : 7,
        color: place.id === selectedId ? '#D96F56' : '#4263A8',
        fillColor: place.id === selectedId ? '#D96F56' : '#4263A8',
        fillOpacity: 0.9,
        weight: 3,
      })
        .addTo(map)
        .bindTooltip(place.name, { direction: 'top', offset: [0, -8] })
        .on('click', () => onSelect(place.id))
      markersRef.current.set(place.id, marker)
    })
    if (valid.length === 1) map.setView([valid[0].latitude, valid[0].longitude], 13)
    else if (valid.length > 1) map.fitBounds(L.latLngBounds(valid.map((place) => [place.latitude, place.longitude])), { padding: [36, 36], maxZoom: 13 })
  }, [places, selectedId, onSelect])

  useEffect(() => {
    const marker = markersRef.current.get(selectedId)
    if (!marker || !mapRef.current) return
    marker.setStyle({ radius: 10, color: '#D96F56', fillColor: '#D96F56' })
    marker.openTooltip()
    mapRef.current.panTo(marker.getLatLng(), { animate: true })
    markersRef.current.forEach((other, id) => {
      if (id !== selectedId) other.setStyle({ radius: 7, color: '#4263A8', fillColor: '#4263A8' })
    })
  }, [selectedId])

  return <div ref={hostRef} className="explore-map" role="region" aria-label="Map of matching attractions" />
}
