import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { getUser } from '../auth.js'
import { Badge, btn, card, Evidence, fmtDate, input, money, Stat } from '../components.jsx'

function DailyBars({ daily }) {
  const max = Math.max(1, ...daily.map((d) => d.violations))
  return (
    <div className="flex items-end gap-1 h-32" role="img" aria-label="Violations and challans per day">
      {daily.map((d) => (
        <div key={d.date} className="flex-1 flex flex-col items-center justify-end h-full" title={`${d.date}: ${d.violations} violations, ${d.challans} challans`}>
          <div className="w-full flex items-end gap-px h-full">
            <div className="flex-1 bg-sky-500/70 rounded-t" style={{ height: `${(d.violations / max) * 100}%` }} />
            <div className="flex-1 bg-violet-500/70 rounded-t" style={{ height: `${(d.challans / max) * 100}%` }} />
          </div>
          <span className="text-[9px] text-slate-500 mt-1">{d.date.slice(8)}</span>
        </div>
      ))}
    </div>
  )
}

function FineRules({ isAdmin }) {
  const [rules, setRules] = useState([]), [edit, setEdit] = useState({}), [msg, setMsg] = useState('')
  const load = () => api.fineRules().then(setRules).catch((e) => setMsg(e.message))
  useEffect(() => { load() }, [])
  async function save(r) {
    setMsg('')
    try { await api.updateFineRule(r.violation_type, edit[r.violation_type]); setEdit({}); setMsg('Fine rule updated'); load() } catch (e) { setMsg(e.message) }
  }
  return (
    <div className={card}>
      <p className="font-semibold mb-2">Fine configuration</p>
      {rules.map((r) => {
        const e = edit[r.violation_type] || {}
        const set = (k) => (ev) => setEdit({ ...edit, [r.violation_type]: { ...e, [k]: Number(ev.target.value) } })
        return (
          <div key={r.violation_type} className="text-sm space-y-2">
            <p>{r.label} <span className="text-xs text-slate-500">· {r.legal_section} · v{r.version}</span></p>
            <div className="flex flex-wrap gap-3 items-center">
              <label className="text-slate-400">Fine ₹<input type="number" disabled={!isAdmin} defaultValue={r.amount} onChange={set('amount')} className={input + ' w-24 ml-1'} /></label>
              <label className="text-slate-400">Repeat ₹<input type="number" disabled={!isAdmin} defaultValue={r.repeat_amount} onChange={set('repeat_amount')} className={input + ' w-24 ml-1'} /></label>
              <label className="text-slate-400">Due in<input type="number" disabled={!isAdmin} defaultValue={r.due_days} onChange={set('due_days')} className={input + ' w-16 mx-1'} />days</label>
              {isAdmin && <button disabled={!edit[r.violation_type]} onClick={() => save(r)} className={btn + ' bg-brand text-white'}>Save</button>}
            </div>
          </div>
        )
      })}
      {msg && <p className="text-xs text-slate-300 mt-2">{msg}</p>}
    </div>
  )
}

function ChallanRow({ c, isAdmin, onChange }) {
  const [open, setOpen] = useState(false), [reason, setReason] = useState(''), [err, setErr] = useState('')
  const st = c.display_status || c.status
  return (
    <>
      <tr className="border-t border-line hover:bg-white/5 cursor-pointer" onClick={() => setOpen(!open)}>
        <td className="py-2 pr-3 font-mono text-xs">{c.challan_number}</td>
        <td className="pr-3 font-mono">{c.registration_number}</td>
        <td className="pr-3 text-xs">{c.owner?.name}</td>
        <td className="pr-3">{money(c.fine?.amount)}{c.fine?.repeat_offence && <span className="text-[10px] text-orange-300 ml-1">repeat</span>}</td>
        <td className="pr-3 text-xs">{fmtDate(c.issued_at, false)}</td>
        <td className="pr-3 text-xs">{fmtDate(c.due_date, false)}</td>
        <td><Badge status={st} /></td>
      </tr>
      {open && (
        <tr className="bg-black/20"><td colSpan={7} className="p-3 space-y-3">
          <Evidence base={`/api/violations/${c.violation_id}`} evidence={c.evidence} />
          <p className="text-xs text-slate-300">{c.violation_label} · {c.legal_section} · occurred {fmtDate(c.occurred_at)} · violation {c.violation_id}</p>
          {c.payment && <p className="text-xs text-emerald-300">Paid {money(c.payment.amount)} on {fmtDate(c.payment.paid_at)} · txn {c.payment.transaction_id} · receipt {c.payment.receipt_number}</p>}
          {isAdmin && c.status === 'unpaid' && (
            <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
              <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Cancellation reason" className={input + ' w-64'} />
              <button disabled={reason.length < 3} onClick={async () => { try { await api.cancelChallan(c.challan_number, reason); onChange() } catch (e) { setErr(e.message) } }} className={btn + ' bg-red-600/80 text-white'}>Cancel challan</button>
            </div>
          )}
          {err && <p className="text-xs text-red-400">{err}</p>}
        </td></tr>
      )}
    </>
  )
}

