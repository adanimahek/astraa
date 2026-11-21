import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { SCEN, rng, createSim, step, metrics, draw } from './sim.js'

const Ctx = createContext(null)
export const useSim = () => useContext(Ctx)
const fresh = () => ({ fixed: createSim('fixed'), ai: createSim('ai'), rand: rng(7), pend: [] })
const APPROACH_INDEX = { north: 0, south: 1, east: 2, west: 3 }

export function SimProvider({ children }) {
  const [scen, setScen] = useState('Medium'), [speed, setSpeed] = useState(1), [running, setRunning] = useState(true)
  const [snap, setSnap] = useState({ f: {}, a: {}, hf: [], ha: [], t: 0, nf: 0, na: 0, ph: 0, g: 0, y: 0 })
  const [priorityEvent, setPriorityEvent] = useState(null)
  const [vehicleEvent, setVehicleEvent] = useState(null)
  const S = useRef(fresh()), cv = { fixed: useRef(null), ai: useRef(null) }
  const live = useRef({}); live.current = { scen, speed, running }

  useEffect(() => {
    let raf, last = performance.now(), lastSnap = 0
    const loop = (now) => {
      const s = S.current, { scen, speed, running } = live.current
      let rem = Math.min(0.1, (now - last) / 1000) * speed; last = now
      while (running && rem > 0) {
        const h = Math.min(0.05, rem); rem -= h
        const ev = s.pend.splice(0)
        SCEN[scen].forEach((r, a) => { if (s.rand() < r * h) ev.push({ a }) })
        step(s.fixed, h, ev); step(s.ai, h, ev)
      }
      ;['fixed', 'ai'].forEach((k) => { const c = cv[k].current; if (c) draw(c.getContext('2d'), s[k]) })
      if (now - lastSnap > 400) {
        lastSnap = now
        setSnap({ f: metrics(s.fixed), a: metrics(s.ai), hf: [...s.fixed.hist], ha: [...s.ai.hist], t: s.ai.t, nf: s.fixed.ambN, na: s.ai.ambN, ph: s.ai.phase, g: s.ai.green, y: s.ai.yellow })
      }
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [])

  const value = {
    scen, speed, running, snap, cv, priorityEvent, vehicleEvent, setSpeed, setRunning,
    chooseScenario: (k) => { setScen(k); S.current = fresh(); setPriorityEvent(null); setVehicleEvent(null) },
    reset: () => { S.current = fresh(); setPriorityEvent(null); setVehicleEvent(null) },
    dispatch: (approach) => {
      const lane = APPROACH_INDEX[approach]
      if (lane === undefined) throw new Error(`Unknown intersection approach: ${approach}`)
      S.current.pend.push({ a: lane, amb: true })
      setPriorityEvent({ approach, createdAt: Date.now() })
      setVehicleEvent({ approach, count: 1, emergency: true, createdAt: Date.now() })
      setRunning(true)
    },
    dispatchVehicles: (approach, count) => {
      const lane = APPROACH_INDEX[approach]
      if (lane === undefined) throw new Error(`Unknown intersection approach: ${approach}`)
      if (!Number.isInteger(count) || count < 1) throw new Error('Vehicle count must be a positive integer')
      S.current.pend.push({ a: lane, count, source: 'scanned' })
      setVehicleEvent({ approach, count, emergency: false, createdAt: Date.now() })
      setRunning(true)
    },
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
