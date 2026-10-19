/*
  Interactive dotted globe for the landing hero (React Three Fiber + three.js).
  Land dots come from a precomputed bitset (globeDots.js, built from Natural
  Earth 110m land by scripts/build-globe-dots.mjs), so no map data is parsed
  in the browser.

  Renders on demand: a frame is drawn only while something moves (turning to a
  city, an arc drawing in, a pin pulsing, a drag). Idle, it costs nothing; off
  screen it stops entirely. Loaded lazily from LandingView and kept free of
  Motion (Framer) code: the two libraries own separate trees.
*/
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { DOT_COUNT, LAND_MASK } from './globeDots.js'

const DEG = Math.PI / 180
const TAU = Math.PI * 2

const PALETTE = {
  light: { ocean: '#EFE7DA', dots: '#20283A', pin: '#D96F56', arc: '#4263A8' },
  dark: { ocean: '#293246', dots: '#F7F3EB', pin: '#E8836B', arc: '#A9BCEB' },
}

function toVec(lat, lon, r = 1) {
  const la = lat * DEG
  const lo = lon * DEG
  return new THREE.Vector3(Math.cos(la) * Math.sin(lo) * r, Math.sin(la) * r, Math.cos(la) * Math.cos(lo) * r)
}

let landDotsCache = null
function landDots() {
  if (landDotsCache) return landDotsCache
  const bits = Uint8Array.from(atob(LAND_MASK), (c) => c.charCodeAt(0))
  const golden = Math.PI * (3 - Math.sqrt(5))
  const dots = []
  for (let i = 0; i < DOT_COUNT; i++) {
    if (!(bits[i >> 3] & (1 << (i & 7)))) continue
    const y = 1 - (i / (DOT_COUNT - 1)) * 2
    const r = Math.sqrt(1 - y * y)
    dots.push([Math.cos(golden * i) * r, y, Math.sin(golden * i) * r])
  }
  landDotsCache = dots
  return dots
}

function LandDots({ color }) {
  const ref = useRef(null)
  const dots = useMemo(() => landDots(), [])
  const geometry = useMemo(() => new THREE.CircleGeometry(0.0072, 6), [])

  useLayoutEffect(() => {
    const mesh = ref.current
    const o = new THREE.Object3D()
    dots.forEach(([x, y, z], i) => {
      o.position.set(x * 1.002, y * 1.002, z * 1.002)
      o.lookAt(x * 2, y * 2, z * 2)
      o.updateMatrix()
      mesh.setMatrixAt(i, o.matrix)
    })
    mesh.instanceMatrix.needsUpdate = true
  }, [dots])

  useEffect(() => () => geometry.dispose(), [geometry])

  return (
    <instancedMesh ref={ref} args={[geometry, undefined, dots.length]}>
      <meshBasicMaterial color={color} transparent opacity={0.62} />
    </instancedMesh>
  )
}

function slerpPath(from, to, segments = 96) {
  const a = toVec(from.lat, from.lon)
  const b = toVec(to.lat, to.lon)
  const angle = a.angleTo(b)
  const lift = Math.min(0.42, angle * 0.24)
  const points = []
  for (let i = 0; i <= segments; i++) {
    const t = i / segments
    const p =
      angle < 1e-4
        ? a.clone()
        : a
            .clone()
            .multiplyScalar(Math.sin((1 - t) * angle) / Math.sin(angle))
            .add(b.clone().multiplyScalar(Math.sin(t * angle) / Math.sin(angle)))
    points.push(p.multiplyScalar(1.004 + Math.sin(Math.PI * t) * lift))
  }
  return new THREE.CatmullRomCurve3(points)
}

// A tube along the great-circle path; the index draw range grows to "fly" it.
function FlightArc({ from, to, color, reduce }) {
  const geometry = useMemo(() => new THREE.TubeGeometry(slerpPath(from, to), 120, 0.0055, 6, false), [from, to])
  const progress = useRef(reduce ? 1 : 0)
  useEffect(() => () => geometry.dispose(), [geometry])
  useFrame((state, delta) => {
    if (progress.current < 1) {
      progress.current = Math.min(1, progress.current + Math.min(delta, 0.05) * 0.8)
      state.invalidate()
    }
    const eased = 1 - Math.pow(1 - progress.current, 3)
    geometry.setDrawRange(0, Math.floor((eased * geometry.index.count) / 3) * 3)
  })
  return (
    <mesh geometry={geometry}>
      <meshBasicMaterial color={color} />
    </mesh>
  )
}

