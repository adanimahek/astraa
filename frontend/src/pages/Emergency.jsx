import { Link, useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { BASE } from '../api.js'
import { useDetect } from '../DetectContext.jsx'
import { useSim } from '../SimContext.jsx'
import { card, Stat } from '../components.jsx'

export default function Emergency() {
  const nav = useNavigate(), { result: r, history } = useDetect(), { dispatch, snap } = useSim()
  const [approach, setApproach] = useState('')
  const lastEm = r?.emergency_detected ? r : history.find((h) => h.emergency_detected)
  const sendToSim = () => { dispatch(approach); nav('/signal') }
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">Emergency Priority</h1>
      {lastEm ? (
        <>
          <div className="rounded-xl bg-red-600/20 border border-red-500 p-4 font-bold text-red-300 text-lg">🚨 EMERGENCY VEHICLE DETECTED</div>
          <section className="grid lg:grid-cols-3 gap-4">
            <div className={card + ' lg:col-span-2'}><img src={BASE + lastEm.annotated_url} alt="Emergency detection" className="w-full rounded-lg" /></div>
            <div className={card + ' space-y-2 text-sm'}>
              <p className="font-semibold">Details</p>
              <p>Ambulances: <b>{lastEm.counts.Ambulance || 0}</b></p>
              <p>Fire trucks: <b>{lastEm.counts['Fire Truck'] || 0}</b></p>
              <p>Source: {lastEm.filename}</p>
              <label className="block text-slate-300">Emergency approach
                <select value={approach} onChange={(e) => setApproach(e.target.value)} className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-white">
                  <option value="">Select approach…</option>
                  {['north', 'south', 'east', 'west'].map((direction) => <option key={direction} value={direction}>{direction[0].toUpperCase() + direction.slice(1)}</option>)}
                </select>
              </label>
              <p className="text-xs text-slate-500">Select the road based on the source view. Without camera calibration, the approach cannot be inferred reliably from the uploaded media.</p>
              <button disabled={!approach} onClick={sendToSim} className="w-full mt-3 px-4 py-2.5 rounded-lg bg-red-500 hover:bg-red-400 disabled:opacity-50 font-semibold">Send detected emergency to simulator →</button>
            </div>
          </section>
        </>
      ) : (
        <div className={card + ' text-center py-10'}><p className="text-slate-400 mb-4">No emergency vehicle detected yet. Analyse an image with an ambulance or fire truck.</p><Link to="/input" className="px-4 py-2 rounded-lg bg-brand font-semibold">Go to Traffic Input</Link></div>
      )}
      <section className="grid sm:grid-cols-2 gap-4">
        <Stat icon="⏱️" title="Fixed-time ambulance clearance (demo)" value={snap.f.amb ? snap.f.amb.toFixed(1) + ' s' : '–'} />
        <Stat icon="🚦" title="ASTRA ambulance clearance (demo)" value={snap.a.amb ? snap.a.amb.toFixed(1) + ' s' : '–'} tone="text-accent" />
      </section>
      <section className={card}>
        <p className="font-semibold mb-3">Priority flow</p>
        <div className="grid sm:grid-cols-4 gap-3">{[['Detect', 'YOLO finds an ambulance or fire truck'], ['Select approach', 'Choose north, south, east, or west'], ['Prioritize', 'The ASTRA demo controller favors that approach'], ['Compare', 'Fixed-time remains the baseline']].map(([t, d], i) => (
          <div key={t} className="rounded-lg bg-bg border border-line p-3"><p className="text-accent text-sm font-semibold">{i + 1}. {t}</p><p className="text-xs text-slate-400 mt-1">{d}</p></div>))}</div>
      </section>
    </div>
  )
}
