import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { useDetect } from '../DetectContext.jsx'
import { useSim } from '../SimContext.jsx'
import { card, Stat, toDate } from '../components.jsx'

export default function Dashboard() {
  const { result, history, historyError, historyLoading } = useDetect()
  const { snap, cv } = useSim()
  const [comparison, setComparison] = useState(null)
  const [comparisonError, setComparisonError] = useState('')
  const [comparisonLoading, setComparisonLoading] = useState(true)
  useEffect(() => {
    let active = true
    api.simulationComparison()
      .then((data) => { if (active) setComparison(data) })
      .catch((error) => { if (active) setComparisonError(error.message) })
      .finally(() => { if (active) setComparisonLoading(false) })
    return () => { active = false }
  }, [])
  const last = result || history[0]
  const total = last ? (last.total_vehicles ?? last.peak_vehicles ?? 0) : null
  const volumeLevel = last?.traffic_analysis?.traffic_volume?.level
  const dens = volumeLevel
    ? [volumeLevel, volumeLevel === 'Low' ? 'text-emerald-400' : volumeLevel === 'Medium' ? 'text-yellow-400' : 'text-red-400']
    : total == null ? ['–', 'text-white'] : total < 8 ? ['Low', 'text-emerald-400'] : total < 20 ? ['Medium', 'text-yellow-400'] : ['High', 'text-red-400']
  const em = history.filter((h) => h.emergency_detected).length
  const latestSimulation = history.find((item) => item.emergency_simulation)?.emergency_simulation
  const latestQPriority = latestSimulation?.comparison === 'fixed_time_vs_q_learning_with_emergency_priority'
  const latestPriorityWait = latestQPriority
    ? latestSimulation.q_learning_priority_emergency_wait_seconds
    : latestSimulation?.priority_emergency_wait_seconds
  const latestPriorityTravel = latestQPriority
    ? latestSimulation.q_learning_priority_emergency_travel_seconds
    : latestSimulation?.priority_emergency_travel_seconds
  const latestPriorityCo2 = latestQPriority
    ? latestSimulation.q_learning_priority_co2_grams
    : latestSimulation?.priority_co2_grams
  const phase = snap.ph === 0 ? 'North ↔ South' : 'East ↔ West'
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">Dashboard</h1>
      <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat icon="🚗" title="Vehicles (last detection)" value={total ?? '–'} sub={last ? last.filename : 'Run a detection first'} />
        <Stat icon="📶" title="Traffic volume" value={dens[0]} tone={dens[1]} sub={last?.traffic_analysis?.traffic_volume?.basis || 'from last detection'} />
        <Stat icon="🎯" title="Detections run" value={historyError ? '–' : historyLoading && history.length === 0 ? '…' : history.length} sub={historyError ? 'history unavailable' : undefined} />
        <Stat icon="🚑" title="Emergency detections" value={em} tone={em ? 'text-red-400' : 'text-white'} sub={em ? 'see Emergency Priority' : 'none so far'} />
      </section>
      <section className="grid lg:grid-cols-3 gap-4">
        <div className={card + ' lg:col-span-2'}>
          <p className="font-semibold mb-2">Live Intersection Overview <span className="text-xs text-slate-500 font-normal">(simulated demo, ASTRA control)</span></p>
          <canvas ref={cv.ai} width={360} height={360} className="w-full max-w-[400px] mx-auto rounded-lg" />
        </div>
        <div className="space-y-4">
          <div className={card}>
            <p className="font-semibold mb-2">Current Signal Phase <span className="text-xs text-slate-500 font-normal">(demo)</span></p>
            <p className="text-xl font-bold">{phase}</p>
            <span className={`inline-block mt-2 px-3 py-1 rounded text-sm font-semibold ${snap.y > 0 ? 'bg-yellow-500/20 text-yellow-300' : 'bg-emerald-500/20 text-emerald-300'}`}>{snap.y > 0 ? 'YELLOW' : 'GREEN'}</span>
            <p className="text-sm text-slate-400 mt-2">Green for {snap.g.toFixed(0)} s</p>
          </div>
          <div className={card}>
            <p className="font-semibold mb-2">Recent Events</p>
            {historyError && <p role="alert" className="text-sm text-red-400">History unavailable: {historyError}</p>}
            {!historyError && historyLoading && history.length === 0 && <p className="text-sm text-slate-400">Loading events…</p>}
            {!historyError && !historyLoading && history.length === 0 && <p className="text-sm text-slate-500">No detections yet.</p>}
            {history.slice(0, 5).map((h) => (
              <p key={h.id} className="text-sm py-1 flex gap-2"><span className="text-slate-500">{toDate(h.created_at).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}</span>
                <span className={h.emergency_detected ? 'text-red-400' : 'text-slate-300'}>{h.emergency_detected ? 'Emergency vehicle detected' : `${h.total_vehicles ?? h.peak_vehicles} vehicles detected`}</span></p>
            ))}
          </div>
        </div>
      </section>
      {latestSimulation && (
        <section className={card}>
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="font-semibold">Latest SUMO emergency-priority comparison</p>
            <p className="text-xs text-slate-400 capitalize">
              {latestSimulation.approach} approach · {latestQPriority ? 'fixed-time vs Q-learning + priority' : 'legacy fixed-time vs standalone priority'}
            </p>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mt-4">
            {[
              ['Emergency wait (fixed)', `${latestSimulation.fixed_time_emergency_wait_seconds.toFixed(1)} s`],
              [latestQPriority ? 'Emergency wait (Q-learning + priority)' : 'Emergency wait (legacy priority)', `${latestPriorityWait.toFixed(1)} s`],
              ['Wait-time reduction', `${latestSimulation.emergency_wait_reduction_percent.toFixed(1)}%`],
              [latestQPriority ? 'Emergency travel (Q-learning + priority)' : 'Emergency travel (legacy priority)', `${latestPriorityTravel.toFixed(1)} s`],
              ['CO₂ (fixed)', `${(latestSimulation.fixed_time_co2_grams / 1000).toFixed(1)} kg`],
              [latestQPriority ? 'CO₂ (Q-learning + priority)' : 'CO₂ (legacy priority)', `${(latestPriorityCo2 / 1000).toFixed(1)} kg`],
            ].map(([label, value]) => <div key={label} className="rounded-lg bg-bg border border-line p-3"><p className="text-xs text-slate-400">{label}</p><p className="text-lg font-semibold">{value}</p></div>)}
          </div>
        </section>
      )}
      <section className={card}>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <p className="font-semibold">SUMO controller benchmark</p>
            <p className="text-xs text-slate-400">Fixed-time vs Q-learning with queue-pressure safeguard · matched traffic seeds</p>
          </div>
          {comparison?.updated_at && <p className="text-xs text-slate-500">Updated {new Date(comparison.updated_at).toLocaleString()}</p>}
        </div>
        {comparisonLoading && <p className="text-sm text-slate-400 mt-3">Loading SUMO benchmark…</p>}
        {!comparisonLoading && comparisonError && <p role="alert" className="text-sm text-amber-300 mt-3">Benchmark unavailable: {comparisonError}. Run <code>sumo\scripts\compare_controllers.py</code> to generate it.</p>}
        {comparison?.summary?.length === 2 && (
          <div className="grid md:grid-cols-2 gap-4 mt-4">
            {comparison.summary.map((row) => (
              <div key={row.controller} className="rounded-lg bg-bg border border-line p-3">
                <p className="font-semibold">{row.controller === 'q_learning' ? 'Q-learning' : 'Fixed-time'} <span className="text-xs text-slate-500 font-normal">({row.replications} seeds)</span></p>
                <div className="grid grid-cols-2 gap-x-3 gap-y-2 mt-3 text-sm">
                  <p className="text-slate-400">Waiting / trip</p><p>{row.average_waiting_time_seconds.toFixed(2)} s</p>
                  <p className="text-slate-400">Travel / trip</p><p>{row.average_travel_time_seconds.toFixed(2)} s</p>
                  <p className="text-slate-400">Average queue</p><p>{row.average_queue_vehicles.toFixed(2)} vehicles</p>
                  <p className="text-slate-400">Throughput</p><p>{row.throughput_vehicles_per_minute.toFixed(1)} veh/min</p>
                  <p className="text-slate-400">CO₂ estimate</p><p>{(row.co2_emissions_grams / 1000).toFixed(1)} kg</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
