import { useCallback, useEffect, useRef, useState } from 'react'

import { robotAPI } from '../services/api'

const POLL_INTERVAL = 2000

export function useRobotConnection() {
  const [connection, setConnection] = useState('unknown')
  const [lastError, setLastError] = useState('')
  const [busy, setBusy] = useState(false)
  const pollRef = useRef(null)

  const refresh = useCallback(async () => {
    try {
      const status = await robotAPI.getStatus()
      setConnection(status.connection || (status.connected ? 'connected' : 'disconnected'))
      setLastError(status.last_error || '')
    } catch (_) {
      setConnection('unknown')
    }
  }, [])

  useEffect(() => {
    refresh()
    pollRef.current = window.setInterval(refresh, POLL_INTERVAL)

    return () => {
      if (pollRef.current) {
        window.clearInterval(pollRef.current)
      }
    }
  }, [refresh])

  const connect = useCallback(async () => {
    setBusy(true)
    setLastError('')
    setConnection('connecting')

    try {
      const status = await robotAPI.connect()
      setConnection(status.connection || 'ready')
      setLastError(status.last_error || '')
      return status
    } catch (error) {
      const message = typeof error === 'string' ? error : error?.message || 'Connect failed'
      setLastError(message)
      setConnection('disconnected')
      throw error
    } finally {
      setBusy(false)
    }
  }, [])

  const disconnect = useCallback(async () => {
    setBusy(true)

    try {
      const status = await robotAPI.disconnect()
      setConnection(status.connection || 'disconnected')
      setLastError(status.last_error || '')
      return status
    } finally {
      setBusy(false)
    }
  }, [])

  return {
    connection,
    lastError,
    busy,
    connect,
    disconnect,
    refresh,
  }
}
