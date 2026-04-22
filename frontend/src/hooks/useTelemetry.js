import { useEffect, useRef, useState } from 'react'

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws/telemetry'

const DEFAULT_TELEMETRY = {
  timestamp: new Date().toISOString(),
  battery_pct: 72,
  imu_tilt_deg: 0.3,
  latency_ms: 18,
  core_temp_c: 54,
  signal_dbm: -62,
  motor_loads: {
    L_HIP: 34,
    R_HIP: 36,
    L_KNEE: 71,
    R_KNEE: 45,
    L_ANKLE: 28,
    R_ANKLE: 31,
  },
  estop_active: false,
  motion_armed: false,
  current_mode: 'mobility_drills',
  system_status: 'connected',
}

function normalizeTelemetry(payload = {}) {
  const merged = {
    ...DEFAULT_TELEMETRY,
    ...payload,
    motor_loads: {
      ...DEFAULT_TELEMETRY.motor_loads,
      ...(payload.motor_loads || {}),
    },
  }

  if (!merged.system_status) {
    if (merged.estop_active) {
      merged.system_status = 'connected'
    } else if (merged.motion_armed) {
      merged.system_status = 'ready'
    } else {
      merged.system_status = 'connected'
    }
  }

  return merged
}

export function useTelemetry() {
  const [telemetry, setTelemetry] = useState(DEFAULT_TELEMETRY)
  const [connected, setConnected] = useState(false)
  const [lastError, setLastError] = useState('')
  const wsRef = useRef(null)
  const retryTimerRef = useRef(null)

  useEffect(() => {
    const token = localStorage.getItem('chadwick_token')
    if (!token) {
      return undefined
    }

    let cancelled = false

    function connect() {
      if (cancelled) {
        return
      }

      const ws = new WebSocket(WS_URL)
      wsRef.current = ws
      setLastError('')

      ws.onopen = () => {
        ws.send(JSON.stringify({ token }))
        setConnected(true)
      }

      ws.onmessage = event => {
        const message = JSON.parse(event.data)

        if (message.error) {
          setConnected(false)
          setLastError(message.error)
          return
        }

        if (message.type === 'telemetry') {
          setTelemetry(normalizeTelemetry(message.data))
        }
      }

      ws.onclose = () => {
        setConnected(false)
        if (!cancelled) {
          retryTimerRef.current = window.setTimeout(connect, 3000)
        }
      }

      ws.onerror = () => {
        setLastError('Telemetry socket error')
        ws.close()
      }
    }

    connect()

    return () => {
      cancelled = true
      if (retryTimerRef.current) {
        window.clearTimeout(retryTimerRef.current)
      }
      wsRef.current?.close()
    }
  }, [])

  return { telemetry, connected, lastError }
}
