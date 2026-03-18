/**
 * useTelemetry.js
 * 自定义 Hook：连接 WebSocket，实时接收遥测数据
 *
 * 使用方式：
 *   const { telemetry, connected } = useTelemetry()
 *   // telemetry.battery_pct, telemetry.motor_loads, ...
 */
import { useState, useEffect, useRef } from 'react'

const WS_URL = 'ws://localhost:8000/ws/telemetry'

// 默认初始值（WebSocket连接前显示）
const DEFAULT_TELEMETRY = {
  battery_pct:   72,
  imu_tilt_deg:  0.3,
  latency_ms:    18,
  core_temp_c:   54,
  signal_dbm:    -62,
  motor_loads:   { L_HIP: 34, R_HIP: 36, L_KNEE: 71, R_KNEE: 45, L_ANKLE: 28, R_ANKLE: 31 },
  estop_active:  false,
  motion_armed:  false,
}

export function useTelemetry() {
  const [telemetry, setTelemetry] = useState(DEFAULT_TELEMETRY)
  const [connected, setConnected] = useState(false)
  const wsRef = useRef(null)

  useEffect(() => {
    const token = localStorage.getItem('chadwick_token')
    if (!token) return

    function connect() {
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onopen = () => {
        // 连接后立即发送 Token 验证
        ws.send(JSON.stringify({ token }))
        setConnected(true)
      }

      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data)
        if (msg.type === 'telemetry') {
          setTelemetry(msg.data)
        }
      }

      ws.onclose = () => {
        setConnected(false)
        // 3秒后重连
        setTimeout(connect, 3000)
      }

      ws.onerror = () => {
        ws.close()
      }
    }

    connect()

    return () => {
      wsRef.current?.close()
    }
  }, [])

  return { telemetry, connected }
}
