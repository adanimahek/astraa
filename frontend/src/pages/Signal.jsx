import { useSim } from '../SimContext.jsx'
import { useDetect } from '../DetectContext.jsx'
import { Link } from 'react-router-dom'
import { SCEN } from '../sim.js'
import { Kpi, card } from '../components.jsx'

export default function Signal() {
  const { scen, speed, running, snap: m, cv, priorityEvent, vehicleEvent, chooseScenario, setSpeed, setRunning, reset } = useSim()
  const { history, simulationResult: currentSimulation, simulationError, simulationLoading } = useDetect()
  const simulationResult = currentSimulation || history.find((item) => item.emergency_simulation)?.emergency_simulation
  const qPriorityComparison = simulationResult?.comparison === 'fixed_time_vs_q_learning_with_emergency_priority'
  const qPriorityWait = qPriorityComparison
    ? simulationResult.q_learning_priority_emergency_wait_seconds
    : simulationResult?.priority_emergency_wait_seconds
  const qPriorityTravel = qPriorityComparison
    ? simulationResult.q_learning_priority_emergency_travel_seconds
    : simulationResult?.priority_emergency_travel_seconds
  const qPriorityActivatedAt = qPriorityComparison
    ? simulationResult.q_learning_priority_activated_at_seconds
    : simulationResult?.priority_activated_at_seconds
  const qPriorityCo2 = qPriorityComparison
    ? simulationResult.q_learning_priority_co2_grams
    : simulationResult?.priority_co2_grams
  const approachQueues = m.a.approaches || { north: 0, south: 0, east: 0, west: 0 }
  const northSouthQueue = approachQueues.north + approachQueues.south
  const eastWestQueue = approachQueues.east + approachQueues.west
  const adaptiveGreen = m.y > 0
    ? 'Changing phase safely (yellow)'
    : m.ph === 0 ? 'North + South' : 'East + West'
  const btn = (on) => `px-3 py-1.5 rounded-lg text-sm font-medium border ${on ? 'bg-brand border-brand text-white' : 'border-line text-slate-300 hover:bg-panel'}`
  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-bold">AI Signal Control</h1><p className="text-slate-400 text-sm">Same traffic, two controllers. Sim time {m.t.toFixed(0)} s</p></div>
      <section className="flex flex-wrap items-center gap-2">
        {Object.keys(SCEN).map((k) => <button key={k} onClick={() => chooseScenario(k)} className={btn(scen === k)}>{k}</button>)}
        <span className="mx-2 text-slate-600">|</span>
        {[1, 2, 4].map((v) => <button key={v} onClick={() => setSpeed(v)} className={btn(speed === v)}>{v}x</button>)}
        <button onClick={() => setRunning(!running)} className={btn(false)}>{running ? 'Pause' : 'Resume'}</button>
        <button onClick={reset} className={btn(false)}>Reset</button>
        <Link to="/input" className="px-3 py-1.5 rounded-lg text-sm font-semibold bg-red-500 hover:bg-red-400 ml-auto">🚑 Test uploaded emergency</Link>
      </section>
      {priorityEvent && (
        <section className="rounded-xl bg-red-600/20 border border-red-500 p-4">
          <p className="font-bold text-red-300">🚨 YOLO DETECTED AN EMERGENCY VEHICLE</p>
          <p className="text-sm text-slate-200 mt-1">A simulated emergency vehicle entered from the <b className="capitalize">{priorityEvent.approach}</b> approach. The browser demo favors that approach; the separate SUMO comparison uses trained Q-learning with an emergency-priority override.</p>
        </section>
      )}
      {vehicleEvent && !vehicleEvent.emergency && (
        <section className="rounded-xl bg-sky-600/10 border border-sky-500/50 p-4">
          <p className="font-bold text-sky-300">YOLO VEHICLES ADDED TO THE SIMULATION</p>
          <p className="text-sm text-slate-200 mt-1">
            {vehicleEvent.count} detected regular {vehicleEvent.count === 1 ? 'vehicle was' : 'vehicles were'} added to the <b className="capitalize">{vehicleEvent.approach}</b> approach. The same vehicles enter fixed-time and ASTRA adaptive simulations.
          </p>
        </section>
      )}
      {simulationLoading && (
        <section className={card}>
          <p className="font-semibold">Running paired SUMO simulations…</p>
          <p className="text-sm text-slate-400 mt-1">Comparing fixed-time with trained Q-learning plus an emergency-priority override using the selected approach.</p>
        </section>
      )}
      {simulationError && (
        <section role="alert" className="rounded-xl bg-red-600/10 border border-red-500 p-4">
          <p className="font-semibold text-red-300">SUMO simulation failed</p>
          <p className="text-sm text-slate-300 mt-1">{simulationError}</p>
        </section>
      )}
      {simulationResult && (
        <section className={card}>
          <p className="font-semibold">SUMO emergency-priority comparison</p>
          <p className="text-xs text-slate-400 mt-1">
            {qPriorityComparison ? 'Fixed-time vs trained Q-learning with emergency-priority override' : 'Legacy fixed-time vs standalone priority result'}.
            {' '}Approach: <span className="capitalize">{simulationResult.approach}</span>; same traffic seed and injected emergency for both runs.
          </p>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 mt-4">
            {[
              ['Emergency wait (fixed)', `${simulationResult.fixed_time_emergency_wait_seconds.toFixed(1)} s`],
              [qPriorityComparison ? 'Emergency wait (Q-learning + priority)' : 'Emergency wait (legacy priority)', `${qPriorityWait.toFixed(1)} s`],
              ['Emergency travel (fixed)', `${simulationResult.fixed_time_emergency_travel_seconds.toFixed(1)} s`],
              [qPriorityComparison ? 'Emergency travel (Q-learning + priority)' : 'Emergency travel (legacy priority)', `${qPriorityTravel.toFixed(1)} s`],
              ['Wait-time reduction', `${simulationResult.emergency_wait_reduction_percent.toFixed(1)}%`],
              ['Priority activated', `${qPriorityActivatedAt.toFixed(0)} s`],
              ['CO₂ (fixed)', `${(simulationResult.fixed_time_co2_grams / 1000).toFixed(1)} kg`],
              [qPriorityComparison ? 'CO₂ (Q-learning + priority)' : 'CO₂ (legacy priority)', `${(qPriorityCo2 / 1000).toFixed(1)} kg`],
            ].map(([label, value]) => <div key={label} className="rounded-lg bg-bg border border-line p-3"><p className="text-xs text-slate-400">{label}</p><p className="text-lg font-semibold">{value}</p></div>)}
          </div>
        </section>
      )}
      <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Kpi title="Avg waiting time" unit="s" fixed={m.f.wait} ai={m.a.wait} />
        <Kpi title="Queue length" unit="veh" fixed={m.f.queue} ai={m.a.queue} />
        <Kpi title="Throughput" unit="veh/min" fixed={m.f.thr} ai={m.a.thr} lowerBetter={false} />
        <Kpi title="Ambulance clearance" unit="s" fixed={m.f.amb} ai={m.a.amb} />
      </section>
      <section className={card}>
        <p className="font-semibold">Adaptive queue-based signal decision <span className="text-xs text-slate-500 font-normal">(browser simulation)</span></p>
        <p className="text-sm text-slate-300 mt-2">
          Current ASTRA green: <b className="text-accent">{adaptiveGreen}</b>
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3">
          {Object.entries(approachQueues).map(([approach, count]) => (
            <div key={approach} className="rounded-lg bg-bg border border-line p-3 capitalize">
              <p className="text-xs text-slate-400">{approach} approach queue</p>
              <p className="text-xl font-semibold">{count}</p>
            </div>
          ))}
        </div>
        <p className="text-xs text-slate-400 mt-3">
          North+South pressure: {northSouthQueue} · East+West pressure: {eastWestQueue}. When the opposite group builds a larger queue, ASTRA changes phase after the minimum green and yellow clearance. North and south share a safe green phase; north does not get a conflicting solo green.
        </p>
      </section>
      <section className={card}>
        <p className="font-semibold">Vehicle source legend <span className="text-xs text-slate-500 font-normal">(counts are cumulative since reset)</span></p>
        <div className="grid md:grid-cols-2 gap-3 mt-3">
          {[
            ['fixed', 'Fixed-time control (15 s cycle)', m.f],
            ['ai', 'ASTRA adaptive control', m.a],
          ].map(([key, title, stats]) => (
            <div key={key} className="rounded-lg bg-bg border border-line p-3">
              <p className="text-sm font-semibold">{title}</p>
              <div className="flex flex-wrap gap-4 mt-2 text-sm">
                <span><i className="inline-block w-3 h-3 rounded-sm bg-sky-400 mr-2" />Browser-generated: <b>{stats.generated ?? 0}</b></span>
                <span><i className="inline-block w-3 h-3 rounded-sm bg-purple-400 mr-2" />YOLO-scanned: <b>{stats.scanned ?? 0}</b></span>
              </div>
            </div>
          ))}
        </div>
        <p className="text-xs text-slate-400 mt-3">In the intersection view, blue vehicles are generated by the browser traffic scenario; purple vehicles came from an uploaded image/video detection. Emergency vehicles flash red/white. Both controllers receive the same arrivals.</p>
      </section>
      <section className="grid md:grid-cols-2 gap-4">
        {[['fixed', 'Fixed-time control (15 s cycle)', 'text-slate-300'], ['ai', 'ASTRA adaptive control', 'text-accent']].map(([k, t, c]) => (
          <div key={k} className={card}><p className={`text-sm font-semibold mb-2 ${c}`}>{t}</p><canvas ref={cv[k]} width={360} height={360} className="w-full max-w-[420px] mx-auto rounded-lg" /></div>
        ))}
      </section>
      <p className="text-xs text-slate-500">North, south, east, and west label the simulated approaches. Upload detection can trigger a vehicle on the selected road; it is not a live roadside signal or a direct SUMO connection.</p>
    </div>
  )
}
