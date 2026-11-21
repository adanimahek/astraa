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
