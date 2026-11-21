export const BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/+$/, '')
export const getToken = () => localStorage.getItem('astra_token')

async function req(path, opts = {}) {
  const headers = { ...(opts.headers || {}) }
  if (getToken()) headers.Authorization = 'Bearer ' + getToken()
  let r
  try { r = await fetch(BASE + path, { ...opts, headers }) }
  catch { throw new Error('Cannot reach the backend. Is it running on ' + BASE + '?') }
  if (r.status === 401 && path !== '/api/auth/login') { localStorage.clear(); window.location.href = '/login'; throw new Error('Session expired') }
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : r.status === 422 ? 'Please check the entered values' : 'Request failed (' + r.status + ')')
  return data
}

export const api = {
  login: (email, password) => req('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) }),
  health: () => req('/api/health'),
  history: () => req('/api/detect/history?limit=50'),
  simulationComparison: () => req('/api/simulation/comparison'),
  runManualSimulation: (scenario) => req('/api/simulation/manual', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(scenario) }),
  liveFeedStatus: () => req('/api/live-feed/status'),
  liveFeedStart: () => req('/api/live-feed/start', { method: 'POST' }),
  liveFeedStop: () => req('/api/live-feed/stop', { method: 'POST' }),
  detect: (kind, file, conf, intersectionView = false) => { const f = new FormData(); f.append('file', file); f.append('conf', conf); f.append('intersection_view', intersectionView); return req('/api/detect/' + kind, { method: 'POST', body: f }) },
  simulateEmergency: (detectionId, approach) => { const f = new FormData(); f.append('detection_id', detectionId); f.append('approach', approach); return req('/api/detect/simulate/emergency', { method: 'POST', body: f }) },
}
