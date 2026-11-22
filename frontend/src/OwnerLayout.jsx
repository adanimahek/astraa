import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { getUser, logout } from './auth.js'

// Lightweight shell for the Vehicle Owner role: no operator contexts
// (detection history / simulation) are mounted, so no staff APIs are called.
export default function OwnerLayout() {
  const nav = useNavigate(), user = getUser()
  return (
    <div className="min-h-screen">
      <header className="flex flex-wrap items-center gap-4 px-6 py-3 border-b border-line bg-[#0a1428] text-sm">
        <p className="text-xl font-extrabold tracking-widest text-white mr-2">ASTRA</p>
        <span className="text-slate-400 hidden sm:block mr-auto">E-Challan Owner Portal</span>
        <NavLink to="/owner" end className={({ isActive }) => `px-3 py-1.5 rounded-lg ${isActive ? 'bg-brand text-white' : 'text-slate-300 hover:bg-panel'}`}>🧾 My Challans</NavLink>
        <span><span className="font-medium">{user.name}</span> <span className="text-slate-400">· {user.role}</span></span>
        <button onClick={() => { logout(); nav('/login') }} className="px-3 py-1.5 rounded-lg border border-line hover:bg-panel">Log out</button>
      </header>
      <main className="p-5 md:p-7 max-w-6xl mx-auto"><Outlet /></main>
    </div>
  )
}
