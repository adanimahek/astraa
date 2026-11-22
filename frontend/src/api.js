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

const json = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body ?? {}) })
const qs = (params) => { const p = new URLSearchParams(Object.entries(params || {}).filter(([, v]) => v !== '' && v != null)); const s = p.toString(); return s ? '?' + s : '' }

// Authenticated image -> object URL (evidence is never served publicly)
export async function fetchBlobUrl(path) {
  const r = await fetch(BASE + path, { headers: getToken() ? { Authorization: 'Bearer ' + getToken() } : {} })
  if (!r.ok) throw new Error('Image unavailable (' + r.status + ')')
  return URL.createObjectURL(await r.blob())
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
  // ---- e-challan: violations (staff)
  violationConfigExample: () => req('/api/violations/config/example'),
  detectViolationsVideo: (file, config, conf) => { const f = new FormData(); f.append('file', file); f.append('config', config); f.append('conf', conf); return req('/api/violations/detect/video', { method: 'POST', body: f }) },
  detectViolationsSumo: (body) => req('/api/violations/detect/sumo', json('POST', body)),
  violations: (params) => req('/api/violations' + qs(params)),
  reviewQueue: () => req('/api/violations/review/queue'),
  verifyPlate: (id, plate_number, note) => req(`/api/violations/${id}/verify-plate`, json('POST', { plate_number, note })),
  rejectViolation: (id, reason) => req(`/api/violations/${id}/reject`, json('POST', { reason })),
  resolveOwner: (id) => req(`/api/violations/${id}/resolve-owner`, json('POST')),
  // ---- e-challan: challans & admin (staff)
  enforcementSummary: () => req('/api/enforcement/summary'),
  challans: (params) => req('/api/challans' + qs(params)),
  cancelChallan: (n, reason) => req(`/api/challans/${n}/cancel`, json('POST', { reason })),
  fineRules: () => req('/api/challans/config/fines'),
  updateFineRule: (type, body) => req(`/api/challans/config/fines/${type}`, json('PUT', body)),
  seedDemo: () => req('/api/registry/demo/seed', json('POST')),
  // ---- vehicle owner portal
  ownerDashboard: () => req('/api/owner/dashboard'),
  ownerChallans: (status) => req('/api/owner/challans' + qs({ status })),
  ownerNotifications: () => req('/api/owner/notifications'),
  ownerReadAll: () => req('/api/owner/notifications/read-all', json('POST')),
  // ---- simulated payments (FR15)
  payChallan: (n, method, simulate_failure = false) => req(`/api/owner/challans/${n}/pay`, json('POST', { method, simulate_failure })),
  ownerReceipt: (n) => req(`/api/owner/challans/${n}/receipt`),
  ownerPayments: () => req('/api/owner/payments'),
  paymentHistory: () => req('/api/challans/payments/history'),
  runOverdueCheck: () => req('/api/challans/overdue/run', json('POST')),
}
