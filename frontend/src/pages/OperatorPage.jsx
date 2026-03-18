/**
 * OperatorPage.jsx
 * 操作员界面 — 遥控、模式切换、遥测监控
 * 安全参数为只读（由 Supervisor 设置）
 */
import React, { useState, useEffect } from 'react'
import { Header, Panel, SectionLabel, EStop, Toggle, TelemetryPanel } from '../components/SharedComponents'
import { robotAPI, sessionAPI } from '../services/api'
import { useTelemetry } from '../hooks/useTelemetry'

const MODES = [
  { key: 'mobility_drills', icon: '🚶', label: 'Mobility\nDrills' },
  { key: 'telepresence',    icon: '📡', label: 'Tele-\npresence' },
  { key: 'choreography',   icon: '🎭', label: 'Choreo-\ngraphy' },
  { key: 'manual_inspect',  icon: '🔍', label: 'Manual\nInspect' },
]

export default function OperatorPage() {
  const { telemetry, connected } = useTelemetry()
  const [armed, setArmed]       = useState(false)
  const [mode, setMode]         = useState('mobility_drills')
  const [safetyConfig, setSafetyConfig] = useState(null)

  // 获取 Supervisor 设置的安全参数（只读展示）
  useEffect(() => {
    robotAPI.getSafetyConfig().then(setSafetyConfig).catch(() => {})
  }, [])

  const sendCmd = async (command) => {
    try {
      await robotAPI.sendCommand(command)
      TelemetryPanel._addLog?.(`[CMD ] ${command}`, 'cmd')
    } catch (err) {
      TelemetryPanel._addLog?.(`[ERR ] ${command}: ${err}`, 'err')
    }
  }

  const handleEstop = async (active) => {
    try {
      if (active) {
        await robotAPI.eStop()
        TelemetryPanel._addLog?.('[ERR ] E-STOP ACTIVATED', 'err')
        setArmed(false)
      } else {
        await robotAPI.releaseEstop()
        TelemetryPanel._addLog?.('[INFO] E-Stop released', 'info')
      }
    } catch (err) {
      console.error(err)
    }
  }

  const handleArm = async (val) => {
    try {
      await robotAPI.setArmed(val)
      setArmed(val)
      TelemetryPanel._addLog?.(val ? '[CMD ] MOTION ARMED' : '[CMD ] MOTION DISARMED', val ? 'cmd' : 'warn')
    } catch (err) {
      TelemetryPanel._addLog?.(`[ERR ] ${err}`, 'err')
    }
  }

  const handleTag = async () => {
    const tag = window.prompt('Event tag / note:')
    if (tag) {
      try {
        await sessionAPI.addTag(tag)
        TelemetryPanel._addLog?.(`[TAG ] ${tag}`, 'info')
      } catch (_) {}
    }
  }

  const statusPills = [
    { label: connected ? 'ROBOT CONNECTED' : 'DISCONNECTED', color: connected ? 'green' : 'red' },
    { label: armed ? 'MOTION ARMED' : 'MOTION DISARMED', color: armed ? 'green' : 'yellow' },
    { label: 'SESSION ACTIVE', color: 'green' },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <Header statusPills={statusPills} />

      <div style={{
        display: 'grid',
        gridTemplateColumns: '220px 1fr 280px',
        gap: 1, flex: 1,
        background: 'var(--border)',
        overflow: 'hidden',
      }}>

        {/* ── LEFT: CONTROLS ── */}
        <Panel style={{ overflowY: 'auto' }}>
          <div style={{ fontFamily: 'Rajdhani, sans-serif', fontSize: 11, fontWeight: 600, letterSpacing: 2, textTransform: 'uppercase', color: 'var(--dim)', marginBottom: 14, paddingBottom: 8, borderBottom: '1px solid var(--border)' }}>Control</div>

          <EStop onTrigger={handleEstop} />

          {/* Motion arm */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 12px', border: '1px solid var(--border)', borderRadius: 6, marginBottom: 12 }}>
            <span style={{ fontFamily: 'Rajdhani, sans-serif', fontWeight: 600, letterSpacing: 1 }}>MOTION ARM</span>
            <Toggle on={armed} onChange={handleArm} />
          </div>

          {/* Mode presets */}
          <SectionLabel>Mode Preset</SectionLabel>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 14 }}>
            {MODES.map(m => (
              <button key={m.key} onClick={() => { setMode(m.key); sendCmd(`MODE_${m.key.toUpperCase()}`) }}
                style={{
                  padding: '8px 6px', borderRadius: 5, textAlign: 'center', cursor: 'pointer',
                  border: `1px solid ${mode === m.key ? 'var(--accent)' : 'var(--border)'}`,
                  background: mode === m.key ? 'rgba(0,200,255,0.1)' : 'transparent',
                  color: mode === m.key ? 'var(--accent)' : 'var(--text)',
                  fontFamily: 'Exo 2, sans-serif', fontSize: 11,
                  boxShadow: mode === m.key ? 'var(--glow)' : 'none',
                  transition: 'all 0.2s', whiteSpace: 'pre-line',
                }}>
                <div style={{ fontSize: 16, marginBottom: 3 }}>{m.icon}</div>
                {m.label}
              </button>
            ))}
          </div>

          {/* Safety limits (READ ONLY) */}
          <SectionLabel>Speed Limit <span style={{ color: 'var(--warn)', fontSize: 9 }}>🔒 SUPERVISOR ONLY</span></SectionLabel>
          <div style={{ padding: '8px 10px', background: 'rgba(255,184,0,0.06)', border: '1px solid rgba(255,184,0,0.3)', borderRadius: 5, marginBottom: 12, fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'var(--warn)' }}>
            🔒 Safety limits can only be changed by a Supervisor.
          </div>
          {safetyConfig && (
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 10px', border: '1px solid var(--border)', borderRadius: 5, marginBottom: 6, fontFamily: 'Share Tech Mono, monospace', fontSize: 11 }}>
              <span style={{ color: 'var(--dim)' }}>MAX SPEED</span>
              <span style={{ color: 'var(--accent)' }}>{safetyConfig.max_speed} m/s</span>
            </div>
          )}

          {/* D-Pad */}
          <SectionLabel>Teleop</SectionLabel>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 44px)', gridTemplateRows: 'repeat(3, 44px)', gap: 4, justifyContent: 'center', margin: '10px auto' }}>
            {[null, { cmd: 'MOVE_FWD', label: '↑' }, null,
              { cmd: 'TURN_LEFT', label: '←' }, { cmd: 'STOP', label: 'STOP', center: true }, { cmd: 'TURN_RIGHT', label: '→' },
              null, { cmd: 'MOVE_BACK', label: '↓' }, null
            ].map((btn, i) => btn ? (
              <button key={i}
                onMouseDown={() => sendCmd(btn.cmd)}
                onMouseUp={() => btn.cmd !== 'STOP' && sendCmd('STOP')}
                style={{
                  background: btn.center ? 'rgba(0,200,255,0.08)' : 'var(--border)',
                  border: `1px solid ${btn.center ? 'var(--accent)' : '#253545'}`,
                  borderRadius: 6,
                  color: btn.center ? 'var(--accent)' : 'var(--text)',
                  fontSize: btn.center ? 10 : 18,
                  fontFamily: btn.center ? 'Share Tech Mono, monospace' : 'inherit',
                  cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  transition: 'all 0.1s', letterSpacing: btn.center ? 1 : 0,
                }}>
                {btn.label}
              </button>
            ) : <div key={i} />)}
          </div>

          {/* Quick actions */}
          <SectionLabel>Quick Actions</SectionLabel>
          {[['Stand Still', 'STAND_STILL'], ['Home Pose', 'HOME_POSE'], ['Wave Greeting', 'WAVE']].map(([label, cmd]) => (
            <button key={cmd} onClick={() => sendCmd(cmd)}
              style={{ width: '100%', padding: 7, borderRadius: 5, marginBottom: 6, border: '1px solid var(--border)', background: 'transparent', color: 'var(--dim)', fontFamily: 'Exo 2, sans-serif', fontSize: 11, cursor: 'pointer', transition: 'all 0.2s' }}
              onMouseEnter={e => { e.target.style.borderColor = 'var(--text)'; e.target.style.color = 'var(--text)' }}
              onMouseLeave={e => { e.target.style.borderColor = 'var(--border)'; e.target.style.color = 'var(--dim)' }}>
              {label}
            </button>
          ))}
        </Panel>

        {/* ── CENTER: CAMERA ── */}
        <Panel title="Camera & Sensing" style={{ display: 'flex', flexDirection: 'column' }}>
          <div style={{ flex: 1, minHeight: 200, background: '#000', border: '1px solid var(--border)', borderRadius: 6, position: 'relative', overflow: 'hidden', marginBottom: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 8 }}>
            <div style={{ width: 60, height: 60, border: '1px solid rgba(0,200,255,0.3)', borderRadius: '50%', position: 'relative' }}>
              <div style={{ position: 'absolute', width: 1, height: '100%', left: '50%', background: 'rgba(0,200,255,0.3)' }} />
              <div style={{ position: 'absolute', height: 1, width: '100%', top: '50%', background: 'rgba(0,200,255,0.3)' }} />
            </div>
            <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 11, color: 'var(--dim)' }}>HEAD CAM — NO FEED (mock mode)</div>
            {/* HUD overlays */}
            <div style={{ position: 'absolute', top: 0, left: 0, padding: 8, fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'rgba(0,200,255,0.6)' }}>HEAD_CAM_01<br/>1920×1080 · 30fps<br/>LATENCY: {(telemetry?.latency_ms ?? 18).toFixed(0)}ms</div>
            <div style={{ position: 'absolute', top: 0, right: 0, padding: 8, fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'rgba(0,200,255,0.6)', textAlign: 'right' }}>
              <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: 'var(--danger)', marginRight: 4 }} />REC<br/>STREAM: OK
            </div>
            <div style={{ position: 'absolute', bottom: 0, right: 0, padding: 8, fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'rgba(0,200,255,0.6)', textAlign: 'right' }}>ZONE: LAB G12<br/>GEOFENCE: OK</div>
          </div>

          {/* Alerts */}
          <div style={{ fontFamily: 'Rajdhani, sans-serif', fontSize: 11, fontWeight: 600, letterSpacing: 2, textTransform: 'uppercase', color: 'var(--dim)', marginBottom: 10, paddingBottom: 8, borderBottom: '1px solid var(--border)' }}>Alerts</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {[
              { type: 'ok',   title: 'Readiness Check Passed', body: 'All systems nominal.', time: '09:14:22' },
              { type: 'warn', title: `Core Temp ${(telemetry?.core_temp_c ?? 54).toFixed(0)}°C`, body: 'Monitor thermal load.', time: new Date().toTimeString().slice(0,8) },
            ].map((a, i) => (
              <div key={i} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
                padding: '8px 10px', borderRadius: 5, fontSize: 11, lineHeight: 1.4,
                borderLeft: `3px solid ${a.type === 'ok' ? 'var(--accent2)' : a.type === 'warn' ? 'var(--warn)' : 'var(--accent)'}`,
                background: a.type === 'ok' ? 'rgba(10,245,160,0.05)' : a.type === 'warn' ? 'rgba(255,184,0,0.06)' : 'rgba(0,200,255,0.05)',
              }}>
                <div>
                  <div style={{ fontWeight: 600 }}>{a.title}</div>
                  <div>{a.body}</div>
                </div>
                <div style={{ fontFamily: 'Share Tech Mono, monospace', color: 'var(--dim)', fontSize: 10, whiteSpace: 'nowrap' }}>{a.time}</div>
              </div>
            ))}
          </div>
        </Panel>

        {/* ── RIGHT: TELEMETRY ── */}
        <TelemetryPanel telemetry={telemetry} onAddTag={handleTag} />
      </div>
    </div>
  )
}
