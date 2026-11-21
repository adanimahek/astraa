import { useEffect, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { getUser, logout } from './auth.js'
import { api } from './api.js'
import { SimProvider } from './SimContext.jsx'
import { DetectProvider } from './DetectContext.jsx'

const NAV = [['/', '🏠', 'Dashboard'], ['/input', '📥', 'Traffic Input'], ['/detection', '🎯', 'Vehicle Detection'], ['/signal', '🚦', 'AI Signal Control'], ['/emergency', '🚑', 'Emergency Priority'], ['/sumo-manual', '🛣️', 'Manual SUMO'], ['/reports', '📄', 'Reports'], ['/live-feed', '📹', 'Live Feed']]
// const SOON = [['🛣️', 'SUMO Simulation'], ['🧪', 'Scenario Testing'], ['📈', 'Analytics'], ['⚙️', 'Settings']]

export default function Layout() {
  const nav = useNavigate(), user = getUser()
  const [online, setOnline] = useState(null), [now, setNow] = useState(new Date())
  useEffect(() => {
    const ping = () => api.health().then(() => setOnline(true)).catch(() => setOnline(false))
    ping(); const a = setInterval(ping, 15000), b = setInterval(() => setNow(new Date()), 1000)
    return () => { clearInterval(a); clearInterval(b) }
  }, [])
  return (
    <DetectProvider><SimProvider>
      <div className="min-h-screen md:flex">
        <aside className="md:w-60 shrink-0 bg-[#0a1428] border-b md:border-b-0 md:border-r border-line flex md:flex-col">
          <div className="p-5 hidden md:block"><p className="text-2xl font-extrabold tracking-widest text-white">ASTRA</p><p className="text-[11px] text-slate-400 mt-1">Adaptive Signal Timing Reinforcement Agent</p></div>
          <nav className="flex md:flex-col gap-1 p-2 md:p-3 md:flex-1 overflow-x-auto">
            {NAV.map(([to, icon, label]) => (
              <NavLink key={to} to={to} end className={({ isActive }) => `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium whitespace-nowrap ${isActive ? 'bg-brand text-white' : 'text-slate-300 hover:bg-panel'}`}><span>{icon}</span>{label}</NavLink>
            ))}
            {/* {SOON.map(([icon, label]) => (
              <div key={label} title="Coming soon" className="hidden md:flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-slate-600 cursor-not-allowed"><span>{icon}</span>{label}<span className="ml-auto text-[10px] border border-slate-700 rounded px-1">soon</span></div>
            ))} */}
          </nav>
        </aside>
        <div className="flex-1 min-w-0">
          <header className="flex items-center justify-end gap-5 px-6 py-3 border-b border-line bg-[#0a1428] text-sm">
            <span className="flex items-center gap-2"><span className={`w-2 h-2 rounded-full ${online ? 'bg-emerald-400' : online === false ? 'bg-red-500' : 'bg-slate-500'}`} />{online ? 'System Online' : online === false ? 'Backend Offline' : 'Checking…'}</span>
            <span className="text-slate-400 hidden sm:block">{now.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })} {now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}</span>
            <span><span className="font-medium">{user.name}</span> <span className="text-slate-400">· {user.role}</span></span>
            <button onClick={() => { logout(); nav('/login') }} className="px-3 py-1.5 rounded-lg border border-line hover:bg-panel">Log out</button>
          </header>
          <main className="p-5 md:p-7 max-w-6xl"><Outlet /></main>
        </div>
      </div>
    </SimProvider></DetectProvider>
  )
}
