/**
 * Operator page for the Week 1 command center demo.
 */
import React, { useEffect, useState } from 'react'

import { EStop, Header, Panel, SectionLabel, TelemetryPanel, Toggle } from '../components/SharedComponents'
import { useRobotConnection } from '../hooks/useRobotConnection'
import { robotAPI, sessionAPI } from '../services/api'
import { isSessionPaused, normalizeSessionLogs } from '../utils/sessionLogs'
import { useTelemetry } from '../hooks/useTelemetry'

const MODES = [
  { key: 'mobility_drills', icon: 'MD', label: 'Mobility\nDrills' },
  { key: 'telepresence', icon: 'TP', label: 'Tele-\npresence' },
  { key: 'choreography', icon: 'CH', label: 'Choreo-\ngraphy' },
  { key: 'manual_inspect', icon: 'MI', label: 'Manual\nInspect' },
]

export default function OperatorPage() {
  const { telemetry, connected: wsConnected, lastError: telemetryError } = useTelemetry()
  const {
    connection,
    lastError: connectionError,
    busy: connectionBusy,
    connect,
    disconnect,
  } = useRobotConnection()
  const [armed, setArmed] = useState(false)
  const [mode, setMode] = useState('mobility_drills')
  const [safetyConfig, setSafetyConfig] = useState(null)
  const [sessionInfo, setSessionInfo] = useState({ active: false })
  const [sessionLogs, setSessionLogs] = useState([])
  const [sessionBusy, setSessionBusy] = useState(false)
  const [sessionPaused, setSessionPaused] = useState(false)

  const connectionDisplay = {
    disconnected: { label: 'DISCONNECTED', color: 'red' },
    connecting: { label: 'CONNECTING', color: 'yellow' },
    connected: { label: 'ROBOT CONNECTED', color: 'yellow' },
    ready: { label: 'ROBOT READY', color: 'green' },
    unknown: { label: 'STATUS UNKNOWN', color: 'yellow' },
  }

  async function loadSessionState() {
    try {
      const current = await sessionAPI.getCurrent()
      setSessionInfo(current)

      if (!current.active) {
        setSessionLogs([])
        setSessionPaused(false)
        return
      }

      const logs = await sessionAPI.getLogs(current.session_id)
      const normalizedLogs = normalizeSessionLogs(logs)
      setSessionLogs(normalizedLogs)
      setSessionPaused(isSessionPaused(normalizedLogs))
    } catch (_) {}
  }

  useEffect(() => {
    robotAPI.getSafetyConfig().then(setSafetyConfig).catch(() => {})
    loadSessionState()

    const timer = window.setInterval(() => {
      loadSessionState()
    }, 1500)

    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    if (typeof telemetry?.motion_armed === 'boolean') {
      setArmed(telemetry.motion_armed)
    }
  }, [telemetry?.motion_armed])

  useEffect(() => {
    if (telemetry?.current_mode) {
      setMode(telemetry.current_mode)
    }
  }, [telemetry?.current_mode])

  const sendCmd = async command => {
    try {
      await robotAPI.sendCommand(command)
    } catch (error) {
      console.error(error)
    }
  }

  const handleEstop = async active => {
    try {
      if (active) {
        await robotAPI.eStop()
        setArmed(false)
      } else {
        await robotAPI.releaseEstop()
      }
      await loadSessionState()
    } catch (error) {
      console.error(error)
    }
  }

  const handleArm = async value => {
    try {
      await robotAPI.setArmed(value)
      setArmed(value)
      await loadSessionState()
    } catch (error) {
      window.alert(String(error))
    }
  }

  const handleConnectRobot = async () => {
    try {
      await connect()
    } catch (error) {
      const message = typeof error === 'string' ? error : error?.message || connectionError || 'Connect failed'
      window.alert(message)
    }
  }

  const handleDisconnectRobot = async () => {
    try {
      await disconnect()
      setArmed(false)
    } catch (error) {
      window.alert(String(error))
    }
  }

  const handleStartSession = async () => {
    setSessionBusy(true)
    try {
      await sessionAPI.start(mode)
      await loadSessionState()
    } catch (error) {
      window.alert(String(error))
    } finally {
      setSessionBusy(false)
    }
  }

  const handlePauseSession = async () => {
    setSessionBusy(true)
    try {
      await sessionAPI.pause()
      await loadSessionState()
    } catch (error) {
      window.alert(String(error))
    } finally {
      setSessionBusy(false)
    }
  }

  const handleTag = async () => {
    if (!sessionInfo.active) {
      window.alert('Start a session before adding a tag.')
      return
    }

    const tag = window.prompt('Tag label:', 'CHECKPOINT')
    if (!tag) {
      return
    }

    const note = window.prompt('Optional note:', '') || null

    setSessionBusy(true)
    try {
      await sessionAPI.addTag(tag, note)
      await loadSessionState()
    } catch (error) {
      window.alert(String(error))
    } finally {
      setSessionBusy(false)
    }
  }

  const robotReady = connection === 'ready'
  const robotConnected = connection === 'connected' || connection === 'ready'
  const canTeleop = robotReady && armed && !telemetry?.estop_active
  const connectionPill = connectionDisplay[connection] || connectionDisplay.unknown
  const statusPills = [
    connectionPill,
    { label: armed ? 'MOTION ARMED' : 'MOTION DISARMED', color: armed ? 'green' : 'yellow' },
    {
      label: sessionInfo.active ? (sessionPaused ? 'SESSION PAUSED' : 'SESSION ACTIVE') : 'NO SESSION',
      color: sessionInfo.active ? (sessionPaused ? 'yellow' : 'green') : 'yellow',
    },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <Header statusPills={statusPills} />

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '220px 1fr 280px',
          gap: 1,
          flex: 1,
          background: 'var(--border)',
          overflow: 'hidden',
        }}
      >
        <Panel style={{ overflowY: 'auto' }}>
          <div
            style={{
              fontFamily: 'Rajdhani, sans-serif',
              fontSize: 11,
              fontWeight: 600,
              letterSpacing: 2,
              textTransform: 'uppercase',
              color: 'var(--dim)',
              marginBottom: 14,
              paddingBottom: 8,
              borderBottom: '1px solid var(--border)',
            }}
          >
            Control
          </div>

          <EStop onTrigger={handleEstop} />

          <div
            style={{
              padding: '10px 12px',
              border: '1px solid var(--border)',
              borderRadius: 6,
              marginBottom: 12,
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 8,
              }}
            >
              <span style={{ fontFamily: 'Rajdhani, sans-serif', fontWeight: 600, letterSpacing: 1 }}>
                ROBOT LINK
              </span>
              {robotConnected ? (
                <button
                  onClick={handleDisconnectRobot}
                  disabled={connectionBusy}
                  style={{
                    padding: '4px 10px',
                    borderRadius: 4,
                    border: '1px solid var(--danger)',
                    background: 'transparent',
                    color: 'var(--danger)',
                    fontFamily: 'Share Tech Mono, monospace',
                    fontSize: 10,
                    cursor: connectionBusy ? 'not-allowed' : 'pointer',
                    letterSpacing: 1,
                    opacity: connectionBusy ? 0.5 : 1,
                  }}
                >
                  DISCONNECT
                </button>
              ) : (
                <button
                  onClick={handleConnectRobot}
                  disabled={connectionBusy || connection === 'connecting'}
                  style={{
                    padding: '4px 10px',
                    borderRadius: 4,
                    border: '1px solid var(--accent2)',
                    background: 'transparent',
                    color: 'var(--accent2)',
                    fontFamily: 'Share Tech Mono, monospace',
                    fontSize: 10,
                    cursor: connectionBusy || connection === 'connecting' ? 'not-allowed' : 'pointer',
                    letterSpacing: 1,
                    opacity: connectionBusy || connection === 'connecting' ? 0.5 : 1,
                  }}
                >
                  {connection === 'connecting' ? 'CONNECTING...' : 'CONNECT'}
                </button>
              )}
            </div>

            <div
              style={{
                marginTop: 8,
                fontFamily: 'Share Tech Mono, monospace',
                fontSize: 10,
                color: connectionError ? 'var(--danger)' : 'var(--dim)',
              }}
            >
              {connectionError || `STATE: ${connection.toUpperCase()}`}
            </div>
          </div>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '10px 12px',
              border: '1px solid var(--border)',
              borderRadius: 6,
              marginBottom: 12,
            }}
          >
            <span style={{ fontFamily: 'Rajdhani, sans-serif', fontWeight: 600, letterSpacing: 1 }}>MOTION ARM</span>
            <Toggle on={armed} onChange={handleArm} disabled={!robotReady} />
          </div>

          <SectionLabel>Mode Preset</SectionLabel>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 14 }}>
            {MODES.map(current => (
              <button
                key={current.key}
                onClick={() => {
                  setMode(current.key)
                  sendCmd(`MODE_${current.key.toUpperCase()}`)
                }}
                style={{
                  padding: '8px 6px',
                  borderRadius: 5,
                  textAlign: 'center',
                  cursor: 'pointer',
                  border: `1px solid ${mode === current.key ? 'var(--accent)' : 'var(--border)'}`,
                  background: mode === current.key ? 'rgba(0,200,255,0.1)' : 'transparent',
                  color: mode === current.key ? 'var(--accent)' : 'var(--text)',
                  fontFamily: 'Exo 2, sans-serif',
                  fontSize: 11,
                  boxShadow: mode === current.key ? 'var(--glow)' : 'none',
                  transition: 'all 0.2s',
                  whiteSpace: 'pre-line',
                }}
              >
                <div style={{ fontSize: 16, marginBottom: 3 }}>{current.icon}</div>
                {current.label}
              </button>
            ))}
          </div>

          <SectionLabel>
            Speed Limit <span style={{ color: 'var(--warn)', fontSize: 9 }}>SUPERVISOR ONLY</span>
          </SectionLabel>
          <div
            style={{
              padding: '8px 10px',
              background: 'rgba(255,184,0,0.06)',
              border: '1px solid rgba(255,184,0,0.3)',
              borderRadius: 5,
              marginBottom: 12,
              fontFamily: 'Share Tech Mono, monospace',
              fontSize: 10,
              color: 'var(--warn)',
            }}
          >
            Safety limits can only be changed by a Supervisor.
          </div>
          {safetyConfig && (
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                padding: '6px 10px',
                border: '1px solid var(--border)',
                borderRadius: 5,
                marginBottom: 6,
                fontFamily: 'Share Tech Mono, monospace',
                fontSize: 11,
              }}
            >
              <span style={{ color: 'var(--dim)' }}>MAX SPEED</span>
              <span style={{ color: 'var(--accent)' }}>{safetyConfig.max_speed} m/s</span>
            </div>
          )}

          <SectionLabel>Teleop</SectionLabel>
          {!canTeleop && (
            <div
              style={{
                padding: '8px 10px',
                border: '1px solid rgba(255,184,0,0.3)',
                borderRadius: 5,
                marginBottom: 10,
                color: 'var(--warn)',
                fontSize: 11,
              }}
            >
              Teleop enabled only when robot is ready, E-Stop is cleared, and motion is armed.
            </div>
          )}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, 44px)',
              gridTemplateRows: 'repeat(3, 44px)',
              gap: 4,
              justifyContent: 'center',
              margin: '10px auto',
            }}
          >
            {[
              null,
              { cmd: 'MOVE_FWD', label: 'F' },
              null,
              { cmd: 'TURN_LEFT', label: 'L' },
              { cmd: 'STOP', label: 'STOP', center: true },
              { cmd: 'TURN_RIGHT', label: 'R' },
              null,
              { cmd: 'MOVE_BACK', label: 'B' },
              null,
            ].map((button, index) =>
              button ? (
                <button
                  key={index}
                  onMouseDown={() => sendCmd(button.cmd)}
                  onMouseUp={() => button.cmd !== 'STOP' && sendCmd('STOP')}
                  disabled={button.cmd !== 'STOP' && !canTeleop}
                  style={{
                    background: button.center ? 'rgba(0,200,255,0.08)' : 'var(--border)',
                    border: `1px solid ${button.center ? 'var(--accent)' : '#253545'}`,
                    borderRadius: 6,
                    color: button.center ? 'var(--accent)' : 'var(--text)',
                    fontSize: button.center ? 10 : 18,
                    fontFamily: button.center ? 'Share Tech Mono, monospace' : 'inherit',
                    cursor: button.cmd !== 'STOP' && !canTeleop ? 'not-allowed' : 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    transition: 'all 0.1s',
                    letterSpacing: button.center ? 1 : 0,
                    opacity: button.cmd !== 'STOP' && !canTeleop ? 0.4 : 1,
                  }}
                >
                  {button.label}
                </button>
              ) : (
                <div key={index} />
              ),
            )}
          </div>

          <SectionLabel>Quick Actions</SectionLabel>
          {[
            ['Stand Still', 'STAND_STILL'],
            ['Home Pose', 'HOME_POSE'],
            ['Wave Greeting', 'WAVE'],
          ].map(([label, command]) => (
            <button
              key={command}
              onClick={() => sendCmd(command)}
              disabled={command !== 'HOME_POSE' && !canTeleop}
              style={{
                width: '100%',
                padding: 7,
                borderRadius: 5,
                marginBottom: 6,
                border: '1px solid var(--border)',
                background: 'transparent',
                color: 'var(--dim)',
                fontFamily: 'Exo 2, sans-serif',
                fontSize: 11,
                cursor: command !== 'HOME_POSE' && !canTeleop ? 'not-allowed' : 'pointer',
                transition: 'all 0.2s',
                opacity: command !== 'HOME_POSE' && !canTeleop ? 0.4 : 1,
              }}
              onMouseEnter={event => {
                if (command !== 'HOME_POSE' && !canTeleop) {
                  return
                }
                event.target.style.borderColor = 'var(--text)'
                event.target.style.color = 'var(--text)'
              }}
              onMouseLeave={event => {
                event.target.style.borderColor = 'var(--border)'
                event.target.style.color = 'var(--dim)'
              }}
            >
              {label}
            </button>
          ))}
        </Panel>

        <Panel title="Camera & Sensing" style={{ display: 'flex', flexDirection: 'column' }}>
          <div
            style={{
              flex: 1,
              minHeight: 200,
              background: '#000',
              border: '1px solid var(--border)',
              borderRadius: 6,
              position: 'relative',
              overflow: 'hidden',
              marginBottom: 8,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexDirection: 'column',
              gap: 8,
            }}
          >
            <div style={{ width: 60, height: 60, border: '1px solid rgba(0,200,255,0.3)', borderRadius: '50%', position: 'relative' }}>
              <div style={{ position: 'absolute', width: 1, height: '100%', left: '50%', background: 'rgba(0,200,255,0.3)' }} />
              <div style={{ position: 'absolute', height: 1, width: '100%', top: '50%', background: 'rgba(0,200,255,0.3)' }} />
            </div>
            <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 11, color: 'var(--dim)' }}>HEAD CAM - NO FEED (mock mode)</div>
            <div style={{ position: 'absolute', top: 0, left: 0, padding: 8, fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'rgba(0,200,255,0.6)' }}>
              HEAD_CAM_01
              <br />
              1920x1080 - 30fps
              <br />
              LATENCY: {(telemetry?.latency_ms ?? 18).toFixed(0)}ms
            </div>
            <div style={{ position: 'absolute', top: 0, right: 0, padding: 8, fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'rgba(0,200,255,0.6)', textAlign: 'right' }}>
              REC
              <br />
              STREAM: OK
            </div>
            <div style={{ position: 'absolute', bottom: 0, right: 0, padding: 8, fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'rgba(0,200,255,0.6)', textAlign: 'right' }}>
              ZONE: LAB G12
              <br />
              GEOFENCE: OK
            </div>
          </div>

          <div
            style={{
              fontFamily: 'Rajdhani, sans-serif',
              fontSize: 11,
              fontWeight: 600,
              letterSpacing: 2,
              textTransform: 'uppercase',
              color: 'var(--dim)',
              marginBottom: 10,
              paddingBottom: 8,
              borderBottom: '1px solid var(--border)',
            }}
          >
            Alerts
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {[
              { type: 'ok', title: 'Readiness Check Passed', body: 'All systems nominal.', time: '09:14:22' },
              {
                type: 'warn',
                title: `Core Temp ${(telemetry?.core_temp_c ?? 54).toFixed(0)}degC`,
                body: 'Monitor thermal load.',
                time: new Date().toTimeString().slice(0, 8),
              },
            ].map((alert, index) => (
              <div
                key={index}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'flex-start',
                  padding: '8px 10px',
                  borderRadius: 5,
                  fontSize: 11,
                  lineHeight: 1.4,
                  borderLeft: `3px solid ${alert.type === 'ok' ? 'var(--accent2)' : alert.type === 'warn' ? 'var(--warn)' : 'var(--accent)'}`,
                  background: alert.type === 'ok' ? 'rgba(10,245,160,0.05)' : alert.type === 'warn' ? 'rgba(255,184,0,0.06)' : 'rgba(0,200,255,0.05)',
                }}
              >
                <div>
                  <div style={{ fontWeight: 600 }}>{alert.title}</div>
                  <div>{alert.body}</div>
                </div>
                <div style={{ fontFamily: 'Share Tech Mono, monospace', color: 'var(--dim)', fontSize: 10, whiteSpace: 'nowrap' }}>
                  {alert.time}
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <TelemetryPanel
          telemetry={telemetry}
          connected={wsConnected}
          lastError={telemetryError}
          logEntries={sessionLogs}
          onAddTag={handleTag}
          onStartSession={handleStartSession}
          onPauseSession={handlePauseSession}
          sessionBusy={sessionBusy}
          sessionActive={sessionInfo.active}
          sessionPaused={sessionPaused}
          showSessionControls
        />
      </div>
    </div>
  )
}
