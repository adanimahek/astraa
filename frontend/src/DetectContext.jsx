import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api } from './api.js'
const Ctx = createContext(null)
export const useDetect = () => useContext(Ctx)
export function DetectProvider({ children }) {
  const [result, setResult] = useState(null), [history, setHistory] = useState([])
  const [simulationResult, setSimulationResult] = useState(null)
  const [simulationError, setSimulationError] = useState('')
  const [simulationLoading, setSimulationLoading] = useState(false)
  const [historyError, setHistoryError] = useState(''), [historyLoading, setHistoryLoading] = useState(false)
  const refresh = useCallback(async () => {
    setHistoryLoading(true)
    try {
      setHistory(await api.history())
      setHistoryError('')
    } catch (error) {
      setHistoryError(error.message)
    } finally {
      setHistoryLoading(false)
    }
  }, [])
  useEffect(() => { refresh() }, [refresh])
  return <Ctx.Provider value={{
    result, setResult, history, refresh, historyError, historyLoading,
    simulationResult, setSimulationResult, simulationError, setSimulationError,
    simulationLoading, setSimulationLoading,
  }}>{children}</Ctx.Provider>
}
