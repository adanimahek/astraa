import { api } from './api.js'
export async function login(email, password) {
  const d = await api.login(email.trim(), password)
  localStorage.setItem('astra_token', d.token)
  localStorage.setItem('astra_user', JSON.stringify(d.user))
  return d.user
}
export const getUser = () => { try { return localStorage.getItem('astra_token') ? JSON.parse(localStorage.getItem('astra_user')) : null } catch { return null } }
export const logout = () => { localStorage.removeItem('astra_token'); localStorage.removeItem('astra_user') }