export default function Challans() {
  const isAdmin = getUser()?.role === 'Administrator'
  const [sum, setSum] = useState(null), [list, setList] = useState({ total: 0, items: [] })
  const [status, setStatus] = useState(''), [q, setQ] = useState(''), [err, setErr] = useState(''), [seedMsg, setSeedMsg] = useState('')
  const load = useCallback(() => {
    api.enforcementSummary().then(setSum).catch((e) => setErr(e.message))
    api.challans({ status, q, limit: 100 }).then(setList).catch((e) => setErr(e.message))
  }, [status, q])
  useEffect(load, [load])
  const c = sum?.challans, v = sum?.violations, p = sum?.payments
  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold mr-auto">E-Challan Management</h1>
        {isAdmin && <button onClick={async () => { try { const r = await api.runOverdueCheck(); setSeedMsg(`Overdue check: ${r.flagged} challan(s) newly flagged`); load() } catch (e) { setSeedMsg(e.message) } }} className={btn + ' border border-line'}>Run overdue check</button>}
        {isAdmin && <button onClick={async () => { try { const r = await api.seedDemo(); setSeedMsg(`Demo data: ${r.total_owners} owners, ${r.total_vehicles} vehicles (logins owner1…${r.total_owners}@example.com)`); load() } catch (e) { setSeedMsg(e.message) } }} className={btn + ' border border-line'}>Seed demo owners & vehicles</button>}
      </div>
      {seedMsg && <p className="text-xs text-slate-300">{seedMsg}</p>}
      {err && <p className="text-sm text-red-400">{err}</p>}
      <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat icon="🚨" title="Violations" value={v?.total ?? '–'} sub={v ? `${v.pending_review} need review · ${v.unregistered} unregistered` : ''} />
        <Stat icon="🧾" title="Challans issued" value={c?.total_challans ?? '–'} sub={c ? `${c.unpaid} unpaid · ${c.paid} paid · ${c.cancelled} cancelled` : ''} />
        <Stat icon="💰" title="Collected" value={money(c?.amount_paid)} tone="text-emerald-400" sub={p ? `${p.count} payment(s)` : ''} />
        <Stat icon="⏰" title="Overdue" value={c?.overdue ?? '–'} tone={c?.overdue ? 'text-red-400' : 'text-white'} sub={c ? `${money(c.amount_overdue)} overdue · ${money(c.amount_outstanding)} outstanding` : ''} />
      </section>
      <section className="grid lg:grid-cols-3 gap-4">
        <div className={card + ' lg:col-span-2'}>
          <p className="font-semibold mb-2">Last 14 days <span className="text-xs font-normal text-sky-400 ml-2">■ violations</span><span className="text-xs font-normal text-violet-400 ml-2">■ challans</span></p>
          {sum && <DailyBars daily={sum.daily} />}
        </div>
        <div className={card}>
          <p className="font-semibold mb-2">Top offenders</p>
          {sum?.top_offenders?.length ? sum.top_offenders.map((o) => <p key={o.registration_number} className="flex justify-between text-sm py-1 border-b border-line/50"><span className="font-mono">{o.registration_number}</span><span>{o.challans}</span></p>) : <p className="text-sm text-slate-500">None yet</p>}
        </div>
      </section>
      <section className="grid lg:grid-cols-2 gap-4">
        <FineRules isAdmin={isAdmin} />
        <div className={card}>
          <p className="font-semibold mb-2">Payments <span className="text-xs font-normal text-slate-500">(simulated)</span></p>
          {p ? (
            <div className="text-sm space-y-1">
              <p>{p.count} successful · {p.failed} declined · {p.overdue_payments} paid after due date</p>
              {Object.entries(p.by_method).map(([m, amt]) => <p key={m} className="flex justify-between border-b border-line/50 py-1"><span className="uppercase text-xs text-slate-400">{m}</span><span>{money(amt)}</span></p>)}
              <p className="flex justify-between pt-1 font-semibold"><span>Total collected</span><span className="text-emerald-400">{money(p.total_collected)}</span></p>
            </div>
          ) : <p className="text-sm text-slate-500">–</p>}
        </div>
      </section>
      <div className={card}>
        <div className="flex flex-wrap gap-2 mb-3">
          {[['', 'All'], ['unpaid', 'Unpaid'], ['overdue', 'Overdue'], ['paid', 'Paid'], ['cancelled', 'Cancelled']].map(([k, l]) => <button key={k} onClick={() => setStatus(k)} className={`${btn} ${status === k ? 'bg-brand text-white' : 'border border-line text-slate-300'}`}>{l}</button>)}
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search plate / challan no." className={input + ' ml-auto w-56'} />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-slate-400"><tr><th className="py-2">Challan</th><th>Vehicle</th><th>Owner</th><th>Fine</th><th>Issued</th><th>Due</th><th>Status</th></tr></thead>
            <tbody>{list.items.map((ch) => <ChallanRow key={ch.challan_number} c={ch} isAdmin={isAdmin} onChange={load} />)}</tbody>
          </table>
          {list.items.length === 0 && <p className="text-sm text-slate-500 py-4 text-center">No challans in this view.</p>}
        </div>
      </div>
    </div>
  )
}
