/**
 * SharedComponents.jsx
 * 复用组件：顶部栏、面板容器、E-Stop、遥测面板等
 */
import React from 'react'
import { useNavigate } from 'react-router-dom'
import { authAPI, sessionAPI } from '../services/api'
import { useAuth } from '../context/AuthContext'

const ALERT_RULES = {
  core_temp_c: { warning: 60, critical: 70 },
  signal_dbm: { warning: -75 },
  battery_pct: { warning: 20, critical: 10 },
  motor_load: { warning: 65 },
}

function getSystemStatusMeta(status = 'disconnected', wsConnected = false) {
  const key = wsConnected ? status : 'disconnected'
  const config = {
    disconnected: { label: 'Disconnected', color: 'var(--danger)' },
    connecting: { label: 'Connecting', color: 'var(--warn)' },
    connected: { label: 'Connected', color: 'var(--accent)' },
    ready: { label: 'Ready', color: 'var(--accent2)' },
    error: { label: 'Error', color: 'var(--danger)' },
  }
  return config[key] || config.disconnected
}

function getMetricLevel(key, value) {
  if (value == null) return 'normal'

  if (key === 'core_temp_c') {
    if (value >= ALERT_RULES.core_temp_c.critical) return 'critical'
    if (value >= ALERT_RULES.core_temp_c.warning) return 'warning'
  }

  if (key === 'signal_dbm') {
    if (value <= ALERT_RULES.signal_dbm.warning) return 'warning'
  }

  if (key === 'battery_pct') {
    if (value <= ALERT_RULES.battery_pct.critical) return 'critical'
    if (value <= ALERT_RULES.battery_pct.warning) return 'warning'
  }

  return 'normal'
}

function buildTelemetryAlerts(telemetry = {}, wsConnected = false) {
  const alerts = []

  if (!wsConnected) {
    alerts.push({
      key: 'socket-disconnected',
      level: 'critical',
      label: 'Telemetry offline',
      message: 'WebSocket disconnected. Showing latest cached values.',
    })
  }

  const coreLevel = getMetricLevel('core_temp_c', telemetry.core_temp_c)
  if (coreLevel !== 'normal') {
    alerts.push({
      key: 'core-temp',
      level: coreLevel,
      label: coreLevel === 'critical' ? 'Core temperature critical' : 'Core temperature high',
      message: `${(telemetry.core_temp_c ?? 0).toFixed(1)}°C`,
    })
  }

  const signalLevel = getMetricLevel('signal_dbm', telemetry.signal_dbm)
  if (signalLevel !== 'normal') {
    alerts.push({
      key: 'signal',
      level: signalLevel,
      label: 'Signal weak',
      message: `${(telemetry.signal_dbm ?? 0).toFixed(0)} dBm`,
    })
  }

  const batteryLevel = getMetricLevel('battery_pct', telemetry.battery_pct)
  if (batteryLevel !== 'normal') {
    alerts.push({
      key: 'battery',
      level: batteryLevel,
      label: batteryLevel === 'critical' ? 'Battery critical' : 'Battery low',
      message: `${(telemetry.battery_pct ?? 0).toFixed(0)}% remaining`,
    })
  }

  Object.entries(telemetry.motor_loads || {}).forEach(([joint, load]) => {
    if (load >= ALERT_RULES.motor_load.warning) {
      alerts.push({
        key: `motor-${joint}`,
        level: load >= 80 ? 'critical' : 'warning',
        label: `${joint} motor load high`,
        message: `${load}%`,
      })
    }
  })

  if (telemetry.estop_active) {
    alerts.unshift({
      key: 'estop-active',
      level: 'critical',
      label: 'E-STOP active',
      message: 'Motion is disabled until released.',
    })
  }

  return alerts
}

