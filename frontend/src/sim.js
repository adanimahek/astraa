// Simplified 4-way intersection simulator (demo). Approaches: 0=N, 1=S, 2=E, 3=W. Phase 0 = N/S green, 1 = E/W green.
export const SCEN = {
  Low: [.07, .07, .07, .07], Medium: [.14, .14, .14, .14], High: [.22, .22, .22, .22],
  'Peak hour': [.32, .32, .12, .12],
}
export function rng(seed) {
  let a = seed
  return () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296 }
}
export function createSim(mode) {
  return { mode, cars: [[], [], [], []], phase: 0, next: 0, yellow: 0, green: 0, t: 0, wait: 0, spawned: 0, generatedSpawned: 0, scannedSpawned: 0, served: 0, ambN: 0, ambSum: 0, hist: [], lastH: 0 }
}
const queued = (sim, a) => sim.cars[a].filter((c) => c.d >= 0 && c.d < 130)
export function approachQueues(sim) {
  return {
    north: queued(sim, 0).length,
    south: queued(sim, 1).length,
    east: queued(sim, 2).length,
    west: queued(sim, 3).length,
  }
}
function decide(sim) {
  const cur = sim.phase * 2, oth = (1 - sim.phase) * 2
  const queues = approachQueues(sim)
  const groups = [
    queues.north + queues.south,
    queues.east + queues.west,
  ]
  const cq = groups[sim.phase]
  const oq = groups[1 - sim.phase]
  const ac = [cur, cur + 1].some((a) => sim.cars[a].some((c) => c.amb && c.d >= 0))
  const ao = [oth, oth + 1].some((a) => sim.cars[a].some((c) => c.amb && c.d >= 0))
  if (ao && !ac) return true
  if (ac) return false
  return (cq === 0 && oq > 0) || oq > cq + 2 || (sim.green >= 30 && oq > 0)
}
export function step(sim, dt, events) {
  sim.t += dt; sim.green += dt
  for (const e of events) {
    const arr = sim.cars[e.a]
    if (e.amb) {
      const back = arr[arr.length - 1]
      arr.push({ d: Math.max(170, back ? back.d + 16 : 0), wait: 0, amb: true, source: 'emergency', t0: sim.t })
      sim.spawned++
      continue
    }
    const count = Math.max(1, Math.floor(e.count || 1))
    for (let i = 0; i < count; i++) {
      const back = arr[arr.length - 1]
      const distance = Math.max(170, back ? back.d + 15 : 0)
      const source = e.source === 'scanned' ? 'scanned' : 'generated'
      arr.push({ d: distance, wait: 0, amb: false, source, t0: sim.t })
      sim.spawned++
      if (source === 'scanned') sim.scannedSpawned++
      else sim.generatedSpawned++
    }
  }
  if (sim.yellow > 0) { sim.yellow -= dt; if (sim.yellow <= 0) { sim.phase = sim.next; sim.green = 0 } }
  else if (sim.mode === 'fixed' ? sim.green >= 15 : sim.green >= 5 && decide(sim)) { sim.yellow = 1.5; sim.next = 1 - sim.phase }
  for (let a = 0; a < 4; a++) {
    const green = sim.yellow <= 0 && (a >> 1) === sim.phase, arr = sim.cars[a]
    arr.forEach((c, i) => {
      let lim = i > 0 ? arr[i - 1].d + 15 : -1e9
      if (c.d >= 0 && !green) lim = Math.max(lim, 0)
      const nd = Math.max(c.d - 60 * dt, lim)
      if (c.d - nd < 1e-6 && c.d >= 0) { c.wait += dt; sim.wait += dt }
      c.d = nd
    })
    sim.cars[a] = arr.filter((c) => {
      if (c.d < -190) { sim.served++; if (c.amb) { sim.ambN++; sim.ambSum += sim.t - c.t0 } return false }
      return true
    })
  }
  if (sim.t - sim.lastH >= 1) { sim.lastH = sim.t; sim.hist.push(sim.wait / Math.max(1, sim.spawned)); if (sim.hist.length > 90) sim.hist.shift() }
}
export function metrics(sim) {
  return {
    wait: sim.wait / Math.max(1, sim.spawned),
    queue: sim.cars.reduce((n, arr) => n + arr.filter((c) => c.d >= 0).length, 0),
    approaches: approachQueues(sim),
    generated: sim.generatedSpawned,
    scanned: sim.scannedSpawned,
    thr: sim.t > 5 ? (sim.served / sim.t) * 60 : 0,
    amb: sim.ambN ? sim.ambSum / sim.ambN : null,
  }
}
export function draw(c, sim) {
  c.fillStyle = '#0b1424'; c.fillRect(0, 0, 360, 360)
  c.fillStyle = '#334155'; c.fillRect(150, 0, 60, 360); c.fillRect(0, 150, 360, 60)
  c.strokeStyle = '#64748b'; c.lineWidth = 1.5; c.setLineDash([8, 8]); c.beginPath()
  c.moveTo(180, 0); c.lineTo(180, 150); c.moveTo(180, 210); c.lineTo(180, 360); c.moveTo(0, 180); c.lineTo(150, 180); c.moveTo(210, 180); c.lineTo(360, 180); c.stroke(); c.setLineDash([])
  c.strokeStyle = '#e2e8f0'; c.lineWidth = 3; c.beginPath()
  c.moveTo(150, 150); c.lineTo(180, 150); c.moveTo(180, 210); c.lineTo(210, 210); c.moveTo(150, 180); c.lineTo(150, 210); c.moveTo(210, 150); c.lineTo(210, 180); c.stroke()
  const L = [[140, 140], [220, 220], [220, 140], [140, 220]]
  L.forEach(([x, y], a) => {
    const mine = (a >> 1) === sim.phase
    c.fillStyle = mine && sim.yellow <= 0 ? '#22c55e' : mine ? '#facc15' : '#ef4444'
    c.shadowColor = c.fillStyle; c.shadowBlur = 10; c.beginPath(); c.arc(x, y, 6, 0, 7); c.fill(); c.shadowBlur = 0
  })
  c.fillStyle = '#cbd5e1'; c.font = '10px sans-serif'; c.textAlign = 'center'
  c.fillText('NORTH', 180, 18); c.fillText('SOUTH', 180, 352)
  c.fillText('WEST', 18, 184); c.fillText('EAST', 342, 184)
  sim.cars.forEach((arr, a) => arr.forEach((k) => {
    const pos = [[165, 150 - k.d], [195, 210 + k.d], [210 + k.d, 165], [150 - k.d, 195]][a], v = a < 2
    c.fillStyle = k.amb ? (Math.floor(sim.t * 4) % 2 ? '#ef4444' : '#f8fafc') : k.source === 'scanned' ? (k.wait > 2 ? '#f0abfc' : '#c084fc') : (k.wait > 2 ? '#f59e0b' : '#38bdf8')
    const w = k.amb ? 9 : 7, h = k.amb ? 17 : 12
    c.fillRect(pos[0] - (v ? w : h) / 2, pos[1] - (v ? h : w) / 2, v ? w : h, v ? h : w)
  }))
}
export function bench(name, secs = 900, seed = 11) {
  const r = rng(seed), f = createSim('fixed'), a = createSim('ai'); let em = 0
  for (let i = 0; i < secs / 0.05; i++) {
    const ev = []; SCEN[name].forEach((p, k) => { if (r() < p * 0.05) ev.push({ a: k }) })
    em += 0.05; if (em >= 60) { em = 0; ev.push({ a: Math.floor(r() * 4), amb: true }) }
    step(f, 0.05, ev); step(a, 0.05, ev)
  }
  return { name, f: metrics(f), a: metrics(a) }
}
