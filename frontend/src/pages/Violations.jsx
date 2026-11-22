import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { Badge, btn, card, Evidence, fmtDate, input } from '../components.jsx'

const FILTERS = [['', 'All'], ['pending_review', 'Needs review'], ['unregistered', 'Unregistered'], ['verified', 'Verified'], ['challan_issued', 'Challan issued'], ['rejected', 'Rejected']]

function DetectPanel({ onDone }) {
  const [mode, setMode] = useState('video')
  const [file, setFile] = useState(null), [config, setConfig] = useState(''), [conf, setConf] = useState(0.4)
  const [sumo, setSumo] = useState({ seed: 101, duration_seconds: 600, violation_probability: 0.05, gui: false })
  const [busy, setBusy] = useState(false), [msg, setMsg] = useState(''), [err, setErr] = useState('')
  useEffect(() => { api.violationConfigExample().then((c) => setConfig(JSON.stringify(c, null, 2))).catch(() => {}) }, [])

  async function run() {
    setErr(''); setMsg(''); setBusy(true)
    try {
      let r
      if (mode === 'video') {
        if (!file) throw new Error('Choose a video file')
        try { JSON.parse(config) } catch { throw new Error('Signal / stop-line config is not valid JSON') }
        r = await api.detectViolationsVideo(file, config, conf)
      } else r = await api.detectViolationsSumo(sumo)
      setMsg(`${r.violations_detected} violation(s) detected, ${r.violations_stored} stored, ${r.duplicates_skipped} duplicate(s) skipped` +
        (r.unknown_signal_frames ? ` · ${r.unknown_signal_frames} frame(s) had UNKNOWN signal state and were not enforced` : ''))
      onDone()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  return (
    <div className={card + ' space-y-3'}>
      <div className="flex items-center gap-2">
        <p className="font-semibold mr-auto">Detect red-light violations</p>
        {[['video', '🎞️ Uploaded video'], ['sumo', '🛣️ SUMO / TraCI']].map(([k, l]) => <button key={k} onClick={() => setMode(k)} className={`${btn} ${mode === k ? 'bg-brand text-white' : 'border border-line'}`}>{l}</button>)}
      </div>
      {mode === 'video' ? (
        <>
          <div className="flex flex-wrap gap-3 items-center">
            <input type="file" accept=".mp4,.avi,.mov" onChange={(e) => setFile(e.target.files[0])} className="text-sm" />
            <label className="text-sm text-slate-400">Confidence <input type="number" min="0.1" max="0.9" step="0.05" value={conf} onChange={(e) => setConf(e.target.value)} className={input + ' w-20 ml-1'} /></label>
          </div>
          <label className="block text-xs text-slate-400">Stop line(s) and signal timeline (normalised 0–1 coordinates; time not covered is UNKNOWN and is never enforced)</label>
          <textarea value={config} onChange={(e) => setConfig(e.target.value)} rows={10} spellCheck={false} className={input + ' w-full font-mono text-xs'} />
        </>
      ) : (
        <div className="flex flex-wrap gap-3 text-sm">
          {[['seed', 'Seed', 1], ['duration_seconds', 'Duration (s)', 60], ['violation_probability', 'Red-light-ignoring share', 0.01]].map(([k, l, step]) => (
            <label key={k} className="text-slate-400">{l}<input type="number" step={step} value={sumo[k]} onChange={(e) => setSumo({ ...sumo, [k]: Number(e.target.value) })} className={input + ' w-28 ml-2'} /></label>
          ))}
          <label className="text-slate-400 flex items-center gap-2"><input type="checkbox" checked={sumo.gui} onChange={(e) => setSumo({ ...sumo, gui: e.target.checked })} />Show SUMO GUI</label>
        </div>
      )}
      <button disabled={busy} onClick={run} className={btn + ' bg-brand text-white'}>{busy ? 'Processing…' : 'Run detection'}</button>
      {msg && <p className="text-sm text-emerald-400">{msg}</p>}
      {err && <p role="alert" className="text-sm text-red-400">{err}</p>}
    </div>
  )
}

function ViolationRow({ v, onChange }) {
  const [open, setOpen] = useState(false), [plate, setPlate] = useState(v.plate?.number || v.plate?.raw_text || '')
  const [reason, setReason] = useState(''), [err, setErr] = useState(''), [busy, setBusy] = useState(false)
  const act = (fn) => async () => { setErr(''); setBusy(true); try { await fn(); onChange() } catch (e) { setErr(e.message) } finally { setBusy(false) } }
  const reviewable = ['pending_review', 'verified', 'unregistered', 'detected'].includes(v.status)
  const p = v.plate || {}
  return (
    <>
      <tr className="border-t border-line hover:bg-white/5 cursor-pointer" onClick={() => setOpen(!open)}>
        <td className="py-2 pr-3 font-mono text-xs">{v.violation_id}</td>
        <td className="pr-3 text-xs">{fmtDate(v.occurred_at)}</td>
        <td className="pr-3 text-xs">{v.source?.kind} · {v.approach}</td>
        <td className="pr-3 text-xs">{v.vehicle_class || '–'}</td>
        <td className="pr-3 font-mono">{p.number || <span className="text-slate-500">{p.raw_text || '–'}</span>}{p.confidence != null && <span className="text-[11px] text-slate-500 ml-1">{(p.confidence * 100).toFixed(0)}%</span>}</td>
        <td className="pr-3"><Badge status={v.status} /></td>
        <td className="text-xs font-mono">{v.challan_number || ''}</td>
      </tr>
      {open && (
        <tr className="bg-black/20"><td colSpan={7} className="p-3 space-y-3">
          <Evidence base={`/api/violations/${v.violation_id}`} evidence={v.evidence} />
          <div className="grid sm:grid-cols-3 gap-3 text-xs text-slate-300">
            <p>Signal: <b className="text-red-300">{v.signal?.state}</b> for {v.signal?.time_into_red?.toFixed?.(1)} s · media t={v.media_time?.toFixed?.(2)} s ({v.occurred_at_basis})</p>
            <p>OCR: {p.raw_text || '–'} · OCR conf {p.ocr_confidence ?? '–'} · detector {p.detector_confidence ?? '–'} · source {p.source || '–'}</p>
            <p>Owner: {v.owner ? `${v.owner.name} (${v.owner.owner_id})` : '–'}{v.registry_warnings?.length ? <span className="text-orange-300"> ⚠ {v.registry_warnings.join('; ')}</span> : null}</p>
          </div>
          {p.review_reasons?.length > 0 && <p className="text-xs text-orange-300">Review reasons: {p.review_reasons.join(', ')}</p>}
          {reviewable && (
            <div className="flex flex-wrap gap-2 items-center" onClick={(e) => e.stopPropagation()}>
              <input value={plate} onChange={(e) => setPlate(e.target.value.toUpperCase())} placeholder="KA01AB1234" className={input + ' font-mono w-40'} />
              <button disabled={busy} onClick={act(() => api.verifyPlate(v.violation_id, plate))} className={btn + ' bg-emerald-600 text-white'}>Verify plate</button>
              {v.status === 'unregistered' && <button disabled={busy} onClick={act(() => api.resolveOwner(v.violation_id))} className={btn + ' border border-line'}>Retry owner lookup</button>}
              <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Rejection reason" className={input + ' w-52'} />
              <button disabled={busy || reason.length < 3} onClick={act(() => api.rejectViolation(v.violation_id, reason))} className={btn + ' bg-red-600/80 text-white'}>Reject</button>
            </div>
          )}
          {err && <p className="text-xs text-red-400">{err}</p>}
        </td></tr>
      )}
    </>
  )
}

export default function Violations() {
  const [status, setStatus] = useState('pending_review'), [data, setData] = useState({ total: 0, items: [] })
  const [err, setErr] = useState(''), [loading, setLoading] = useState(true)
  const load = useCallback(() => {
    setLoading(true)
    api.violations({ status, limit: 100 }).then(setData).catch((e) => setErr(e.message)).finally(() => setLoading(false))
  }, [status])
  useEffect(load, [load])
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">Red-Light Violations</h1>
      <DetectPanel onDone={load} />
      <div className={card}>
        <div className="flex flex-wrap gap-2 mb-3">
          {FILTERS.map(([k, l]) => <button key={k} onClick={() => setStatus(k)} className={`${btn} ${status === k ? 'bg-brand text-white' : 'border border-line text-slate-300'}`}>{l}</button>)}
          <span className="ml-auto text-sm text-slate-400 self-center">{loading ? 'Loading…' : `${data.total} record(s)`}</span>
        </div>
        {err && <p className="text-sm text-red-400">{err}</p>}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-slate-400"><tr><th className="py-2">ID</th><th>Time</th><th>Source</th><th>Class</th><th>Plate</th><th>Status</th><th>Challan</th></tr></thead>
            <tbody>{data.items.map((v) => <ViolationRow key={v.violation_id} v={v} onChange={load} />)}</tbody>
          </table>
          {!loading && data.items.length === 0 && <p className="text-sm text-slate-500 py-4 text-center">No violations in this view.</p>}
        </div>
      </div>
    </div>
  )
}