function formatMode(mode = 'mobility_drills') {
  return mode
    .split('_')
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function formatTimestamp(ts) {
  if (!ts) return '--'
  const date = new Date(ts)
  if (Number.isNaN(date.getTime())) return ts
  return `${date.toLocaleDateString()} ${date.toLocaleTimeString()}`
}

function metricColor(level) {
  if (level === 'critical') return 'var(--danger)'
  if (level === 'warning') return 'var(--warn)'
  return 'var(--accent)'
}

function alertAccent(level) {
  if (level === 'critical') return 'var(--danger)'
  if (level === 'warning') return 'var(--warn)'
  return 'var(--accent2)'
}

/**
 * components/Header.jsx
 * 顶部应用栏：标题、状态、用户、退出
 */
export function Header({ statusPills = [] }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = async () => {
    try {
      await authAPI.logout()
    } catch (_) {}
    logout()
    navigate('/login')
  }

  return (
    <header style={{
      height: 56,
      background: 'var(--panel)',
      borderBottom: '1px solid var(--border)',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '0 18px',
      boxShadow: '0 0 18px rgba(0,0,0,0.25)',
      zIndex: 10,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
        <div>
          <div style={{
            fontFamily: 'Rajdhani, sans-serif',
            fontSize: 18,
            fontWeight: 700,
            letterSpacing: 1.5,
            color: 'var(--text)',
            lineHeight: 1,
          }}>
            CHADWICK II <span style={{ color: 'var(--accent)' }}>COMMAND CENTER</span>
          </div>
          <div style={{
            fontFamily: 'Share Tech Mono, monospace',
            fontSize: 10,
            color: 'var(--dim)',
            marginTop: 2,
            letterSpacing: 1.2,
          }}>
            HUMANOID ROBOTICS CONTROL INTERFACE
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {statusPills.map((pill, idx) => (
            <StatusPill key={idx} {...pill} />
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontFamily: 'Rajdhani, sans-serif', fontSize: 13, fontWeight: 600 }}>
            {user?.display_name || 'Unknown User'}
          </div>
          <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'var(--dim)' }}>
            {(user?.role || 'guest').toUpperCase()}
          </div>
        </div>
        <button onClick={handleLogout}
          style={{
            padding: '7px 14px',
            border: '1px solid var(--border)', borderRadius: 6,
            background: 'transparent', color: 'var(--dim)',
            fontFamily: 'Share Tech Mono, monospace',
            fontSize: 10, cursor: 'pointer', letterSpacing: 1,
            transition: 'all 0.2s',
          }}
          onMouseEnter={e => { e.target.style.borderColor = 'var(--danger)'; e.target.style.color = 'var(--danger)' }}
          onMouseLeave={e => { e.target.style.borderColor = 'var(--border)'; e.target.style.color = 'var(--dim)' }}
        >
          ⏏ LOGOUT
        </button>
      </div>
    </header>
  )
}

export function StatusPill({ label, color = 'green' }) {
  const colors = {
    green: 'var(--accent2)',
    blue: 'var(--accent)',
    yellow: 'var(--warn)',
    red: 'var(--danger)',
  }
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 6,
      padding: '4px 12px',
      border: '1px solid var(--border)', borderRadius: 20,
      fontFamily: 'Share Tech Mono, monospace', fontSize: 11,
    }}>
      <span style={{
        width: 7, height: 7, borderRadius: '50%',
        background: colors[color] || color,
        display: 'inline-block',
        animation: color === 'red' ? 'none' : 'blink 1.5s infinite',
      }} />
      {label}
    </div>
  )
}

export function Panel({ title, children, style = {} }) {
  return (
    <div style={{
      background: 'var(--panel)', padding: 16,
      overflowY: 'auto', ...style,
    }}>
      {title && (
        <div style={{
          fontFamily: 'Rajdhani, sans-serif', fontSize: 11, fontWeight: 600,
          letterSpacing: 2, textTransform: 'uppercase',
          color: 'var(--dim)', marginBottom: 14,
          paddingBottom: 8, borderBottom: '1px solid var(--border)',
        }}>
          {title}
        </div>
      )}
      {children}
    </div>
  )
}

export function SectionLabel({ children }) {
  return (
    <div style={{
      fontSize: 10, letterSpacing: 2, textTransform: 'uppercase',
      color: 'var(--dim)', margin: '14px 0 8px',
      fontFamily: 'Share Tech Mono',
    }}>
      {children}
    </div>
  )
}

