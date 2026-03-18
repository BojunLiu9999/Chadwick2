/**
 * SupervisorPage.jsx
 * 监管员界面 — 概览 / 安全设置 / 审计日志
 */
import React, { useState, useEffect } from 'react'
import { Header, Panel, SectionLabel, EStop, Toggle, TelemetryPanel } from '../components/SharedComponents'
import { robotAPI, sessionAPI } from '../services/api'
import { useTelemetry } from '../hooks/useTelemetry'

const TABS = ['📊 Overview', '🛡️ Safety Controls', '📋 Audit Log']

export default function SupervisorPage() {
  const { telemetry, connected } = useTelemetry()
  const [activeTab, setActiveTab] = useState(0)
  const [safetyConfig, setSafetyConfig] = useState({
    max_speed: 0.4, turn_rate: 30, max_torque_pct: 40,
    temp_warn: 60,  temp_stop: 70,  active_zone: 'LAB G12',
  })
  const [localConfig, setLocalConfig] = useState({ ...safetyConfig })
  const [auditLog, setAuditLog] = useState([
    { time: '09:14:18', operator: 'student_01', type: 'INFO', event: 'Session Start',    detail: 'SES-0042 · Mobility Drills' },
    { time: '09:14:20', operator: 'system',     type: 'INFO', event: 'Readiness Check',  detail: 'All checks passed' },
    { time: '09:14:25', operator: 'student_01', type: 'CMD',  event: 'Mode Change',      detail: '→ Mobility Drills' },
    { time: '09:21:05', operator: 'system',     type: 'WARN', event: 'Thermal Alert',    detail: 'L_KNEE 58°C (threshold 60°C)' },
  ])

  useEffect(() => {
    robotAPI.getSafetyConfig().then(c => { setSafetyConfig(c); setLocalConfig(c) }).catch(() => {})
  }, [])

  const handleApplySafety = async () => {
    try {
      await robotAPI.updateSafetyConfig(localConfig)
      setSafetyConfig({ ...localConfig })
      addAudit('supervisor', 'CMD', 'Safety Config Updated', JSON.stringify(localConfig))
      alert('✓ Safety limits applied.')
    } catch (err) {
      alert(`Error: ${err}`)
    }
  }

  const handleEstop = async (active) => {
    try {
      if (active) {
        await robotAPI.eStop()
        addAudit('supervisor', 'ERR', 'Force E-Stop', 'Supervisor override')
      } else {
        await robotAPI.releaseEstop()
      }
    } catch (_) {}
  }

  const addAudit = (operator, type, event, detail) => {
    const time = new Date().toTimeString().slice(0, 8)
    setAuditLog(prev => [{ time, operator, type, event, detail }, ...prev])
  }

  const exportCSV = () => {
    const rows = [['Time','Operator','Type','Event','Detail'],
      ...auditLog.map(e => [e.time, e.operator, e.type, e.event, e.detail])]
    const csv = rows.map(r => r.join(',')).join('\n')
    const a = document.createElement('a')
    a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv)
    a.download = 'chadwick_audit.csv'; a.click()
  }

  const typeColor = { CMD: 'var(--accent2)', WARN: 'var(--warn)', ERR: 'var(--danger)', INFO: 'var(--accent)' }

  const statusPills = [
    { label: connected ? 'ROBOT CONNECTED' : 'DISCONNECTED', color: connected ? 'green' : 'red' },
    { label: '1 OPERATOR ACTIVE', color: 'yellow' },
    { label: 'SESSION ACTIVE', color: 'green' },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <Header statusPills={statusPills} />

      {/* Tab nav */}
      <div style={{ display: 'flex', background: 'var(--panel)', borderBottom: '1px solid var(--border)', padding: '0 20px' }}>
        {TABS.map((tab, i) => (
          <button key={i} onClick={() => setActiveTab(i)}
            style={{
              padding: '10px 20px', border: 'none',
              borderBottom: `2px solid ${activeTab === i ? 'var(--accent2)' : 'transparent'}`,
              background: 'transparent',
              color: activeTab === i ? 'var(--accent2)' : 'var(--dim)',
              fontFamily: 'Rajdhani, sans-serif', fontSize: 13, fontWeight: 600,
              letterSpacing: 1, cursor: 'pointer', transition: 'all 0.2s',
            }}>
            {tab}
          </button>
        ))}
      </div>

      {/* ── TAB 0: OVERVIEW ── */}
      {activeTab === 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr 300px', gap: 1, flex: 1, background: 'var(--border)', overflow: 'hidden' }}>
          <Panel style={{ overflowY: 'auto' }}>
            <div style={{ fontFamily: 'Rajdhani, sans-serif', fontSize: 11, fontWeight: 600, letterSpacing: 2, textTransform: 'uppercase', color: 'var(--dim)', marginBottom: 14, paddingBottom: 8, borderBottom: '1px solid var(--border)' }}>Active Operators</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', border: '1px solid var(--border)', borderRadius: 6, marginBottom: 16 }}>
              <div style={{ width: 32, height: 32, borderRadius: '50%', background: 'rgba(0,200,255,0.1)', border: '1px solid var(--accent2)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14 }}>🕹️</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontFamily: 'Rajdhani, sans-serif', fontSize: 13, fontWeight: 600 }}>student_01</div>
                <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'var(--dim)' }}>Mode: Mobility Drills · SES-0042</div>
              </div>
              <span style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'var(--accent)' }}>● LIVE</span>
            </div>

            <SectionLabel>Emergency Override</SectionLabel>
            <EStop onTrigger={handleEstop} />
            <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'var(--dim)', textAlign: 'center', marginBottom: 14 }}>Overrides all operators instantly</div>

            <SectionLabel>Current Limits</SectionLabel>
            {[['MAX SPEED', `${safetyConfig.max_speed} m/s`], ['TURN RATE', `${safetyConfig.turn_rate}°/s`], ['GEOFENCE', safetyConfig.active_zone], ['TEMP WARN', `${safetyConfig.temp_warn}°C`]].map(([k, v]) => (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 10px', border: '1px solid var(--border)', borderRadius: 5, marginBottom: 6, fontFamily: 'Share Tech Mono, monospace', fontSize: 11 }}>
                <span style={{ color: 'var(--dim)' }}>{k}</span>
                <span style={{ color: 'var(--accent2)' }}>{v}</span>
              </div>
            ))}
            <button onClick={() => setActiveTab(1)} style={{ width: '100%', padding: 9, borderRadius: 5, border: '1px solid var(--accent2)', background: 'transparent', color: 'var(--accent2)', fontFamily: 'Rajdhani, sans-serif', fontSize: 12, fontWeight: 600, letterSpacing: 1, cursor: 'pointer', marginTop: 8 }}>
              ⚙️ Edit Safety Limits →
            </button>
          </Panel>

          <Panel title="Live Feed — Supervisor Monitor" style={{ display: 'flex', flexDirection: 'column' }}>
            <div style={{ flex: 1, minHeight: 300, background: '#000', border: '1px solid var(--border)', borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 8, position: 'relative' }}>
              <div style={{ width: 60, height: 60, border: '1px solid rgba(10,245,160,0.3)', borderRadius: '50%', position: 'relative' }}>
                <div style={{ position: 'absolute', width: 1, height: '100%', left: '50%', background: 'rgba(10,245,160,0.3)' }} />
                <div style={{ position: 'absolute', height: 1, width: '100%', top: '50%', background: 'rgba(10,245,160,0.3)' }} />
              </div>
              <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 11, color: 'var(--dim)' }}>HEAD CAM — NO FEED (mock mode)</div>
              <div style={{ position: 'absolute', top: 0, left: 0, padding: 8, fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'rgba(10,245,160,0.6)' }}>HEAD_CAM_01<br/>LATENCY: {(telemetry?.latency_ms ?? 18).toFixed(0)}ms</div>
              <div style={{ position: 'absolute', bottom: 0, right: 0, padding: 8, fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'rgba(10,245,160,0.6)', textAlign: 'right' }}>ZONE: {safetyConfig.active_zone}<br/>GEOFENCE: ✓ ACTIVE</div>
            </div>
          </Panel>

          <TelemetryPanel telemetry={telemetry} />
        </div>
      )}

      {/* ── TAB 1: SAFETY CONTROLS ── */}
      {activeTab === 1 && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 1, flex: 1, background: 'var(--border)', overflow: 'hidden' }}>

          {/* Motion limits */}
          <Panel title="Motion Limits" style={{ overflowY: 'auto' }}>
            <SafetyCard title="⚡ Speed & Movement">
              {[
                { label: 'Max Speed', id: 'max_speed', min: 0.1, max: 1.5, step: 0.1, unit: 'm/s' },
                { label: 'Turn Rate', id: 'turn_rate', min: 0, max: 100, step: 5, unit: '°/s' },
              ].map(f => (
                <SliderRow key={f.id} label={f.label} value={localConfig[f.id]} unit={f.unit}
                  min={f.min} max={f.max} step={f.step}
                  onChange={v => setLocalConfig(c => ({ ...c, [f.id]: v }))} />
              ))}
              <ApplyBtn onClick={handleApplySafety} />
            </SafetyCard>
            <SafetyCard title="💪 Force / Torque">
              <SliderRow label="Max Joint Torque" value={localConfig.max_torque_pct} unit="%"
                min={10} max={100} step={5}
                onChange={v => setLocalConfig(c => ({ ...c, max_torque_pct: v }))} />
              <ApplyBtn onClick={handleApplySafety} />
            </SafetyCard>
          </Panel>

          {/* Geofence & thermal */}
          <Panel title="Geofence & Thresholds" style={{ overflowY: 'auto' }}>
            <SafetyCard title="📍 Active Zone">
              {['LAB G12', 'CORRIDOR A', 'DEMO AREA B'].map(zone => (
                <div key={zone} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', fontSize: 12 }}>
                  <span>{zone}</span>
                  <Toggle on={localConfig.active_zone === zone}
                    onChange={() => setLocalConfig(c => ({ ...c, active_zone: zone }))} />
                </div>
              ))}
              <ApplyBtn onClick={handleApplySafety} />
            </SafetyCard>
            <SafetyCard title="🌡️ Thermal Thresholds">
              <SliderRow label="Warning Temp" value={localConfig.temp_warn} unit="°C" min={40} max={80}
                onChange={v => setLocalConfig(c => ({ ...c, temp_warn: v }))} />
              <SliderRow label="Stop Temp" value={localConfig.temp_stop} unit="°C" min={50} max={90}
                onChange={v => setLocalConfig(c => ({ ...c, temp_stop: v }))} />
              <ApplyBtn onClick={handleApplySafety} />
            </SafetyCard>
          </Panel>

          {/* Permissions */}
          <Panel title="Role Permissions" style={{ overflowY: 'auto' }}>
            <SafetyCard title="🕹️ Operator Can...">
              {[
                ['Teleop (basic)', true, false],
                ['Scripted actions', true, false],
                ['Mobility Drills', true, false],
                ['Choreography mode', false, false],
                ['Modify speed limits', false, true],
                ['Export session data', false, false],
              ].map(([label, on, locked]) => (
                <div key={label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '7px 0', fontSize: 12 }}>
                  <span>{label}</span>
                  <Toggle on={on} disabled={locked} />
                </div>
              ))}
            </SafetyCard>
            <SafetyCard title="📹 Recording Policy">
              {[['Auto-record sessions', true], ['Save lidar scans', true], ['Face detection (blocked)', false]].map(([label, on]) => (
                <div key={label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '7px 0', fontSize: 12 }}>
                  <span>{label}</span>
                  <Toggle on={on} disabled={label.includes('blocked')} />
                </div>
              ))}
              <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 9, color: 'var(--dim)', marginTop: 10, lineHeight: 1.6 }}>
                All data stored on USyd on-prem.<br />No external cloud by default.
              </div>
            </SafetyCard>
          </Panel>
        </div>
      )}

      {/* ── TAB 2: AUDIT LOG ── */}
      {activeTab === 2 && (
        <div style={{ flex: 1, overflow: 'hidden' }}>
          <Panel style={{ height: '100%', overflowY: 'auto' }}>
            <div style={{ fontFamily: 'Rajdhani, sans-serif', fontSize: 11, fontWeight: 600, letterSpacing: 2, textTransform: 'uppercase', color: 'var(--dim)', marginBottom: 14, paddingBottom: 8, borderBottom: '1px solid var(--border)' }}>Audit Log — Session SES-0042</div>
            <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
              {['⬇ Export CSV', '⬇ Export JSON'].map(label => (
                <button key={label} onClick={exportCSV}
                  style={{ padding: '8px 16px', borderRadius: 5, border: '1px solid var(--border)', background: 'transparent', color: 'var(--text)', fontFamily: 'Rajdhani, sans-serif', fontSize: 12, fontWeight: 600, letterSpacing: 1, cursor: 'pointer', transition: 'all 0.2s' }}
                  onMouseEnter={e => { e.target.style.borderColor = 'var(--accent2)'; e.target.style.color = 'var(--accent2)' }}
                  onMouseLeave={e => { e.target.style.borderColor = 'var(--border)'; e.target.style.color = 'var(--text)' }}>
                  {label}
                </button>
              ))}
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'Share Tech Mono, monospace', fontSize: 11 }}>
              <thead>
                <tr>
                  {['Timestamp', 'Operator', 'Type', 'Event', 'Details'].map(h => (
                    <th key={h} style={{ textAlign: 'left', padding: '8px 12px', borderBottom: '1px solid var(--border)', color: 'var(--dim)', fontSize: 10, letterSpacing: 2, textTransform: 'uppercase' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {auditLog.map((e, i) => (
                  <tr key={i} style={{ transition: 'background 0.1s' }}
                    onMouseEnter={el => el.currentTarget.style.background = 'rgba(10,245,160,0.02)'}
                    onMouseLeave={el => el.currentTarget.style.background = 'transparent'}>
                    <td style={{ padding: '8px 12px', borderBottom: '1px solid rgba(255,255,255,0.03)' }}>{e.time}</td>
                    <td style={{ padding: '8px 12px', borderBottom: '1px solid rgba(255,255,255,0.03)' }}>{e.operator}</td>
                    <td style={{ padding: '8px 12px', borderBottom: '1px solid rgba(255,255,255,0.03)', color: typeColor[e.type] }}>{e.type}</td>
                    <td style={{ padding: '8px 12px', borderBottom: '1px solid rgba(255,255,255,0.03)' }}>{e.event}</td>
                    <td style={{ padding: '8px 12px', borderBottom: '1px solid rgba(255,255,255,0.03)', color: 'var(--dim)' }}>{e.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
        </div>
      )}
    </div>
  )
}

// ── 小组件 ──
function SafetyCard({ title, children }) {
  return (
    <div style={{ background: 'rgba(10,245,160,0.03)', border: '1px solid rgba(10,245,160,0.15)', borderRadius: 8, padding: 14, marginBottom: 12 }}>
      <div style={{ fontFamily: 'Rajdhani, sans-serif', fontSize: 13, fontWeight: 600, color: 'var(--accent2)', marginBottom: 10, letterSpacing: 1 }}>{title}</div>
      {children}
    </div>
  )
}

function SliderRow({ label, value, unit, min, max, step = 1, onChange }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, fontSize: 11 }}>
        <span>{label}</span>
        <span style={{ color: 'var(--accent2)', fontFamily: 'Share Tech Mono, monospace' }}>{value}{unit}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(parseFloat(e.target.value))}
        style={{ WebkitAppearance: 'none', width: '100%', height: 4, background: 'var(--border)', borderRadius: 2, outline: 'none' }} />
    </div>
  )
}

function ApplyBtn({ onClick }) {
  return (
    <button onClick={onClick} style={{ width: '100%', padding: 8, borderRadius: 5, border: '1px solid var(--accent2)', background: 'rgba(10,245,160,0.08)', color: 'var(--accent2)', fontFamily: 'Rajdhani, sans-serif', fontSize: 13, fontWeight: 600, letterSpacing: 2, cursor: 'pointer', marginTop: 8, transition: 'all 0.2s' }}>
      ✓ APPLY
    </button>
  )
}
