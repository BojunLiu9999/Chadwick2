/**
 * useRobotConnection.js
 * 轮询 /api/robot/status，获取机器人连接状态
 * 同时提供 connect / disconnect 方法
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { robotAPI } from '../services/api'

const POLL_INTERVAL = 2000  // 2秒拉一次

export function useRobotConnection() {
  // connection: "disconnected" | "connecting" | "connected" | "ready" | "unknown"
  const [connection, setConnection] = useState('unknown')
  const [lastError, setLastError]   = useState(null)
  const [busy, setBusy]             = useState(false)  // 正在执行 connect/disconnect
  const pollRef = useRef(null)

  // 拉一次状态
  const refresh = useCallback(async () => {
    try {
      const s = await robotAPI.getStatus()
      setConnection(s.connection || (s.connected ? 'connected' : 'disconnected'))
      setLastError(s.last_error || null)
    } catch (e) {
      // 后端挂了或没登录，保持 unknown
      setConnection('unknown')
    }
  }, [])

  // 挂载时立即拉一次 + 启动轮询
  useEffect(() => {
    refresh()
    pollRef.current = setInterval(refresh, POLL_INTERVAL)
    return () => clearInterval(pollRef.current)
  }, [refresh])

  // 点击"连接"按钮
  const connect = useCallback(async () => {
    setBusy(true)
    setLastError(null)
    // 乐观更新：立即显示 connecting，给用户即时反馈
    setConnection('connecting')
    try {
      const s = await robotAPI.connect()
      setConnection(s.connection)
    } catch (e) {
      const msg = typeof e === 'string' ? e : (e?.message || 'Connect failed')
      setLastError(msg)
      setConnection('disconnected')
      throw e
    } finally {
      setBusy(false)
    }
  }, [])

  const disconnect = useCallback(async () => {
    setBusy(true)
    try {
      const s = await robotAPI.disconnect()
      setConnection(s.connection)
    } finally {
      setBusy(false)
    }
  }, [])

  return { connection, lastError, busy, connect, disconnect, refresh }
}