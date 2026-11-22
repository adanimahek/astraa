import { useEffect, useState } from 'react'
import { fetchBlobUrl } from './api.js'
export const f1 = (v) => (v == null ? '–' : v.toFixed(1))
export const card = 'rounded-xl bg-panel border border-line p-4'
export const toDate = (s) => new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : s + 'Z')
export const CLASSES = [['Car', '🚗'], ['Bus', '🚌'], ['Truck', '🚚'], ['2-Wheeler', '🏍️'], ['3-Wheeler', '🛺'], ['Tempo/Van', '🚐'], ['Bicycle', '🚲'], ['Other', '🚙'], ['Ambulance', '🚑'], ['Fire Truck', '🚒']]

export function Stat({ icon, title, value, sub, tone = 'text-white' }) {
  return (
    <div className={card + ' flex items-center gap-4'}>
      <div className="text-3xl w-12 h-12 grid place-items-center rounded-lg bg-brand/20">{icon}</div>
      <div><p className="text-xs text-slate-400">{title}</p><p className={`text-2xl font-bold ${tone}`}>{value}</p>{sub && <p className="text-xs text-slate-500">{sub}</p>}</div>
    </div>
  )
}

export function Kpi({ title, unit, fixed, ai, lowerBetter = true }) {
  const better = fixed != null && ai != null && fixed > 0 && (lowerBetter ? ai < fixed : ai > fixed)
  const pct = fixed > 0 && ai != null ? Math.abs(((ai - fixed) / fixed) * 100) : 0
  return (
    <div className={card}>
      <p className="text-xs uppercase tracking-wide text-slate-400">{title}</p>
      <div className="flex items-end justify-between mt-2">
        <div><p className="text-xs text-slate-500">Fixed-time</p><p className="text-xl font-semibold text-slate-300">{f1(fixed)}</p></div>
        <div className="text-right"><p className="text-xs text-accent">ASTRA</p><p className="text-3xl font-bold text-accent">{f1(ai)}<span className="text-sm text-slate-400 ml-1">{unit}</span></p></div>
      </div>
      {better && <p className="mt-2 text-xs text-emerald-400">▲ {pct.toFixed(0)}% better</p>}
    </div>
  )
}

export const money = (v) => (v == null ? '–' : '₹' + Number(v).toLocaleString('en-IN'))
export const fmtDate = (s, time = true) => (s ? toDate(s).toLocaleString('en-IN', time ? { dateStyle: 'medium', timeStyle: 'short' } : { dateStyle: 'medium' }) : '–')
export const btn = 'px-3 py-1.5 rounded-lg text-sm font-medium disabled:opacity-50'
export const input = 'rounded-lg bg-[#0a1428] border border-line px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent'

const TONES = {
  unpaid: 'bg-yellow-500/15 text-yellow-300', paid: 'bg-emerald-500/15 text-emerald-300', overdue: 'bg-red-500/20 text-red-300',
  cancelled: 'bg-slate-500/20 text-slate-300', challan_issued: 'bg-brand/25 text-sky-300', verified: 'bg-emerald-500/15 text-emerald-300',
  pending_review: 'bg-orange-500/20 text-orange-300', unregistered: 'bg-fuchsia-500/20 text-fuchsia-300', rejected: 'bg-slate-500/20 text-slate-400', detected: 'bg-slate-500/20 text-slate-300',
}
export function Badge({ status }) {
  return <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold uppercase tracking-wide ${TONES[status] || 'bg-slate-500/20'}`}>{String(status || '–').replace('_', ' ')}</span>
}

// Evidence images require the JWT, so they are fetched as blobs.
export function AuthImage({ src, alt, className = '' }) {
  const [url, setUrl] = useState(null), [err, setErr] = useState('')
  useEffect(() => {
    let active = true, made = null
    setUrl(null); setErr('')
    fetchBlobUrl(src).then((u) => { made = u; if (active) setUrl(u); else URL.revokeObjectURL(u) }).catch((e) => active && setErr(e.message))
    return () => { active = false; if (made) URL.revokeObjectURL(made) }
  }, [src])
  if (err) return <div className={`grid place-items-center text-xs text-slate-500 bg-black/30 rounded ${className}`}>{err}</div>
  if (!url) return <div className={`animate-pulse bg-black/30 rounded ${className}`} />
  return <a href={url} target="_blank" rel="noreferrer"><img src={url} alt={alt} className={`rounded object-contain bg-black/40 ${className}`} /></a>
}

// Evidence gallery; `base` is e.g. /api/violations/VIO-1 or /api/owner/challans/ECH-1
export function Evidence({ base, evidence }) {
  if (!evidence) return null
  const items = []
  for (const k of ['scene_zoom', 'scene', 'pre_crossing']) if (evidence[k]) items.push([k, `${base}/evidence/${k}`])
  ;(evidence.vehicle_crops || []).forEach((_, i) => items.push([`vehicle ${i + 1}`, `${base}/evidence/vehicle_crops?index=${i}`]))
  ;(evidence.plate_crops || []).forEach((_, i) => items.push([`plate ${i + 1}`, `${base}/evidence/plate_crops?index=${i}`]))
  if (!items.length) return <p className="text-xs text-slate-500">No evidence images.</p>
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
      {items.map(([label, src]) => <figure key={src}><AuthImage src={src} alt={label} className="w-full h-32" /><figcaption className="text-[11px] text-slate-400 mt-1">{label.replace('_', ' ')}</figcaption></figure>)}
    </div>
  )
}
