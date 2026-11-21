import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { card, CLASSES, Stat } from '../components.jsx'

const APPROACHES = ['north', 'south', 'east', 'west']

export default function LiveFeed() {
  const [status, setStatus] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    try {
      setStatus(await api.liveFeedStatus())
      setError('')
    } catch (requestError) {
      setError(requestError.message)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])
  useEffect(() => {
    if (!['starting', 'running'].includes(status?.state)) return undefined
    const timer = setInterval(refresh, 1500)
    return () => clearInterval(timer)
  }, [status?.state, refresh])

  async function start() {
    setBusy(true)
    setError('')
    try {
      setStatus(await api.liveFeedStart())
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy(false)
    }
  }

  async function stop() {
    setBusy(true)
    setError('')
    try {
      setStatus(await api.liveFeedStop())
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy(false)
    }
  }

  const running = ['starting', 'running'].includes(status?.state)
  const metrics = status?.metrics

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Live Feed & Simulation</h1>
        <p className="text-sm text-slate-400">Four RTSP cameras → YOLO counts → trained Q-learning policy → SUMO simulation.</p>
      </div>

      <section className={card}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="font-semibold">Camera and SUMO session</p>
            <p className="text-sm text-slate-400 mt-1">{status?.message || 'Checking backend session…'}</p>
            {status?.state === 'running' && (
              <p className="text-xs text-slate-500 mt-1">
                Controller: {status.controller} · SUMO time {status.simulation_time_seconds.toFixed(0)} / {status.simulation_end_seconds}s
              </p>
            )}
          </div>
          {!running
            ? <button disabled={busy} onClick={start} className="px-4 py-2 rounded-lg bg-brand hover:bg-blue-500 disabled:opacity-50 font-semibold">{busy ? 'Starting…' : 'Start live YOLO + SUMO'}</button>
            : <button disabled={busy} onClick={stop} className="px-4 py-2 rounded-lg border border-line hover:bg-panel disabled:opacity-50 font-semibold">{busy ? 'Stopping…' : 'Stop session'}</button>}
        </div>
        {error && <p role="alert" className="mt-3 text-sm text-red-400">{error}</p>}
        {status?.state === 'error' && <p role="alert" className="mt-3 text-sm text-red-400">{status.message}</p>}
      </section>

      <section className={card}>
        <p className="font-semibold">SUMO signal decision</p>
        <p className="text-xl font-bold text-accent mt-2">{status?.signal?.state || 'Waiting for simulation'}</p>
        <p className="text-sm text-slate-300 mt-1">{status?.controller_decision || 'The Q-learning controller has not made a decision yet.'}</p>
        <p className="text-xs text-slate-500 mt-2">
          North queue input: {status?.approach_vehicle_counts?.north ?? '–'} · South: {status?.approach_vehicle_counts?.south ?? '–'} · East: {status?.approach_vehicle_counts?.east ?? '–'} · West: {status?.approach_vehicle_counts?.west ?? '–'}
        </p>
        <p className="text-xs text-slate-500 mt-1">North/South share one safe green phase; East/West share the other. The trained Q-policy uses grouped approach counts, with a queue-pressure safeguard that favors the busier group after minimum green; maximum green prevents starvation.</p>
      </section>

      <section className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        <Stat icon="⏱️" title="Estimated waiting / arrival" value={metrics?.arrived_vehicles ? `${metrics.average_waiting_time_seconds.toFixed(1)} s` : '–'} sub="queue vehicle-seconds ÷ arrivals" />
        <Stat icon="🛣️" title="SUMO travel / arrival" value={metrics?.arrived_vehicles ? `${metrics.average_travel_time_seconds.toFixed(1)} s` : '–'} />
        <Stat icon="🚗" title="SUMO arrivals" value={metrics?.arrived_vehicles ?? '–'} />
        <Stat icon="📈" title="SUMO throughput" value={metrics ? `${metrics.throughput_vehicles_per_minute.toFixed(1)} /min` : '–'} />
        <Stat icon="🌫️" title="SUMO CO₂ estimate" value={metrics ? `${(metrics.co2_emissions_grams / 1000).toFixed(2)} kg` : '–'} />
        <Stat icon="🚨" title="Simulated emergency priority" value={metrics?.emergency_vehicle_dispatches ?? 0} sub={`${metrics?.emergency_priority_override_steps ?? 0} SUMO steps · ${status?.priority_active_approach ? `active: ${status.priority_active_approach}` : 'Q-policy otherwise active'}`} />
      </section>
      {metrics && (
        <p className="text-xs text-slate-500">
          SUMO average queue: {metrics.average_queue_vehicles.toFixed(2)} vehicles · queue vehicle-seconds: {metrics.queue_vehicle_seconds.toFixed(0)}. Metrics are from the simulated SUMO traffic, not measured camera wait times.
        </p>
      )}

      <section className="grid md:grid-cols-2 gap-4">
        {APPROACHES.map((approach) => {
          const camera = status?.cameras?.[approach]
          const counts = camera?.counts || {}
          const total = camera?.total_vehicles ?? Object.values(counts).reduce((sum, count) => sum + count, 0)
          return (
            <div key={approach} className={card}>
              <div className="flex items-center justify-between gap-2">
                <p className="font-semibold capitalize">{approach} approach</p>
                <span className={`text-xs ${status?.signal?.green_approaches?.includes(approach) ? 'text-emerald-400 font-semibold' : camera?.connected ? 'text-slate-400' : 'text-slate-500'}`}>
                  {status?.signal?.green_approaches?.includes(approach) ? 'GREEN' : camera?.connected ? 'RED' : 'Waiting for camera'}
                </span>
              </div>
              <div className="mt-3 aspect-video rounded-lg bg-bg border border-line overflow-hidden grid place-items-center">
                {camera?.annotated_frame
                  ? <img src={`data:image/jpeg;base64,${camera.annotated_frame}`} alt={`${approach} camera with YOLO detections`} className="w-full h-full object-contain" />
                  : <p className="text-sm text-slate-500 px-3 text-center">No annotated frame received.</p>}
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2 mt-3">
                <p className="text-sm text-slate-300">Vehicles in latest frame: <b>{camera?.connected ? total : '–'}</b></p>
                {camera?.emergency_detected && <span className="text-sm font-bold text-red-400">Emergency detected — SUMO priority active</span>}
              </div>
              <div className="grid grid-cols-2 gap-x-3 gap-y-1 mt-3 text-xs">
                {CLASSES.map(([name]) => (
                  <p key={name} className={name === 'Ambulance' || name === 'Fire Truck' ? 'text-red-300' : 'text-slate-400'}>
                    {name}: <span className="text-slate-200">{counts[name] || 0}</span>
                  </p>
                ))}
              </div>
              {camera?.last_frame_at && <p className="text-[11px] text-slate-500 mt-2">Last analyzed: {new Date(camera.last_frame_at).toLocaleTimeString()}</p>}
            </div>
          )
        })}
      </section>

      <section className={card}>
        <p className="font-semibold">What this integration controls</p>
        <p className="text-sm text-slate-400 mt-2">
          Each camera is assigned to its named approach. YOLO counts in the latest frame are combined into north/south and east/west state buckets and supplied to the saved Q-learning policy. If one group has more than two additional detections, the controller favors that group after minimum green, subject to the maximum-green limit. These counts are vehicle-count proxies—not calibrated queue measurements—so the live-feed control remains experimental.
        </p>
        <p className="text-sm text-slate-400 mt-2">
          An ambulance or fire truck detected on an approach triggers a simulated emergency vehicle and temporarily overrides the Q-policy to serve that approach; Q-learning resumes afterward. This changes only the SUMO simulation, never a real traffic signal.
        </p>
      </section>
    </div>
  )
}
