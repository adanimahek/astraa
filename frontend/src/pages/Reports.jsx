import { BASE } from '../api.js'
import { useDetect } from '../DetectContext.jsx'
import { card, toDate } from '../components.jsx'

export default function Reports() {
  const { history, refresh, historyError, historyLoading } = useDetect()
  const approaches = (analysis) => {
    const counts = analysis?.approach_counts
    return counts ? Object.entries(counts).map(([name, count]) => `${name}: ${count}`).join(', ') : '–'
  }
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between"><div><h1 className="text-2xl font-bold">Reports</h1><p className="text-slate-400 text-sm">Saved detection runs (from MongoDB)</p></div>
        <button onClick={refresh} disabled={historyLoading} className="px-3 py-1.5 rounded-lg border border-line hover:bg-panel disabled:opacity-50 text-sm">{historyLoading ? 'Refreshing…' : 'Refresh'}</button></div>
      <section className={card + ' overflow-x-auto'}>
        {historyError && <p role="alert" className="text-red-400 text-sm mb-3">{historyError}</p>}
        {!historyError && historyLoading && history.length === 0 ? <p className="text-slate-400 text-sm">Loading reports…</p> : null}
        {!historyError && !historyLoading && history.length === 0 ? <p className="text-slate-500 text-sm">No detection runs saved yet.</p> : null}
        {history.length > 0 && (
          <table className="w-full text-sm text-left">
            <thead className="text-slate-400"><tr><th className="py-2">Time</th><th>File</th><th>Type</th><th>Vehicles</th><th>Volume</th><th>Approaches</th><th>Confidence</th><th>Time (s)</th><th>Emergency</th><th></th></tr></thead>
            <tbody>{history.map((h) => (
              <tr key={h.id} className="border-t border-line">
                <td className="py-2">{toDate(h.created_at).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })}</td><td>{h.filename}</td><td className="capitalize">{h.type}</td>
                <td>{h.total_vehicles ?? h.peak_vehicles}</td><td>{h.traffic_analysis?.traffic_volume?.level || '–'}</td><td className="capitalize">{approaches(h.traffic_analysis)}</td><td>{(h.avg_confidence * 100).toFixed(1)}%</td><td>{h.processing_seconds}</td>
                <td className={h.emergency_detected ? 'text-red-400 font-semibold' : 'text-slate-500'}>{h.emergency_detected ? 'Yes' : 'No'}</td>
                <td><a href={BASE + h.annotated_url} target="_blank" rel="noreferrer" className="text-accent">View</a></td>
              </tr>))}</tbody>
          </table>)}
      </section>
    </div>
  )
}