function RouteLine({ from, to, color }) {
  const geometry = useMemo(() => new THREE.TubeGeometry(slerpPath(from, to, 64), 64, 0.0018, 4, false), [from, to])
  useEffect(() => () => geometry.dispose(), [geometry])
  return (
    <mesh geometry={geometry}>
      <meshBasicMaterial color={color} transparent opacity={0.28} depthWrite={false} />
    </mesh>
  )
}

const Z_AXIS = new THREE.Vector3(0, 0, 1)
const PULSE_SECONDS = 1.8
const PULSES = 3

function Pin({ city, focused, marked, color, onSelect, reduce }) {
  const position = useMemo(() => toVec(city.lat, city.lon, 1.006), [city])
  const quaternion = useMemo(() => new THREE.Quaternion().setFromUnitVectors(Z_AXIS, position.clone().normalize()), [position])
  const ring = useRef(null)
  const dot = useRef(null)
  const pulseStart = useRef(null)

  useEffect(() => {
    pulseStart.current = null
  }, [focused])

  useFrame((state, delta) => {
    const targetScale = focused ? 1.5 : marked ? 1.25 : 1
    const current = dot.current.scale.x
    const next = THREE.MathUtils.damp(current, targetScale, 8, Math.min(delta, 0.05))
    dot.current.scale.setScalar(next)
    if (Math.abs(next - targetScale) > 0.002) state.invalidate()

    ring.current.visible = false
    if (!focused || reduce) return
    if (pulseStart.current === null) pulseStart.current = state.clock.elapsedTime
    const elapsed = state.clock.elapsedTime - pulseStart.current
    if (elapsed > PULSE_SECONDS * PULSES) return
    const t = (elapsed % PULSE_SECONDS) / PULSE_SECONDS
    ring.current.visible = true
    ring.current.scale.setScalar(1 + t * 2.4)
    ring.current.material.opacity = (1 - t) * 0.7
    state.invalidate()
  })

  return (
    <group position={position} quaternion={quaternion}>
      <mesh
        onClick={(event) => {
          event.stopPropagation()
          onSelect()
        }}
        onPointerOver={(event) => {
          event.stopPropagation()
          document.body.style.cursor = 'pointer'
        }}
        onPointerOut={() => {
          document.body.style.cursor = ''
        }}
      >
        <circleGeometry args={[0.075, 16]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
      <mesh ref={dot} position-z={0.002}>
        <circleGeometry args={[0.022, 24]} />
        <meshBasicMaterial color={color} />
      </mesh>
      <mesh ref={ring} position-z={0.001} visible={false}>
        <ringGeometry args={[0.024, 0.032, 32]} />
        <meshBasicMaterial color={color} transparent depthWrite={false} />
      </mesh>
    </group>
  )
}

function shortestAngle(current, target) {
  return current + ((((target - current) % TAU) + TAU * 1.5) % TAU) - Math.PI
}

function Globe({ cities, focus, arcs, routeLines, marked, onSelect, colors, reduce, drag, invalidateRef }) {
  const group = useRef(null)
  const invalidate = useThree((state) => state.invalidate)
  const start = cities[focus]
  const rotation = useRef({ x: start.lat * DEG * 0.75, y: -start.lon * DEG })
  const target = useRef({ ...rotation.current })

  useEffect(() => {
    invalidateRef.current = invalidate
  }, [invalidate, invalidateRef])

  useEffect(() => {
    const city = cities[focus]
    if (!city) return
    target.current.x = city.lat * DEG * 0.75
    target.current.y = shortestAngle(rotation.current.y, -city.lon * DEG)
    if (reduce) rotation.current = { ...target.current }
    invalidate()
  }, [focus, cities, reduce, invalidate])

  useFrame((state, delta) => {
    const r = rotation.current
    const t = target.current
    const d = drag.current
    if (d.dx || d.dy) {
      t.y += d.dx * 0.0065
      t.x = THREE.MathUtils.clamp(t.x + d.dy * 0.0045, -1.05, 1.05)
      d.dx = 0
      d.dy = 0
    }
    const k = d.active || reduce ? 1 : 1 - Math.exp(-Math.min(delta, 0.05) * 3)
    r.x += (t.x - r.x) * k
    r.y += (t.y - r.y) * k
    group.current.rotation.set(r.x, r.y, 0)
    // 3e-4 rad is well under a pixel at this size, so stop there.
    if (Math.abs(t.x - r.x) > 3e-4 || Math.abs(t.y - r.y) > 3e-4) state.invalidate()
  })

  const markedSet = new Set(marked)

  return (
    <group ref={group}>
      {/* The ocean swallows clicks so pins on the far side cannot be picked. */}
      <mesh onClick={(event) => event.stopPropagation()}>
        <sphereGeometry args={[1, 64, 64]} />
        <meshBasicMaterial color={colors.ocean} />
      </mesh>
      <LandDots color={colors.dots} />
      {routeLines &&
        cities
          .slice(1)
          .map((city, i) => <RouteLine key={`${cities[i].name}-${city.name}`} from={cities[i]} to={city} color={colors.arc} />)}
      {arcs.map(({ from, to, key }) =>
        cities[from] && cities[to] ? (
          <FlightArc key={key} from={cities[from]} to={cities[to]} color={colors.arc} reduce={reduce} />
        ) : null,
      )}
      {cities.map((city, i) => (
        <Pin
          key={city.name}
          city={city}
          focused={i === focus}
          marked={markedSet.has(i)}
          color={colors.pin}
          reduce={reduce}
          onSelect={() => onSelect(i)}
        />
      ))}
    </group>
  )
}

function useThemeName() {
  const read = () => (document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light')
  const [theme, setTheme] = useState(read)
  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(read()))
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => observer.disconnect()
  }, [])
  return theme
}

