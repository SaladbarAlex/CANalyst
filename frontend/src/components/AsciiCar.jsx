import { useEffect, useRef } from 'react'

/* A small 3D car drawn in ASCII. The model is a cloud of surface points with
   normals and a tone offset (body, cabin, darker glass and tyres); each frame rotates it, projects
   it with a z-buffer and shades every cell by how directly it faces the
   light, the same idea as the classic spinning-donut demo. It only animates
   while visible, and holds one still frame for prefers-reduced-motion. */

const COLS = 60
const ROWS = 16
const SHADES = '.,-~:;=!*#$@'
const FPS = 12
const TURN_S = 6

function buildModel() {
  const pts = []
  const step = 0.07
  const range = (a, b) => {
    const out = []
    for (let v = a; v <= b + 1e-9; v += step) out.push(v)
    return out
  }
  // Axis-aligned box: x is length, y is height, z is width.
  const box = (x0, x1, y0, y1, z0, z1, skip = {}) => {
    for (const x of range(x0, x1)) for (const y of range(y0, y1)) {
      if (!skip.zn) pts.push([x, y, z0, 0, 0, -1])
      if (!skip.zp) pts.push([x, y, z1, 0, 0, 1])
    }
    for (const x of range(x0, x1)) for (const z of range(z0, z1)) {
      if (!skip.yn) pts.push([x, y0, z, 0, -1, 0])
      if (!skip.yp) pts.push([x, y1, z, 0, 1, 0])
    }
    for (const y of range(y0, y1)) for (const z of range(z0, z1)) {
      if (!skip.xn) pts.push([x0, y, z, -1, 0, 0])
      if (!skip.xp) pts.push([x1, y, z, 1, 0, 0])
    }
  }
  // Lower body and cabin.
  box(-2.0, 2.0, 0.3, 0.85, -0.85, 0.85)
  box(-1.15, 0.55, 0.85, 1.4, -0.75, 0.75, { yn: true, xp: true })
  // Sloped windshield from the cabin roof down to the hood.
  const n = Math.hypot(0.55, 0.65)
  for (const t of range(0, 1)) for (const z of range(-0.75, 0.75)) {
    pts.push([0.55 + 0.65 * t, 1.4 - 0.55 * t, z, 0.55 / n, 0.65 / n, 0, -0.45]) // glass reads darker
  }
  // Wheels: tread and both side faces.
  for (const wx of [-1.3, 1.3]) for (const wz of [-0.85, 0.85]) {
    const r = 0.34
    for (let a = 0; a < Math.PI * 2; a += 0.18) {
      const c = Math.cos(a)
      const s = Math.sin(a)
      for (const dz of range(-0.16, 0.16)) pts.push([wx + r * c, 0.34 + r * s, wz + dz, c, s, 0, -0.6])
      for (let rr = 0.08; rr < r; rr += 0.08) {
        pts.push([wx + rr * c, 0.34 + rr * s, wz + Math.sign(wz) * 0.17, 0, 0, Math.sign(wz), rr < 0.15 ? 0.2 : -0.6])
      }
    }
  }
  return pts
}

const MODEL = buildModel()

function render(angle) {
  const out = Array.from({ length: ROWS }, () => Array(COLS).fill(' '))
  const zbuf = Array.from({ length: ROWS }, () => Array(COLS).fill(-Infinity))
  const ca = Math.cos(angle)
  const sa = Math.sin(angle)
  const tilt = 0.28 // look down at the car a little
  const ct = Math.cos(tilt)
  const st = Math.sin(tilt)
  const light = [-0.42, 0.62, -0.66]
  const dist = 7
  const sx = 54 // columns per unit at unit depth
  const sy = 27 // rows are about twice as tall as columns are wide
  for (const [px, py, pz, nx, ny, nz, tone = 0] of MODEL) {
    // Spin about the vertical axis, then tilt toward the viewer.
    let x = px * ca + pz * sa
    let z = -px * sa + pz * ca
    let y = py - 0.7
    const y2 = y * ct + z * st
    z = -y * st + z * ct
    y = y2
    let mx = nx * ca + nz * sa
    let mz = -nx * sa + nz * ca
    const my = ny * ct + mz * st
    mz = -ny * st + mz * ct
    if (mz > 0.15) continue // facing away from the viewer
    const ooz = 1 / (dist + z)
    const col = Math.round(COLS / 2 + sx * x * ooz)
    const row = Math.round(ROWS / 2 - sy * y * ooz)
    if (row < 0 || row >= ROWS || col < 0 || col >= COLS || ooz <= zbuf[row][col]) continue
    zbuf[row][col] = ooz
    const lum = Math.max(-1, Math.min(1, mx * light[0] + my * light[1] + mz * light[2] + tone))
    const level = Math.round(((lum + 1) / 2) ** 1.4 * (SHADES.length - 1))
    out[row][col] = SHADES[Math.max(0, Math.min(SHADES.length - 1, level))]
  }
  return out.map((r) => r.join('')).join('\n')
}

export default function AsciiCar({ className = '' }) {
  const ref = useRef(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return undefined
    const still = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    el.textContent = render(-0.7)
    if (still) return undefined

    let visible = true
    let frame = 0
    let last = 0
    const start = performance.now()
    const tick = (now) => {
      frame = requestAnimationFrame(tick)
      if (!visible || document.hidden || now - last < 1000 / FPS) return
      last = now
      el.textContent = render(-0.7 + ((now - start) / 1000) * (Math.PI * 2 / TURN_S))
    }
    const io = 'IntersectionObserver' in window
      ? new IntersectionObserver(([entry]) => { visible = entry.isIntersecting })
      : null
    io?.observe(el)
    frame = requestAnimationFrame(tick)
    return () => { cancelAnimationFrame(frame); io?.disconnect() }
  }, [])

  return <pre ref={ref} className={`ascii-car ${className}`} aria-hidden="true" />
}
