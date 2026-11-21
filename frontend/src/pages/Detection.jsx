import { Link } from 'react-router-dom'
import { BASE } from '../api.js'
import { useDetect } from '../DetectContext.jsx'
import { card, CLASSES, Stat } from '../components.jsx'

export default function Detection() {
  const { result: r } = useDetect()
  if (!r) return (
    <div className={card + ' text-center py-12'}><p className="text-slate-400 mb-4">No detection yet. Upload an image or video first.</p><Link to="/input" className="px-4 py-2 rounded-lg bg-brand font-semibold">Go to Traffic Input</Link></div>
  )
  const video = r.type === 'video', total = video ? r.peak_vehicles : r.total_vehicles
  const analysis = r.traffic_analysis
  const approaches = analysis?.approach_counts
  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-bold">Vehicle Detection and Traffic Analysis</h1><p className="text-slate-400 text-sm">{video ? 'Video: peak simultaneous count from sampled frames' : 'Image result'}</p></div>
      {r.emergency_detected && (
        <div className="rounded-xl bg-red-600/20 border border-red-500 p-4 flex items-center justify-between">
          <p className="font-bold text-red-300">🚨 EMERGENCY VEHICLE DETECTED</p><Link to="/emergency" className="px-3 py-1.5 rounded-lg bg-red-500 text-sm font-semibold">Open Emergency Priority</Link>
        </div>)}
      {!r.emergency_detected && r.traffic_analysis?.approach_counts && (
        <p className="rounded-xl bg-panel border border-line p-4 text-sm text-slate-300">No ambulance or fire truck detected. No emergency vehicle was dispatched to the intersection simulation.</p>
      )}
      <section className="grid lg:grid-cols-3 gap-4">
        <div className={card + ' lg:col-span-2'}><img src={BASE + r.annotated_url} alt="Detection output" className="w-full rounded-lg" /></div>
        <div className={card}>
          <p className="font-semibold mb-3">Detection Results {video && <span className="text-xs text-slate-500 font-normal">(peak frame)</span>}</p>
          {CLASSES.map(([c, icon]) => (
            <div key={c} className={`flex justify-between py-1.5 border-b border-line text-sm ${r.counts[c] && c.match(/Ambulance|Fire/) ? 'text-red-300 font-semibold' : ''}`}><span>{icon} {c}</span><span>{r.counts[c] || 0}</span></div>
          ))}
        </div>
      </section>
      <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat icon="🚗" title={video ? 'Peak vehicles in a frame' : 'Total vehicles'} value={total} sub={video ? `${r.average_vehicles_per_frame} average per analysed frame` : undefined} />
        <Stat icon="📶" title="Traffic volume" value={analysis?.traffic_volume?.level || '–'} sub={analysis?.traffic_volume?.basis} />
        <Stat icon="🎯" title="Detection confidence" value={`${(r.avg_confidence * 100).toFixed(1)}%`} />
        <Stat icon="⏱️" title="Processing time" value={`${r.processing_seconds} s`} />
        {video ? <Stat icon="🎞️" title="Frames analysed" value={r.frames_analysed} sub={`${r.analysis_fps} fps`} /> : <Stat icon="📐" title="Image size" value={`${r.width}x${r.height}`} />}
      </section>
      {approaches && (
        <section className={card}>
          <p className="font-semibold mb-1">Estimated approach counts {video && <span className="text-xs text-slate-500 font-normal">(peak frame)</span>}</p>
          <p className="text-xs text-amber-300 mb-3">{analysis.approach_method}</p>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-sm">
            {Object.entries(approaches).map(([name, count]) => <div key={name} className="rounded-lg bg-bg border border-line p-3 capitalize">{name}<p className="text-lg font-semibold">{count}</p></div>)}
          </div>
        </section>
      )}
      <div className="flex gap-3"><Link to="/input" className="px-4 py-2 rounded-lg border border-line hover:bg-panel text-sm">Analyse another</Link><Link to="/reports" className="px-4 py-2 rounded-lg border border-line hover:bg-panel text-sm">View reports</Link></div>
    </div>
  )
}