/**
 * cities: [{ name, lat, lon }]; focus: index the globe turns to;
 * arcs: [{ from, to, key }] flight arcs (each draws in once, keyed);
 * routeLines: faint lines joining the cities in order; marked: indices to
 * emphasise (e.g. cities in a route).
 */
export default function HeroGlobe({ cities, focus, arcs = [], routeLines = false, marked = [], onSelect, onInteract, reduce }) {
  const wrap = useRef(null)
  const invalidateRef = useRef(null)
  const drag = useRef({ active: false, x: 0, y: 0, dx: 0, dy: 0, moved: false, id: null })
  const [visible, setVisible] = useState(true)
  const colors = PALETTE[useThemeName()]

  // Stop rendering entirely while the hero is off screen.
  useEffect(() => {
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { rootMargin: '120px' })
    observer.observe(wrap.current)
    return () => observer.disconnect()
  }, [])

  const onPointerDown = (event) => {
    const d = drag.current
    d.id = event.pointerId
    d.x = event.clientX
    d.y = event.clientY
    d.moved = false
  }
  const onPointerMove = (event) => {
    const d = drag.current
    if (d.id !== event.pointerId) return
    const dx = event.clientX - d.x
    const dy = event.clientY - d.y
    if (!d.moved) {
      if (Math.hypot(dx, dy) < 5) return
      // Only capture once it is clearly a drag, so plain clicks still reach the pins.
      d.moved = true
      d.active = true
      wrap.current.setPointerCapture(event.pointerId)
      wrap.current.dataset.dragging = ''
      onInteract?.()
    }
    d.dx += dx
    d.dy += dy
    d.x = event.clientX
    d.y = event.clientY
    invalidateRef.current?.()
  }
  const onPointerEnd = (event) => {
    const d = drag.current
    if (d.id !== event.pointerId) return
    d.id = null
    d.active = false
    delete wrap.current.dataset.dragging
  }

  return (
    <div
      ref={wrap}
      className="hero-globe"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerEnd}
      onPointerCancel={onPointerEnd}
      aria-hidden="true"
    >
      {/* `flat` turns off tone mapping so the flat brand colours render as specified. */}
      <Canvas
        flat
        dpr={[1, 2]}
        camera={{ position: [0, 0, 3.75], fov: 36 }}
        gl={{ antialias: true, alpha: true }}
        frameloop={visible ? 'demand' : 'never'}
      >
        <Globe
          cities={cities}
          focus={focus}
          arcs={arcs}
          routeLines={routeLines}
          marked={marked}
          onSelect={(i) => {
            onInteract?.()
            onSelect(i)
          }}
          colors={colors}
          reduce={reduce}
          drag={drag}
          invalidateRef={invalidateRef}
        />
      </Canvas>
    </div>
  )
}
