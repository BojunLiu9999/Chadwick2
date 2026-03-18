/**
 * components/Header.jsx
 * 顶部导航栏，所有页面共用
 */
import React from 'react'
import { useAuth } from '../context/AuthContext'
import { useNavigate } from 'react-router-dom'

export function Header({ statusPills = [] }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  const isSuper = user?.role === 'supervisor'

  return (
    <header style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '10px 20px',
      background: 'var(--panel)',
      borderBottom: `1px solid ${isSuper ? 'rgba(10,245,160,0.2)' : 'var(--border)'}`,
      position: 'sticky', top: 0, zIndex: 100,
    }}>
      <div style={{
        fontFamily: 'Rajdhani, sans-serif', fontSize: 20, fontWeight: 700,
        letterSpacing: 3, color: isSuper ? 'var(--accent2)' : 'var(--accent)',
      }}>
        CHADWICK <span style={{ color: 'var(--text)', fontWeight: 300 }}>II</span>
        &nbsp;//&nbsp;
        <span style={{ fontSize: 14 }}>{isSuper ? 'SUPERVISOR VIEW' : 'OPERATOR VIEW'}</span>
      </div>

      {/* Status pills */}
      <div style={{ display: 'flex', gap: 12 }}>
        {statusPills.map((p, i) => (
          <StatusPill key={i} label={p.label} color={p.color} />
        ))}
      </div>

      {/* User info */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{
          padding: '3px 10px', borderRadius: 3,
          background: isSuper ? 'rgba(10,245,160,0.1)' : 'rgba(0,200,255,0.1)',
          border: `1px solid ${isSuper ? 'var(--accent2)' : 'var(--accent)'}`,
          color: isSuper ? 'var(--accent2)' : 'var(--accent)',
          fontFamily: 'Share Tech Mono, monospace', fontSize: 10, letterSpacing: 1,
        }}>
          {isSuper ? 'SUPERVISOR' : 'OPERATOR'}
        </span>
        <span style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 11, color: 'var(--dim)' }}>
          {user?.display_name}
        </span>
        <button onClick={handleLogout} style={{
          padding: '4px 12px', borderRadius: 4,
          border: '1px solid var(--border)', background: 'transparent',
          color: 'var(--dim)', fontFamily: 'Share Tech Mono, monospace',
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
    green:  'var(--accent2)',
    blue:   'var(--accent)',
    yellow: 'var(--warn)',
    red:    'var(--danger)',
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

/**
 * components/Panel.jsx
 * 带标题的面板容器
 */
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

/**
 * components/SectionLabel.jsx
 */
export function SectionLabel({ children }) {
  return (
    <div style={{
      fontSize: 10, letterSpacing: 2, textTransform: 'uppercase',
      color: 'var(--dim)', margin: '14px 0 8px',
      fontFamily: 'Share Tech Mono, monospace',
    }}>
      {children}
    </div>
  )
}

/**
 * components/EStop.jsx
 * 紧急停止按钮
 */
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

/**
 * components/Toggle.jsx
 */
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

/**
 * components/TelemetryPanel.jsx
 * 右侧遥测面板（Operator 和 Supervisor 共用）
 */
export function TelemetryPanel({ telemetry, onAddTag, onExport }) {
  const [logEntries, setLogEntries] = React.useState([
    { time: '09:14:18', text: '[INFO] Session started', cls: 'info' },
    { time: '09:14:20', text: '[INFO] Readiness check passed', cls: 'info' },
  ])

  // 暴露给外部添加日志的方法
  React.useEffect(() => {
    TelemetryPanel._addLog = (text, cls = 'cmd') => {
      const t = new Date().toTimeString().slice(0, 8)
      setLogEntries(prev => [...prev, { time: t, text, cls }])
    }
  }, [])

  const logColor = { cmd: 'var(--accent)', info: 'var(--accent2)', warn: 'var(--warn)', err: 'var(--danger)' }

  const motors = telemetry?.motor_loads || {}

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0, height: '100%', overflowY: 'auto' }}>
      <Panel title="Telemetry">
        {/* Battery */}
        <SectionLabel>Battery</SectionLabel>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
          <div style={{ flex: 1, height: 18, background: 'var(--border)', borderRadius: 4, overflow: 'hidden' }}>
            <div style={{
              height: '100%', borderRadius: 4,
              width: `${telemetry?.battery_pct ?? 72}%`,
              background: 'linear-gradient(90deg, var(--accent2), #00ffc8)',
              transition: 'width 0.5s',
            }} />
          </div>
          <span style={{ fontFamily: 'Share Tech Mono, monospace', color: 'var(--accent2)', fontSize: 12, width: 36 }}>
            {(telemetry?.battery_pct ?? 72).toFixed(0)}%
          </span>
        </div>

        {/* Metric cards */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 14 }}>
          {[
            { val: `${(telemetry?.imu_tilt_deg ?? 0.3).toFixed(1)}°`, unit: 'deg', name: 'IMU Tilt' },
            { val: `${(telemetry?.latency_ms ?? 18).toFixed(0)}ms`,   unit: '',    name: 'Latency' },
            { val: `${(telemetry?.core_temp_c ?? 54).toFixed(0)}°`,   unit: 'C',   name: 'Core Temp' },
            { val: `${(telemetry?.signal_dbm ?? -62).toFixed(0)}`,    unit: 'dBm', name: 'Signal' },
          ].map(m => (
            <div key={m.name} style={{
              background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)',
              borderRadius: 6, padding: 10, textAlign: 'center',
            }}>
              <span style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 20, color: 'var(--accent)', display: 'block', lineHeight: 1 }}>{m.val}</span>
              <span style={{ fontSize: 10, color: 'var(--dim)' }}>{m.unit}</span>
              <div style={{ fontSize: 10, color: 'var(--dim)', marginTop: 4, letterSpacing: 1, textTransform: 'uppercase' }}>{m.name}</div>
            </div>
          ))}
        </div>

        {/* Motor loads */}
        <SectionLabel>Motor Load</SectionLabel>
        {Object.entries(motors).map(([name, val]) => (
          <div key={name} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <span style={{ width: 60, color: 'var(--dim)', fontFamily: 'Share Tech Mono, monospace', fontSize: 10 }}>{name}</span>
            <div style={{ flex: 1, height: 6, background: 'var(--border)', borderRadius: 3, overflow: 'hidden' }}>
              <div style={{
                height: '100%', borderRadius: 3,
                width: `${val}%`,
                background: val > 65 ? 'var(--danger)' : val > 50 ? 'var(--warn)' : 'var(--accent2)',
                transition: 'width 0.5s',
              }} />
            </div>
            <span style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'var(--dim)', width: 28, textAlign: 'right' }}>{val}%</span>
          </div>
        ))}
      </Panel>

      {/* Session log */}
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
          <button className="btn-base btn-ok" onClick={() => TelemetryPanel._addLog?.('[INFO] Session resumed', 'info')}
            style={{ flex: 1, padding: '8px 10px', borderRadius: 5, border: '1px solid var(--accent2)', background: 'transparent', color: 'var(--accent2)', fontFamily: 'Exo 2, sans-serif', fontSize: 11, cursor: 'pointer' }}>
            ▶ Start
          </button>
          <button onClick={() => TelemetryPanel._addLog?.('[INFO] Session paused', 'warn')}
            style={{ flex: 1, padding: '8px 10px', borderRadius: 5, border: '1px solid var(--warn)', background: 'transparent', color: 'var(--warn)', fontFamily: 'Exo 2, sans-serif', fontSize: 11, cursor: 'pointer' }}>
            ⏸ Pause
          </button>
          <button onClick={onAddTag}
            style={{ flex: 1, padding: '8px 10px', borderRadius: 5, border: '1px solid var(--dim)', background: 'transparent', color: 'var(--dim)', fontFamily: 'Exo 2, sans-serif', fontSize: 11, cursor: 'pointer' }}>
            🏷 Tag
          </button>
        </div>
      </Panel>
    </div>
  )
}
