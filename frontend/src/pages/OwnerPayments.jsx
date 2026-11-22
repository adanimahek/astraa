import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Badge, btn, card, fmtDate, money } from '../components.jsx'

// FR15 – simulated payments. No card / bank details are collected and no real
// payment gateway is contacted.
const METHODS = [['upi', 'UPI'], ['card', 'Card'], ['netbanking', 'Net banking']]

export function PayButton({ challan, onPaid }) {
  const [open, setOpen] = useState(false), [method, setMethod] = useState('upi'), [fail, setFail] = useState(false)
  const [busy, setBusy] = useState(false), [err, setErr] = useState(''), [done, setDone] = useState(null)
  async function pay() {
    setBusy(true); setErr('')
    try { const p = await api.payChallan(challan.challan_number, method, fail); setDone(p); setTimeout(onPaid, 1500) } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  if (!open) return <button onClick={() => setOpen(true)} className={btn + ' bg-emerald-600 text-white'}>Pay {money(challan.fine?.amount)}</button>
  return (
    <div className="w-full mt-3 rounded-lg border border-emerald-600/50 bg-emerald-500/5 p-3 space-y-2 text-sm">
      <p className="font-semibold">Simulated payment · {challan.challan_number} · {money(challan.fine?.amount)}</p>
      <p className="text-xs text-slate-400">Demonstration only – no money is transferred and no card or bank details are requested.</p>
      {done ? (
        <p className="text-emerald-300">Payment successful ✓ Transaction {done.transaction_id} · Receipt {done.receipt_number}</p>
      ) : (
        <>
          <div className="flex flex-wrap gap-2">{METHODS.map(([k, l]) => <button key={k} onClick={() => setMethod(k)} className={`${btn} ${method === k ? 'bg-brand text-white' : 'border border-line'}`}>{l}</button>)}</div>
          <label className="flex items-center gap-2 text-xs text-slate-400"><input type="checkbox" checked={fail} onChange={(e) => setFail(e.target.checked)} />Simulate a declined payment</label>
          <div className="flex gap-2">
            <button disabled={busy} onClick={pay} className={btn + ' bg-emerald-600 text-white'}>{busy ? 'Processing…' : 'Confirm payment'}</button>
            <button onClick={() => { setOpen(false); setErr('') }} className={btn + ' border border-line'}>Cancel</button>
          </div>
        </>
      )}
      {err && <p role="alert" className="text-xs text-red-400">{err}</p>}
    </div>
  )
}

export function Receipt({ challanNumber }) {
  const [r, setR] = useState(null), [err, setErr] = useState('')
  useEffect(() => { api.ownerReceipt(challanNumber).then(setR).catch((e) => setErr(e.message)) }, [challanNumber])
  if (err) return <p className="text-xs text-red-400">{err}</p>
  if (!r) return null
  const rows = [['Receipt no.', r.receipt_number], ['Transaction ID', r.transaction_id], ['Paid on', fmtDate(r.paid_at)], ['Amount', money(r.amount)], ['Method', r.method],
    ['Challan', r.challan_number], ['Vehicle', r.registration_number], ['Violation', r.violation], ['Occurred', fmtDate(r.occurred_at)], ['Owner', r.owner?.name]]
  return (
    <div className="receipt rounded-lg bg-white text-slate-900 p-4 max-w-md">
      <p className="font-bold text-lg">ASTRA e-Challan Payment Receipt</p>
      <p className="text-[11px] text-slate-500 mb-2">{r.disclaimer}</p>
      <table className="text-sm w-full"><tbody>{rows.map(([k, v]) => <tr key={k}><td className="pr-3 py-0.5 text-slate-500">{k}</td><td className="font-medium">{v}</td></tr>)}</tbody></table>
      {r.was_overdue && <p className="text-xs text-red-600 mt-2">Paid after the due date ({fmtDate(r.due_date, false)}).</p>}
      <button onClick={() => window.print()} className="no-print mt-3 px-3 py-1.5 rounded bg-slate-900 text-white text-sm">Print / save as PDF</button>
    </div>
  )
}

export function PaymentHistory({ refreshKey }) {
  const [rows, setRows] = useState([])
  useEffect(() => { api.ownerPayments().then(setRows).catch(() => {}) }, [refreshKey])
  return (
    <div className={card}>
      <p className="font-semibold mb-2">Payment history</p>
      {rows.length ? (
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead className="text-left text-xs text-slate-400"><tr><th className="py-1">Date</th><th>Challan</th><th>Amount</th><th>Method</th><th>Transaction</th><th>Receipt</th><th>Status</th></tr></thead>
          <tbody>{rows.map((p) => (
            <tr key={p.transaction_id} className="border-t border-line"><td className="py-2 text-xs">{fmtDate(p.created_at)}</td><td className="font-mono text-xs">{p.challan_number}</td><td>{money(p.amount)}</td><td className="text-xs">{p.method_label}</td><td className="font-mono text-[11px]">{p.transaction_id}</td><td className="font-mono text-[11px]">{p.receipt_number || '–'}</td><td><Badge status={p.status === 'success' ? 'paid' : 'rejected'} /></td></tr>
          ))}</tbody>
        </table></div>
      ) : <p className="text-sm text-slate-500">No payments yet.</p>}
    </div>
  )
}
