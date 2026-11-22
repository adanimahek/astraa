import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { login } from '../auth.js'

const STREAKS = Array.from({ length: 14 }, (_, i) => ({ top: 8 + ((i * 37) % 84), dur: 5 + ((i * 7) % 9), delay: -((i * 3) % 11), color: i % 3 === 0 ? '#ef4444' : i % 3 === 1 ? '#f8fafc' : '#facc15' }))

export default function Login() {
  const nav = useNavigate()
  const [email, setEmail] = useState(''), [password, setPassword] = useState('')
  const [show, setShow] = useState(false), [error, setError] = useState(''), [loading, setLoading] = useState(false)
  async function onSubmit(e) {
    e.preventDefault(); setError('')
    if (!email || !password) return setError('Please enter email and password')
    setLoading(true)
    try { const u = await login(email, password); nav(u.role === 'Vehicle Owner' ? '/owner' : '/', { replace: true }) } catch (err) { setError(err.message) } finally { setLoading(false) }
  }
  const input = 'w-full rounded-lg bg-white/10 border border-white/20 px-3 py-2.5 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-accent'
  return (
    <div className="relative min-h-screen overflow-hidden bg-gradient-to-br from-[#060d1a] via-[#0b1d3a] to-[#08142a] text-white">
      {STREAKS.map((s, i) => <span key={i} className="streak opacity-70" style={{ top: `${s.top}%`, background: s.color, animationDuration: `${s.dur}s`, animationDelay: `${s.delay}s`, boxShadow: `0 0 14px ${s.color}` }} />)}
      <div className="relative z-10 min-h-screen grid lg:grid-cols-2 items-center gap-8 px-6 lg:px-16">
        <section>
          <h1 className="text-7xl font-extrabold tracking-widest">ASTRA</h1>
          <p className="mt-2 text-xl text-accent font-semibold">Adaptive Signal Timing Reinforcement Agent</p>
          <p className="mt-6 text-lg text-slate-200 max-w-md">Intelligent Traffic Signal Optimization Using AI and SUMO Simulation</p>
          <p className="mt-4 text-sm text-slate-400">Smarter Traffic &nbsp;|&nbsp; Safer Roads &nbsp;|&nbsp; Intelligent Cities</p>
        </section>
        <form onSubmit={onSubmit} noValidate className="w-full max-w-md justify-self-center lg:justify-self-end bg-white/10 backdrop-blur-md border border-white/20 rounded-2xl shadow-2xl p-8">
          <h2 className="text-2xl font-bold text-center">Welcome Back</h2>
          <p className="text-slate-300 mt-1 mb-6 text-center text-sm">Sign in to continue to ASTRA</p>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" autoComplete="username" className={input + ' mb-4'} />
          <div className="relative">
            <input type={show ? 'text' : 'password'} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" autoComplete="current-password" className={input + ' pr-16'} />
            <button type="button" onClick={() => setShow(!show)} className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-accent">{show ? 'Hide' : 'Show'}</button>
          </div>
          {error && <p role="alert" className="text-sm text-red-400 mt-3">{error}</p>}
          <button disabled={loading} className="w-full mt-6 bg-gradient-to-r from-brand to-violet-500 hover:opacity-90 disabled:opacity-60 font-bold rounded-lg py-2.5">{loading ? 'Signing in…' : 'Login'}</button>
          <p className="text-xs text-slate-400 mt-4 text-center">Authorized users and registered vehicle owners only. Accounts are created by the administrator.</p>
        </form>
      </div>
    </div>
  )
}
