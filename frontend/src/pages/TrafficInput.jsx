import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.js'
import { useDetect } from '../DetectContext.jsx'
import { useSim } from '../SimContext.jsx'
import { card } from '../components.jsx'

export default function TrafficInput() {
  const nav = useNavigate(), {
    setResult, refresh, setSimulationResult, setSimulationError, setSimulationLoading,
  } = useDetect()
  const { dispatch, dispatchVehicles, reset } = useSim()
  const [kind, setKind] = useState('image'), [file, setFile] = useState(null), [url, setUrl] = useState(null)
  const [meta, setMeta] = useState({}), [conf, setConf] = useState(0.5), [intersectionView, setIntersectionView] = useState(false), [simulateTraffic, setSimulateTraffic] = useState(false), [approach, setApproach] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const simulationEnabled = intersectionView || simulateTraffic
  const max = kind === 'image' ? 10 : 200
  const pick = (f) => {
    setError(''); setMeta({})
    if (!f) return
    const okType = kind === 'image' ? /^image\/(jpeg|png)$/.test(f.type) : /\.(mp4|avi|mov)$/i.test(f.name)
    if (!okType) return setError(kind === 'image' ? 'Only JPG or PNG images are supported' : 'Only MP4, AVI or MOV videos are supported')
    if (f.size > max * 1024 * 1024) return setError(`File is larger than ${max} MB`)
    setFile(f); setUrl(URL.createObjectURL(f))
  }
  const switchKind = (k) => { setKind(k); setFile(null); setUrl(null); setMeta({}); setError('') }
  async function run() {
    setBusy(true); setError('')
    if (simulationEnabled) {
      reset()
      setSimulationResult(null)
      setSimulationError('')
      setSimulationLoading(false)
    }
    try {
      const r = await api.detect(kind, file, conf, simulationEnabled)
      setResult(r)
      refresh()
      const emergencyCount = (r.counts?.Ambulance || 0) + (r.counts?.['Fire Truck'] || 0)
      const normalCount = Math.max(0, (kind === 'video' ? r.peak_vehicles : r.total_vehicles) - emergencyCount)
      if (simulationEnabled && normalCount > 0) {
        dispatchVehicles(approach, normalCount)
      }
      if (intersectionView && r.emergency_detected) {
        dispatch(approach)
        setSimulationLoading(true)
        nav('/signal')
        try {
          setSimulationResult(await api.simulateEmergency(r.id, approach))
          refresh()
        } catch (simulationError) {
          setSimulationError(simulationError.message)
        } finally {
          setSimulationLoading(false)
        }
      } else if (simulationEnabled && normalCount > 0) {
        nav('/signal')
      } else {
        nav('/detection')
      }
    }
    catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const tab = (on) => `px-4 py-2 rounded-lg text-sm font-medium border ${on ? 'bg-brand border-brand text-white' : 'border-line text-slate-300 hover:bg-panel'}`
  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-bold">Traffic Data Input</h1><p className="text-slate-400 text-sm">Upload an image or video for vehicle detection</p></div>
      <div className="flex gap-2">
        <button onClick={() => switchKind('image')} className={tab(kind === 'image')}>Upload Image</button>
        <button onClick={() => switchKind('video')} className={tab(kind === 'video')}>Upload Video</button>
        
      </div>
      <section className="grid md:grid-cols-2 gap-4">
        <label onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); pick(e.dataTransfer.files[0]) }}
          className={card + ' border-dashed border-2 flex flex-col items-center justify-center text-center min-h-64 cursor-pointer hover:border-accent'}>
          <p className="text-4xl mb-2">{kind === 'image' ? '🖼️' : '🎬'}</p>
          <p className="font-medium">Drag & drop a {kind} here, or click to browse</p>
          <p className="text-xs text-slate-500 mt-3">{kind === 'image' ? 'JPG, PNG (max 10 MB)' : 'MP4, AVI, MOV (max 200 MB)'}</p>
          <input key={kind} type="file" className="hidden" accept={kind === 'image' ? 'image/jpeg,image/png' : '.mp4,.avi,.mov'} onChange={(e) => pick(e.target.files[0])} />
        </label>
        <div className={card}>
          <p className="font-semibold mb-2">Input Preview</p>
          {!url && <p className="text-sm text-slate-500">Nothing selected yet.</p>}
          {url && kind === 'image' && <img src={url} alt="preview" onLoad={(e) => setMeta({ res: `${e.target.naturalWidth} x ${e.target.naturalHeight}` })} className="rounded-lg max-h-56 mx-auto" />}
          {url && kind === 'video' && <video src={url} controls onLoadedMetadata={(e) => setMeta({ res: `${e.target.videoWidth} x ${e.target.videoHeight}`, dur: `${e.target.duration.toFixed(0)} s` })} className="rounded-lg max-h-56 mx-auto" />}
          {file && <div className="mt-3 text-sm text-slate-300 space-y-0.5"><p>File: {file.name}</p><p>Size: {(file.size / 1048576).toFixed(1)} MB</p>{meta.res && <p>Resolution: {meta.res}</p>}{meta.dur && <p>Duration: {meta.dur}</p>}</div>}
        </div>
      </section>
      <section className={card}>
        <label className="flex items-center gap-4 text-sm">Confidence threshold
          <input type="range" min="0.1" max="0.9" step="0.05" value={conf} onChange={(e) => setConf(+e.target.value)} className="flex-1 max-w-xs" />
          <span className="font-semibold w-10">{conf.toFixed(2)}</span></label>
        <label className="mt-4 flex items-start gap-3 text-sm">
          <input type="checkbox" checked={intersectionView} onChange={(e) => { setIntersectionView(e.target.checked); if (!e.target.checked) setApproach('') }} className="mt-1" />
          <span>Emergency intersection simulation
            <span className="block text-xs text-slate-500 mt-1">When YOLO detects an ambulance or fire truck, SUMO compares fixed-time control with trained Q-learning plus emergency priority. Regular vehicles detected in the same image/video are also added to the Signal-page demo at the selected approach.</span>
          </span>
        </label>
        <label className="mt-4 flex items-start gap-3 text-sm">
          <input type="checkbox" checked={simulateTraffic} onChange={(e) => setSimulateTraffic(e.target.checked)} className="mt-1" />
          <span>Simulate detected regular vehicles in ASTRA adaptive control
            <span className="block text-xs text-slate-500 mt-1">After YOLO detection, dispatch the detected non-emergency vehicle count to the selected approach in the Signal page. The fixed-time and adaptive demos receive the same vehicles for comparison.</span>
          </span>
        </label>
        {simulationEnabled && (
          <label className="mt-4 flex flex-wrap items-center gap-3 text-sm">
            Detected vehicle approach
            <select value={approach} onChange={(e) => setApproach(e.target.value)} className="rounded-lg border border-line bg-bg px-3 py-2 text-white">
              <option value="">Select approach…</option>
              {['north', 'south', 'east', 'west'].map((direction) => <option key={direction} value={direction}>{direction[0].toUpperCase() + direction.slice(1)}</option>)}
            </select>
            <span className="text-xs text-slate-500">Choose based on the camera's road direction; it cannot be inferred reliably without calibration.</span>
          </label>
        )}
        {error && <p role="alert" className="text-sm text-red-400 mt-3">{error}</p>}
        <button disabled={!file || busy || (simulationEnabled && !approach)} onClick={run} className="mt-4 px-5 py-2.5 rounded-lg bg-brand hover:bg-blue-500 disabled:opacity-50 font-semibold">{busy ? (kind === 'video' ? 'Analysing video… this can take a minute' : 'Analysing…') : simulateTraffic ? 'Detect and simulate vehicles →' : intersectionView ? 'Detect and compare Q-learning + priority →' : 'Run YOLO Detection →'}</button>
      </section>
    </div>
  )
}
