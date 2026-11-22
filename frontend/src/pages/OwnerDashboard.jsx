import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { Badge, btn, card, Evidence, fmtDate, money, Stat } from '../components.jsx'
import { PayButton, Receipt, PaymentHistory } from './OwnerPayments.jsx'

function ChallanCard({ c, onPaid }) {
  const [open, setOpen] = useState(false)
  const st = c.display_status || c.status
  return (
    <div className={`${card} ${st === 'overdue' ? 'border-red-500/60' : ''}`}>
      <div className="flex flex-wrap items-center gap-3">
        <div className="mr-auto">
          <p className="font-mono text-sm">{c.challan_number} <Badge status={st} /></p>
          <p className="text-xs text-slate-400 mt-1">{c.violation_label} · {c.registration_number} · {fmtDate(c.occurred_at)}</p>
        </div>
        <div className="text-right">
          <p className="text-xl font-bold">{money(c.fine?.amount)}</p>
          <p className={`text-xs ${st === 'overdue' ? 'text-red-300' : 'text-slate-400'}`}>{c.status === 'paid' ? `Paid ${fmtDate(c.payment?.paid_at, false)}` : `Due ${fmtDate(c.due_date, false)}`}</p>
        </div>
        <button onClick={() => setOpen(!open)} className={btn + ' border border-line'}>{open ? 'Hide' : 'Evidence'}</button>
        {c.status === 'unpaid' && <PayButton challan={c} onPaid={onPaid} />}
      </div>
      {open && (
        <div className="mt-3 space-y-2">
          <Evidence base={`/api/owner/challans/${c.challan_number}`} evidence={c.evidence} />
          <p className="text-xs text-slate-400">{c.legal_section} · location: {c.location?.approach} approach ({c.location?.source}){c.fine?.repeat_offence ? ' · repeat offence' : ''}</p>
          {c.payment && <Receipt challanNumber={c.challan_number} />}
        </div>
      )}
    </div>
  )
}

export default function OwnerDashboard() {
  const [d, setD] = useState(null), [challans, setChallans] = useState([]), [notes, setNotes] = useState([])
  const [filter, setFilter] = useState(''), [err, setErr] = useState('')
  const load = useCallback(() => {
    api.ownerDashboard().then(setD).catch((e) => setErr(e.message))
    api.ownerChallans(filter).then(setChallans).catch((e) => setErr(e.message))
    api.ownerNotifications().then(setNotes).catch(() => {})
  }, [filter])
  useEffect(load, [load])
  const s = d?.summary
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">My Vehicles & E-Challans</h1>
      {err && <p className="text-sm text-red-400">{err}</p>}
      {s?.overdue > 0 && <p role="alert" className="rounded-lg border border-red-500/60 bg-red-500/10 px-4 py-3 text-sm text-red-200">You have {s.overdue} overdue challan(s) totalling {money(s.amount_overdue)}. Please pay as soon as possible.</p>}
      <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat icon="🚗" title="Registered vehicles" value={d?.vehicles?.length ?? '–'} />
        <Stat icon="🧾" title="Unpaid challans" value={s ? s.unpaid : '–'} tone={s?.unpaid ? 'text-yellow-300' : 'text-white'} sub={s ? `${money(s.amount_outstanding)} outstanding` : ''} />
        <Stat icon="⏰" title="Overdue" value={s ? s.overdue : '–'} tone={s?.overdue ? 'text-red-400' : 'text-white'} />
        <Stat icon="✅" title="Paid" value={s ? s.paid : '–'} tone="text-emerald-400" sub={s ? money(s.amount_paid) : ''} />
      </section>
      <section className="grid lg:grid-cols-3 gap-4">
        <div className={card + ' lg:col-span-2'}>
          <p className="font-semibold mb-2">My vehicles</p>
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-slate-400"><tr><th className="py-1">Registration</th><th>Vehicle</th><th>Class</th><th>Challans</th><th>Outstanding</th></tr></thead>
            <tbody>{(d?.vehicles || []).map((v) => (
              <tr key={v.registration_number} className="border-t border-line"><td className="py-2 font-mono">{v.registration_number}</td><td>{v.make} {v.model}</td><td>{v.vehicle_class}</td><td>{v.challans}</td><td>{money(v.outstanding)}</td></tr>
            ))}</tbody>
          </table>
        </div>
        <div className={card}>
          <div className="flex items-center mb-2"><p className="font-semibold mr-auto">Notifications {d?.unread_notifications ? <span className="ml-1 text-xs bg-brand rounded-full px-2">{d.unread_notifications}</span> : null}</p>
            {d?.unread_notifications > 0 && <button onClick={() => api.ownerReadAll().then(load)} className="text-xs text-accent">Mark all read</button>}</div>
          <div className="space-y-2 max-h-72 overflow-y-auto">
            {notes.length ? notes.map((n) => (
              <div key={n.notification_id} className={`text-xs rounded p-2 ${n.read ? 'bg-black/20 text-slate-400' : 'bg-brand/15 text-slate-200'}`}>
                <p className="font-semibold">{n.title}</p><p>{n.message}</p><p className="text-[10px] text-slate-500 mt-1">{fmtDate(n.created_at)}</p>
              </div>
            )) : <p className="text-sm text-slate-500">No notifications.</p>}
          </div>
        </div>
      </section>
      <section className="space-y-3">
        <div className="flex flex-wrap gap-2 items-center">
          <p className="font-semibold mr-auto">My challans</p>
          {[['', 'All'], ['unpaid', 'Unpaid'], ['overdue', 'Overdue'], ['paid', 'Paid']].map(([k, l]) => <button key={k} onClick={() => setFilter(k)} className={`${btn} ${filter === k ? 'bg-brand text-white' : 'border border-line text-slate-300'}`}>{l}</button>)}
        </div>
        {challans.length ? challans.map((c) => <ChallanCard key={c.challan_number} c={c} onPaid={load} />) : <p className={card + ' text-sm text-slate-400'}>No challans in this view. Drive safely! 🚦</p>}
      </section>
      <PaymentHistory refreshKey={challans.map((c) => c.status).join()} />
    </div>
  )
}
