/**
 * Operator page for the Week 1 command center demo.
 */
import React, { useEffect, useState } from 'react'

import { CameraFeed, EStop, Header, Panel, SectionLabel, TelemetryPanel, Toggle } from '../components/SharedComponents'
import { useRobotConnection } from '../hooks/useRobotConnection'
import { robotAPI, sessionAPI } from '../services/api'
import { isSessionPaused, normalizeSessionLogs } from '../utils/sessionLogs'
import { useTelemetry } from '../hooks/useTelemetry'

const SESSION_MODE = 'teleoperation'

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

  const sendCmd = async command => {
    try {
      const locoCommands = ['MOVE_FWD', 'MOVE_BACK', 'TURN_LEFT', 'TURN_RIGHT', 'STOP']

      if (locoCommands.includes(command)) {
        await robotAPI.runLoco(command)
      } else {
        await robotAPI.sendCommand(command)
      }
    } catch (error) {
      console.error(error)
    }
  }

  const handlePlayAudio = async () => {
    try {
      const result = await robotAPI.playAudio()
      console.log('Audio result:', result)

      if (result.success) {
        window.alert('✅ Audio sent to robot')
      } else {
        window.alert('❌ Audio failed')
      }
    } catch (error) {
      console.error(error)
      window.alert(`❌ Audio failed: ${error}`)
    }
  }
  
  const handleHighLevelCommand = async command => {
  try {
    let result

    if (command === 'HOME_POSE') {
      result = await robotAPI.sendCommand(command)
    } else if (command === 'STOP') {
      result = await robotAPI.runLoco(command)
    } else {
      result = await robotAPI.runHighLevel(command)
    }

    console.log('Command result:', result)

    if (result.success) {
      window.alert(`✅ ${command} sent`)
    } else {
      window.alert(`❌ ${command} failed`)
    }

  } catch (error) {
    console.error(error)
    window.alert(`❌ Command failed: ${error}`)
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
      await sessionAPI.start(SESSION_MODE)
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
  const canHomePose = robotReady && !telemetry?.estop_active
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

          <div
            style={{
              padding: '9px 10px',
              background: 'rgba(10,245,160,0.06)',
              border: '1px solid rgba(10,245,160,0.26)',
              borderRadius: 5,
              marginBottom: 14,
              fontFamily: 'Share Tech Mono, monospace',
              fontSize: 10,
              color: 'var(--accent2)',
              lineHeight: 1.5,
            }}
          >
            Motion mode is enabled on the robot with the remote controller before web teleoperation.
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
             ['Stand Still', 'STOP'],
             ['Home Pose', 'HOME_POSE'],
             ['Wave Greeting', 'high wave'],
          ].map(([label, command]) => (
            <button
              key={command}
              onClick={() => handleHighLevelCommand(command)}
              disabled={command === 'HOME_POSE' ? !canHomePose : !canTeleop}
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
                cursor: command === 'HOME_POSE' ? (!canHomePose ? 'not-allowed' : 'pointer') : (!canTeleop ? 'not-allowed' : 'pointer'),
                transition: 'all 0.2s',
                opacity: command === 'HOME_POSE' ? (!canHomePose ? 0.4 : 1) : (!canTeleop ? 0.4 : 1),
              }}
              onMouseEnter={event => {
                if (command === 'HOME_POSE' ? !canHomePose : !canTeleop) {
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

          <button
            onClick={handlePlayAudio}
            style={{
              width: '100%',
              padding: 7,
              borderRadius: 5,
              marginBottom: 6,
              border: '1px solid var(--accent)',
              background: 'transparent',
              color: 'var(--accent)',
              fontFamily: 'Exo 2, sans-serif',
              fontSize: 11,
              cursor: 'pointer',
              transition: 'all 0.2s',
            }}
          >
            ▶️ Play Audio
          </button>
         <button
  onClick={() => handleHighLevelCommand('shake hand')}
  style={{
    width: '100%',
    padding: 7,
    borderRadius: 5,
    marginBottom: 6,
    border: '1px solid var(--accent)',
    background: 'transparent',
    color: 'var(--accent)',
    fontFamily: 'Exo 2, sans-serif',
    fontSize: 11,
    cursor: 'pointer',
  }}
>
  🤝 Shake Hand
</button>

<button
  onClick={() => handleHighLevelCommand('high wave')}
  style={{
    width: '100%',
    padding: 7,
    borderRadius: 5,
    marginBottom: 6,
    border: '1px solid var(--accent)',
    background: 'transparent',
    color: 'var(--accent)',
    fontFamily: 'Exo 2, sans-serif',
    fontSize: 11,
    cursor: 'pointer',
  }}
>
  👋 Wave Hand
</button>

<button
  onClick={() => handleHighLevelCommand('clap')}
  style={{
    width: '100%',
    padding: 7,
    borderRadius: 5,
    marginBottom: 6,
    border: '1px solid var(--accent)',
    background: 'transparent',
    color: 'var(--accent)',
    fontFamily: 'Exo 2, sans-serif',
    fontSize: 11,
    cursor: 'pointer',
  }}
>
  👏 Clap
</button>

<button
  onClick={() => handleHighLevelCommand('high five')}
  style={{
    width: '100%',
    padding: 7,
    borderRadius: 5,
    marginBottom: 6,
    border: '1px solid var(--accent)',
    background: 'transparent',
    color: 'var(--accent)',
    fontFamily: 'Exo 2, sans-serif',
    fontSize: 11,
    cursor: 'pointer',
  }}
>
  ✋ High Five
</button>

<button
  onClick={() => handleHighLevelCommand('hands up')}
  style={{
    width: '100%',
    padding: 7,
    borderRadius: 5,
    marginBottom: 6,
    border: '1px solid var(--accent)',
    background: 'transparent',
    color: 'var(--accent)',
    fontFamily: 'Exo 2, sans-serif',
    fontSize: 11,
    cursor: 'pointer',
  }}
>
  🙌 Hands Up
</button>
          
          
        </Panel>

        <Panel title="Camera & Sensing" style={{ display: 'flex', flexDirection: 'column' }}>
          <CameraFeed
            latencyMs={telemetry?.latency_ms ?? 18}
            zone={safetyConfig?.active_zone || 'LAB G12'}
            accentColor="var(--accent)"
          />

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