export function EStop({ onTrigger }) {
  const [active, setActive] = React.useState(false)

  const handleClick = async () => {
    const next = !active
    setActive(next)
    onTrigger?.(next)
  }

  return (
    <button onClick={handleClick} style={{
      width: '100%', padding: '16px',
      background: active
        ? 'linear-gradient(135deg,#000,#2a0000)'
        : 'linear-gradient(135deg,#8b0000,#cc0000)',
      border: '2px solid var(--danger)',
      borderRadius: 8, color: active ? 'var(--danger)' : '#fff',
      fontFamily: 'Rajdhani, sans-serif',
      fontSize: active ? 16 : 18, fontWeight: 700, letterSpacing: 2,
      cursor: 'pointer',
      boxShadow: 'var(--glow-red)',
      transition: 'all 0.1s', marginBottom: 16,
    }}>
      {active ? '✓ E-STOP ACTIVE' : (
        <>
          <div style={{ fontSize: 10, opacity: 0.7, letterSpacing: 3, marginBottom: 2 }}>SOFTWARE</div>
          E-STOP
        </>
      )}
    </button>
  )
}

export function Toggle({ on, onChange, disabled = false }) {
  return (
    <div
      onClick={() => !disabled && onChange?.(!on)}
      style={{
        width: 40, height: 22,
        background: on ? 'var(--accent2)' : 'var(--border)',
        borderRadius: 11, position: 'relative',
        cursor: disabled ? 'not-allowed' : 'pointer',
        transition: 'background 0.3s',
        opacity: disabled ? 0.4 : 1,
        flexShrink: 0,
      }}
    >
      <div style={{
        width: 16, height: 16, borderRadius: '50%', background: '#fff',
        position: 'absolute', top: 3,
        left: on ? 21 : 3,
        transition: 'left 0.3s',
      }} />
    </div>
  )
}

function MetricCard({ name, value, unit, level = 'normal' }) {
  return (
    <div style={{
      background: 'rgba(255,255,255,0.02)',
      border: `1px solid ${level === 'normal' ? 'var(--border)' : metricColor(level)}`,
      borderRadius: 6,
      padding: 10,
      textAlign: 'center',
      boxShadow: level === 'normal' ? 'none' : `0 0 12px color-mix(in srgb, ${metricColor(level)} 24%, transparent)`,
    }}>
      <span style={{
        fontFamily: 'Share Tech Mono, monospace',
        fontSize: 20,
        color: metricColor(level),
        display: 'block',
        lineHeight: 1,
      }}>
        {value}
      </span>
      <span style={{ fontSize: 10, color: 'var(--dim)' }}>{unit}</span>
      <div style={{ fontSize: 10, color: 'var(--dim)', marginTop: 4, letterSpacing: 1, textTransform: 'uppercase' }}>
        {name}
      </div>
    </div>
  )
}

function AlertItem({ level, label, message }) {
  return (
    <div style={{
      border: `1px solid ${alertAccent(level)}`,
      borderRadius: 6,
      padding: '8px 10px',
      marginBottom: 8,
      background: 'rgba(255,255,255,0.02)',
    }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        gap: 8,
        fontFamily: 'Rajdhani, sans-serif',
        fontWeight: 700,
        letterSpacing: 0.8,
        color: alertAccent(level),
      }}>
        <span>{label}</span>
        <span style={{ fontSize: 11 }}>{level.toUpperCase()}</span>
      </div>
      <div style={{ marginTop: 4, color: 'var(--text)', fontSize: 11 }}>{message}</div>
    </div>
  )
}

