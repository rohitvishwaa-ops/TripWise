// Decorative topographic contour lines (static SVG, no WebGL, no animation
// loop). Lines are generated once from a fixed seed so every render matches.
// Every fifth line is an "index contour", drawn heavier as on survey maps.
// Colour comes from `currentColor`, so it follows the light/dark theme.

function rng(seed) {
  let s = seed >>> 0
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0
    return s / 2 ** 32
  }
}

// Closed smooth path through points (quadratic curves between midpoints).
function smoothClosed(points) {
  const mid = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
  const n = points.length
  const start = mid(points[n - 1], points[0])
  let d = `M${start[0].toFixed(1)} ${start[1].toFixed(1)}`
  for (let i = 0; i < n; i++) {
    const p = points[i]
    const m = mid(p, points[(i + 1) % n])
    d += `Q${p[0].toFixed(1)} ${p[1].toFixed(1)} ${m[0].toFixed(1)} ${m[1].toFixed(1)}`
  }
  return `${d}Z`
}

function hill({ cx, cy, rings, step, seed, squash = 0.72 }) {
  const rand = rng(seed)
  const waves = [2, 3, 5, 7].map((freq) => ({
    freq,
    amp: (0.16 / freq) * (0.6 + rand()),
    phase: rand() * Math.PI * 2,
    drift: (rand() - 0.5) * 0.18,
  }))
  const paths = []
  for (let k = 0; k < rings; k++) {
    const pts = []
    for (let a = 0; a < 72; a++) {
      const t = (a / 72) * Math.PI * 2
      let f = 0
      for (const w of waves) f += w.amp * Math.sin(w.freq * t + w.phase + k * w.drift)
      const r = (k + 1) * step * (1 + f)
      pts.push([cx + Math.cos(t) * r, cy + Math.sin(t) * r * squash])
    }
    paths.push({ d: smoothClosed(pts), index: (k + 1) % 5 === 0 })
  }
  return paths
}

const PATHS = [
  ...hill({ cx: 600, cy: 230, rings: 17, step: 24, seed: 7 }),
  ...hill({ cx: 170, cy: 410, rings: 6, step: 19, seed: 23 }),
]

export default function ContourField({ className = '' }) {
  return (
    <svg
      className={`contour-field ${className}`}
      viewBox="0 0 800 520"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
      focusable="false"
    >
      <g fill="none" stroke="currentColor" strokeLinejoin="round">
        {PATHS.map((p, i) => (
          <path key={i} d={p.d} strokeWidth={p.index ? 1.6 : 0.8} opacity={p.index ? 0.9 : 0.55} />
        ))}
      </g>
      <g className="contour-field__mark" transform="translate(600 230)">
        <circle r="5" />
        <path d="M-14 0H14M0 -14V14" />
      </g>
    </svg>
  )
}
