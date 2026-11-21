import { Navigate, Route, Routes } from 'react-router-dom'
import Login from './pages/Login.jsx'
import Layout from './Layout.jsx'
import Dashboard from './pages/Dashboard.jsx'
import TrafficInput from './pages/TrafficInput.jsx'
import Detection from './pages/Detection.jsx'
import Emergency from './pages/Emergency.jsx'
import Signal from './pages/Signal.jsx'
import Reports from './pages/Reports.jsx'
import LiveFeed from './pages/LiveFeed.jsx'
import ManualSumo from './pages/ManualSumo.jsx'
import { getUser } from './auth.js'

const Protected = ({ children }) => (getUser() ? children : <Navigate to="/login" replace />)

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Protected><Layout /></Protected>}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/input" element={<TrafficInput />} />
        <Route path="/detection" element={<Detection />} />
        <Route path="/emergency" element={<Emergency />} />
        <Route path="/signal" element={<Signal />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/live-feed" element={<LiveFeed />} />
        <Route path="/sumo-manual" element={<ManualSumo />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