export function TelemetryPanel({ telemetry, connected, onAddTag, onExport }) {
  const [logEntries, setLogEntries] = React.useState([
    { time: '09:14:18', text: '[INFO] Session started', cls: 'info' },
    { time: '09:14:20', text: '[INFO] Readiness check passed', cls: 'info' },
  ])
  const seenAlertsRef = React.useRef(new Set())

  React.useEffect(() => {
    TelemetryPanel._addLog = (text, cls = 'cmd') => {
      const t = new Date().toTimeString().slice(0, 8)
      setLogEntries(prev => [...prev, { time: t, text, cls }].slice(-80))
    }

    return () => {
      TelemetryPanel._addLog = undefined
    }
  }, [])

  const alerts = React.useMemo(
    () => buildTelemetryAlerts(telemetry, connected),
    [telemetry, connected],
  )

  React.useEffect(() => {
    alerts.forEach(alert => {
      if (!seenAlertsRef.current.has(alert.key)) {
        TelemetryPanel._addLog?.(`[WARN] ${alert.label}: ${alert.message}`, alert.level === 'critical' ? 'err' : 'warn')
        seenAlertsRef.current.add(alert.key)
      }
    })
  }, [alerts])

  const logColor = { cmd: 'var(--accent)', info: 'var(--accent2)', warn: 'var(--warn)', err: 'var(--danger)' }
  const motors = telemetry?.motor_loads || {}
  const statusMeta = getSystemStatusMeta(telemetry?.system_status, connected)
  const batteryLevel = getMetricLevel('battery_pct', telemetry?.battery_pct)

  const metricCards = [
    {
      name: 'IMU Tilt',
      value: `${(telemetry?.imu_tilt_deg ?? 0.3).toFixed(1)}°`,
      unit: 'deg',
      level: 'normal',
    },
    {
      name: 'Latency',
      value: `${(telemetry?.latency_ms ?? 18).toFixed(0)}ms`,
      unit: '',
      level: 'normal',
    },
    {
      name: 'Core Temp',
      value: `${(telemetry?.core_temp_c ?? 54).toFixed(1)}°`,
      unit: 'C',
      level: getMetricLevel('core_temp_c', telemetry?.core_temp_c),
    },
    {
      name: 'Signal',
      value: `${(telemetry?.signal_dbm ?? -62).toFixed(0)}`,
      unit: 'dBm',
      level: getMetricLevel('signal_dbm', telemetry?.signal_dbm),
    },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0, height: '100%', overflowY: 'auto' }}>
      <Panel title="Telemetry">
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 10,
          padding: '10px 12px',
          borderRadius: 6,
          border: `1px solid ${statusMeta.color}`,
          marginBottom: 12,
        }}>
          <div>
            <div style={{ fontFamily: 'Rajdhani, sans-serif', fontSize: 14, fontWeight: 700, color: statusMeta.color }}>
              {statusMeta.label}
            </div>
            <div style={{ fontSize: 11, color: 'var(--dim)' }}>
              Mode: {formatMode(telemetry?.current_mode)}
            </div>
          </div>
          <div style={{ textAlign: 'right', fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'var(--dim)' }}>
            Updated<br />{formatTimestamp(telemetry?.timestamp)}
          </div>
        </div>

        <SectionLabel>Active alerts</SectionLabel>
        {alerts.length ? alerts.map(alert => (
          <AlertItem key={alert.key} {...alert} />
        )) : (
          <div style={{
            padding: '9px 10px',
            border: '1px solid var(--accent2)',
            borderRadius: 6,
            color: 'var(--accent2)',
            fontSize: 11,
            marginBottom: 12,
          }}>
            No abnormal telemetry alerts.
          </div>
        )}

        <SectionLabel>Battery</SectionLabel>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
          <div style={{ flex: 1, height: 18, background: 'var(--border)', borderRadius: 4, overflow: 'hidden' }}>
            <div style={{
              height: '100%',
              borderRadius: 4,
              width: `${Math.max(0, Math.min(100, telemetry?.battery_pct ?? 72))}%`,
              background: batteryLevel === 'critical'
                ? 'linear-gradient(90deg, #a80000, var(--danger))'
                : batteryLevel === 'warning'
                  ? 'linear-gradient(90deg, #7a5200, var(--warn))'
                  : 'linear-gradient(90deg, var(--accent2), #00ffc8)',
              transition: 'width 0.5s',
            }} />
          </div>
          <span style={{
            fontFamily: 'Share Tech Mono, monospace',
            color: batteryLevel === 'normal' ? 'var(--accent2)' : alertAccent(batteryLevel),
            fontSize: 12,
            width: 36,
          }}>
            {(telemetry?.battery_pct ?? 72).toFixed(0)}%
          </span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 14 }}>
          {metricCards.map(card => (
            <MetricCard key={card.name} {...card} />
          ))}
        </div>

        <SectionLabel>Robot state</SectionLabel>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 14 }}>
          {[
            { name: 'Motion', value: telemetry?.motion_armed ? 'ARMED' : 'DISARMED', color: telemetry?.motion_armed ? 'var(--accent2)' : 'var(--warn)' },
            { name: 'E-Stop', value: telemetry?.estop_active ? 'ACTIVE' : 'CLEAR', color: telemetry?.estop_active ? 'var(--danger)' : 'var(--accent2)' },
          ].map(item => (
            <div key={item.name} style={{ border: '1px solid var(--border)', borderRadius: 6, padding: 10 }}>
              <div style={{ fontSize: 10, color: 'var(--dim)', textTransform: 'uppercase', marginBottom: 5 }}>{item.name}</div>
              <div style={{ fontFamily: 'Share Tech Mono, monospace', color: item.color }}>{item.value}</div>
            </div>
          ))}
        </div>

        <SectionLabel>Motor Load</SectionLabel>
        {Object.entries(motors).map(([name, val]) => {
          const level = val >= 80 ? 'critical' : val >= 65 ? 'warning' : 'normal'
          return (
            <div key={name} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <span style={{ width: 60, color: 'var(--dim)', fontFamily: 'Share Tech Mono, monospace', fontSize: 10 }}>{name}</span>
              <div style={{ flex: 1, height: 6, background: 'var(--border)', borderRadius: 3, overflow: 'hidden' }}>
                <div style={{
                  height: '100%', borderRadius: 3,
                  width: `${val}%`,
                  background: level === 'critical' ? 'var(--danger)' : level === 'warning' ? 'var(--warn)' : 'var(--accent2)',
                  transition: 'width 0.5s',
                }} />
              </div>
              <span style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: level === 'normal' ? 'var(--dim)' : alertAccent(level), width: 28, textAlign: 'right' }}>{val}%</span>
            </div>
          )
        })}
      </Panel>

      <Panel title="Session Log" style={{ flex: 1 }}>
        <div style={{
          background: '#000', border: '1px solid var(--border)', borderRadius: 6,
          padding: 10, height: 180, overflowY: 'auto',
          fontFamily: 'Share Tech Mono, monospace', fontSize: 10, lineHeight: 1.7,
        }}>
          {logEntries.map((e, i) => (
            <div key={i} style={{ display: 'flex', gap: 8 }}>
              <span style={{ color: 'var(--dim)' }}>{e.time}</span>
              <span style={{ color: logColor[e.cls] || 'var(--text)' }}>{e.text}</span>
            </div>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
          <button
            className="btn-base btn-ok"
            onClick={async () => {
              try {
                await sessionAPI.start(telemetry?.current_mode || 'mobility_drills')
                TelemetryPanel._addLog?.('[INFO] Session started', 'info')
              } catch {
                TelemetryPanel._addLog?.('[ERR] Session start failed', 'err')
              }
            }}
            style={{ flex: 1, padding: '8px 10px', borderRadius: 5, border: '1px solid var(--accent2)', background: 'transparent', color: 'var(--accent2)', fontFamily: 'Exo 2, sans-serif', fontSize: 11, cursor: 'pointer' }}>
            ▶ Start
          </button>
          <button
            onClick={async () => {
              try {
                await sessionAPI.stop()
                TelemetryPanel._addLog?.('[INFO] Session stopped', 'warn')
              } catch {
                TelemetryPanel._addLog?.('[ERR] Session stop failed', 'err')
              }
            }}
            style={{ flex: 1, padding: '8px 10px', borderRadius: 5, border: '1px solid var(--warn)', background: 'transparent', color: 'var(--warn)', fontFamily: 'Exo 2, sans-serif', fontSize: 11, cursor: 'pointer' }}>
            ⏸ Stop
          </button>
          <button onClick={onAddTag}
            style={{ flex: 1, padding: '8px 10px', borderRadius: 5, border: '1px solid var(--dim)', background: 'transparent', color: 'var(--dim)', fontFamily: 'Exo 2, sans-serif', fontSize: 11, cursor: 'pointer' }}>
            🏷 Tag
          </button>
        </div>
        {onExport && (
          <button
            onClick={onExport}
            style={{
              width: '100%',
              marginTop: 8,
              padding: '8px 10px',
              borderRadius: 5,
              border: '1px solid var(--accent)',
              background: 'transparent',
              color: 'var(--accent)',
              fontFamily: 'Exo 2, sans-serif',
              fontSize: 11,
              cursor: 'pointer',
            }}
          >
            ⤓ Export Log
          </button>
        )}
      </Panel>
    </div>
  )
}
