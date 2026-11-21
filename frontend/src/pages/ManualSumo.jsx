import { useState } from 'react'
import { api } from '../api.js'
import { card } from '../components.jsx'

const APPROACHES = ['north', 'south', 'east', 'west']
const emptyLanes = () => Object.fromEntries(APPROACHES.map((approach) => [approach, [0, 0]]))
const initialApproaches = ['north', 'south']

export default function ManualSumo() {
  const [laneCounts, setLaneCounts] = useState(emptyLanes)
  const [roadCount, setRoadCount] = useState(2)
  const [activeApproaches, setActiveApproaches] = useState(initialApproaches)
  const [emergencyLanes, setEmergencyLanes] = useState([])
  const [duration, setDuration] = useState(300)
  const [visualize, setVisualize] = useState(true)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const vehicleTotal = activeApproaches.reduce(
    (sum, approach) => sum + laneCounts[approach].reduce((laneSum, count) => laneSum + count, 0),
    0,
  ) + emergencyLanes.filter((item) => activeApproaches.includes(item.approach)).length

  function updateActiveApproaches(nextApproaches) {
    setActiveApproaches(nextApproaches)
    const inactive = APPROACHES.filter((approach) => !nextApproaches.includes(approach))
    setLaneCounts((current) => ({
      ...current,
      ...Object.fromEntries(inactive.map((approach) => [approach, [0, 0]])),
    }))
    setEmergencyLanes((current) => current.filter((item) => nextApproaches.includes(item.approach)))
  }

  function changeRoadCount(value) {
    const nextCount = Number(value)
    setRoadCount(nextCount)
    const nextApproaches = activeApproaches.slice(0, nextCount)
    for (const approach of APPROACHES) {
      if (nextApproaches.length === nextCount) break
      if (!nextApproaches.includes(approach)) nextApproaches.push(approach)
    }
    updateActiveApproaches(nextApproaches)
  }

  function toggleApproach(approach) {
    const nextApproaches = activeApproaches.includes(approach)
      ? activeApproaches.filter((item) => item !== approach)
      : [...activeApproaches, approach]
    if (nextApproaches.length <= roadCount) updateActiveApproaches(nextApproaches)
  }

  function setCount(approach, lane, value) {
    setLaneCounts((current) => ({
      ...current,
      [approach]: current[approach].map((count, index) => index === lane ? Number(value) : count),
    }))
  }

  function toggleEmergency(approach, lane) {
    setEmergencyLanes((current) => {
      const exists = current.some((item) => item.approach === approach && item.lane === lane)
      return exists
        ? current.filter((item) => item.approach !== approach || item.lane !== lane)
        : [...current, { approach, lane }]
    })
  }

  async function runSimulation(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    setResult(null)
    try {
      setResult(await api.runManualSimulation({
        road_count: roadCount,
        active_approaches: activeApproaches,
        lane_counts: laneCounts,
        emergency_vehicles: emergencyLanes,
        duration_seconds: Number(duration),
        visualize,
      }))
    } catch (simulationError) {
      setError(simulationError.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-bold">Manual SUMO Scenario</h1>
        <p className="text-sm text-slate-400 mt-1">Choose 2–4 active approaches and place regular or emergency vehicles in the existing two lanes, then compare fixed-time with ASTRA adaptive SUMO control.</p>
      </header>

      <form className={`${card} space-y-5`} onSubmit={runSimulation}>
        <div className="rounded-lg border border-line bg-bg p-3 text-sm text-slate-300">
          SUMO uses the project's existing intersection. Choose how many approaches are active, then select those directions. Only selected approaches receive vehicles; each has the two lanes defined in the network. The fixed-time trial uses 15-second greens when both signal groups are active; ASTRA uses the trained Q-learning policy and prioritizes selected emergency vehicles.
        </div>
        <div className="grid gap-3 sm:grid-cols-2 items-start">
          <label className="flex items-center gap-3 text-sm">
            Number of roads/approaches
            <select
              value={roadCount}
              onChange={(event) => changeRoadCount(event.target.value)}
              className="rounded-lg border border-line bg-bg px-3 py-2"
            >
              {[2, 3, 4].map((count) => <option key={count} value={count}>{count}</option>)}
            </select>
          </label>
          <fieldset>
            <legend className="text-sm text-slate-300">Choose exactly {roadCount} approaches</legend>
            <div className="flex flex-wrap gap-x-4 gap-y-2 mt-2">
              {APPROACHES.map((approach) => (
                <label key={approach} className="flex items-center gap-2 text-sm capitalize">
                  <input
                    type="checkbox"
                    checked={activeApproaches.includes(approach)}
                    disabled={!activeApproaches.includes(approach) && activeApproaches.length >= roadCount}
                    onChange={() => toggleApproach(approach)}
                  />
                  {approach}
                </label>
              ))}
            </div>
          </fieldset>
        </div>
        <div className="flex flex-wrap gap-5 text-sm">
          <span><i className="inline-block w-3 h-3 rounded-sm bg-sky-400 mr-2" />Regular vehicles</span>
          <span><i className="inline-block w-3 h-3 rounded-sm bg-red-500 mr-2" />Emergency vehicles</span>
        </div>
        <div className="grid md:grid-cols-2 gap-4">
          {APPROACHES.map((approach) => (
            <section key={approach} className={`rounded-lg border border-line p-4 ${activeApproaches.includes(approach) ? '' : 'opacity-50'}`}>
              <h2 className="font-semibold capitalize mb-3">{approach} approach</h2>
              <div className="grid grid-cols-[1fr_auto_auto] gap-x-4 gap-y-3 items-center text-sm">
                <span className="text-slate-400">Lane</span>
                <span className="text-slate-400">Regular vehicles</span>
                <span className="text-slate-400">Emergency</span>
                {[0, 1].map((lane) => (
                  <div key={lane} className="contents">
                    <span>Lane {lane + 1}</span>
                    <input
                      type="number"
                      min="0"
                      max="50"
                      value={laneCounts[approach][lane]}
                      disabled={!activeApproaches.includes(approach)}
                      onChange={(event) => setCount(approach, lane, event.target.value)}
                      aria-label={`${approach} lane ${lane + 1} regular vehicle count`}
                      className="w-24 rounded-lg border border-line bg-bg px-3 py-2"
                    />
                    <label className="flex items-center justify-center">
                      <input
                        type="checkbox"
                        checked={emergencyLanes.some((item) => item.approach === approach && item.lane === lane)}
                        disabled={!activeApproaches.includes(approach)}
                        onChange={() => toggleEmergency(approach, lane)}
                        aria-label={`Add emergency vehicle to ${approach} lane ${lane + 1}`}
                      />
                    </label>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
        <label className="flex flex-wrap gap-3 items-center text-sm">
          Maximum simulation duration
          <input
            type="number"
            min="60"
            max="900"
            step="30"
            value={duration}
            onChange={(event) => setDuration(event.target.value)}
            className="w-28 rounded-lg border border-line bg-bg px-3 py-2"
          />
          <span className="text-slate-400">seconds (60–900)</span>
        </label>
        <label className="flex items-start gap-3 text-sm">
          <input
            type="checkbox"
            checked={visualize}
            onChange={(event) => setVisualize(event.target.checked)}
            className="mt-1"
          />
          <span>
            Show vehicle flow in SUMO-GUI
            <span className="block text-xs text-slate-400 mt-1">Opens SUMO-GUI during each controller run with slowed playback. This requires the backend to run on this computer's desktop; uncheck to run headlessly.</span>
          </span>
        </label>
        <div className="flex flex-wrap items-center gap-4">
          <p className="text-sm text-slate-300">Vehicles to simulate: <b>{vehicleTotal}</b> / 100 maximum</p>
          <button
            type="submit"
            disabled={busy || activeApproaches.length !== roadCount || vehicleTotal < 1 || vehicleTotal > 100}
            className="rounded-lg bg-brand px-5 py-2.5 font-semibold hover:bg-blue-500 disabled:opacity-50"
          >
            {busy ? (visualize ? 'Opening SUMO-GUI and simulating…' : 'Running SUMO simulations…') : 'Run manual SUMO comparison'}
          </button>
        </div>
        {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
      </form>

      {result && (
        <section className={card}>
          <h2 className="font-semibold">SUMO results</h2>
          <p className="text-sm text-slate-400 mt-1">Active approaches: {result.active_approaches.join(', ')} · Requested vehicles: {result.requested_vehicles}; regular lane counts and emergency placements are identical in both runs.</p>
          <div className="grid md:grid-cols-2 gap-4 mt-4">
            {result.results.map((run) => (
              <article key={run.controller} className="rounded-lg border border-line bg-bg p-4">
                <h3 className="font-semibold text-accent">{run.controller}</h3>
                <div className="grid grid-cols-2 gap-3 mt-3">
                  {[
                    ['Arrived', `${run.arrived_vehicles}`],
                    ['Unfinished', `${run.unfinished_vehicles}`],
                    ['Average wait', `${run.average_waiting_time_seconds.toFixed(1)} s`],
                    ['Average travel', `${run.average_travel_time_seconds.toFixed(1)} s`],
                    ['Average queue', `${run.average_queue_vehicles.toFixed(2)} vehicles`],
                    ['Throughput', `${run.throughput_vehicles_per_minute.toFixed(2)} veh/min`],
                    ['CO₂', `${(run.co2_emissions_grams / 1000).toFixed(2)} kg`],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <p className="text-xs text-slate-400">{label}</p>
                      <p className="font-medium">{value}</p>
                    </div>
                  ))}
                </div>
                <p className="text-sm mt-3">
                  Emergency vehicles arrived: {run.emergency_arrived}
                  {run.emergency_average_waiting_time_seconds !== null
                    ? ` · average emergency wait ${run.emergency_average_waiting_time_seconds.toFixed(1)} s`
                    : ''}
                </p>
                <div className="mt-4">
                  <h4 className="text-sm font-semibold">Signal order</h4>
                  <p className="text-xs text-slate-400 mt-1">Time-ordered SUMO signal phases and the state for each selected approach.</p>
                  <div className="overflow-x-auto mt-2">
                    <table className="w-full text-xs text-left">
                      <thead className="text-slate-400">
                        <tr>
                          <th className="py-2 pr-3">Time</th>
                          <th className="py-2 pr-3">Phase</th>
                          {result.active_approaches.map((approach) => <th key={approach} className="py-2 pr-3 capitalize">{approach}</th>)}
                        </tr>
                      </thead>
                      <tbody>
                        {run.signal_order.map((event, index) => (
                          <tr key={`${event.time_seconds}-${event.phase_index}-${index}`} className="border-t border-line">
                            <td className="py-2 pr-3">{event.time_seconds}s</td>
                            <td className="py-2 pr-3">{event.phase_name}</td>
                            {result.active_approaches.map((approach) => (
                              <td
                                key={approach}
                                className={`py-2 pr-3 font-semibold ${event.approach_states[approach] === 'GREEN' ? 'text-emerald-400' : event.approach_states[approach] === 'YELLOW' ? 'text-amber-400' : 'text-red-400'}`}
                              >
                                {event.approach_states[approach]}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </article>
            ))}
          </div>
          <p className="text-xs text-slate-500 mt-4">This is a computer simulation only. It does not connect to physical traffic lights or road vehicles.</p>
        </section>
      )}
    </div>
  )
}
