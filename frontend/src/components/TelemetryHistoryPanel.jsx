import React, { useEffect, useMemo, useState } from 'react'

import { Panel, SectionLabel } from './SharedComponents'
import { sessionAPI } from '../services/api'

const SERIES = [
  { key: 'core_temp_c', label: 'Temp (°C)', color: '#ff6b5b' },
  { key: 'battery_pct', label: 'Battery (%)', color: '#5be07a' },
  { key: 'motor_load_pct', label: 'Motor Load (%)', color: '#ffd23f' },
  { key: 'tilt_deg', label: 'Tilt (°)', color: '#5bb8ff' },
]

const CHART_W = 520
const CHART_H = 160
const PAD = { top: 8, right: 8, bottom: 18, left: 28 }

function normalize(values) {
  const nums = values.filter(v => typeof v === 'number' && Number.isFinite(v))
  if (nums.length === 0) return { min: 0, max: 1 }
  const min = Math.min(...nums)
  const max = Math.max(...nums)
  if (min === max) return { min: min - 1, max: max + 1 }
  const pad = (max - min) * 0.1
  return { min: min - pad, max: max + pad }
}

function MiniChart({ samples, series }) {
  const innerW = CHART_W - PAD.left - PAD.right
  const innerH = CHART_H - PAD.top - PAD.bottom

  if (!samples || samples.length < 2) {
    return (
      <div style={{ color: 'var(--dim)', fontSize: 12, padding: '20px 0' }}>
        Not enough samples yet — start a session and wait a few seconds.
      </div>
    )
  }

  const xs = samples.map(s => new Date(s.timestamp).getTime())
  const xMin = xs[0]
  const xMax = xs[xs.length - 1]
  const xSpan = xMax - xMin || 1

  const values = samples.map(s => s[series.key])
  const { min: yMin, max: yMax } = normalize(values)
  const ySpan = yMax - yMin || 1

  const points = samples
    .map((s, i) => {
      const v = s[series.key]
      if (typeof v !== 'number' || !Number.isFinite(v)) return null
      const x = PAD.left + ((xs[i] - xMin) / xSpan) * innerW
      const y = PAD.top + (1 - (v - yMin) / ySpan) * innerH
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .filter(Boolean)
    .join(' ')

  const yTickMid = (yMin + yMax) / 2
  const ticks = [yMax, yTickMid, yMin]

  return (
    <svg
      viewBox={`0 0 ${CHART_W} ${CHART_H}`}
      style={{ width: '100%', height: 'auto', display: 'block' }}
    >
      <rect x={0} y={0} width={CHART_W} height={CHART_H} fill="var(--bg)" />
      {ticks.map((t, i) => {
        const y = PAD.top + (i * innerH) / 2
        return (
          <g key={i}>
            <line
              x1={PAD.left}
              x2={CHART_W - PAD.right}
              y1={y}
              y2={y}
              stroke="var(--border)"
              strokeDasharray="2 3"
              strokeWidth={0.5}
            />
            <text
              x={PAD.left - 4}
              y={y + 3}
              textAnchor="end"
              fontSize="9"
              fontFamily="Share Tech Mono, monospace"
              fill="var(--dim)"
            >
              {t.toFixed(1)}
            </text>
          </g>
        )
      })}
      <polyline points={points} fill="none" stroke={series.color} strokeWidth={1.5} />
    </svg>
  )
}

export function TelemetryHistoryPanel({ sessionId, sessionActive }) {
  const [samples, setSamples] = useState([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open || !sessionId) return undefined

    let cancelled = false

    async function load() {
      setLoading(true)
      try {
        const data = await sessionAPI.getTelemetry(sessionId)
        if (!cancelled) {
          setSamples(Array.isArray(data) ? data : [])
          setError('')
        }
      } catch (err) {
        if (!cancelled) setError(typeof err === 'string' ? err : 'Failed to load telemetry')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    const timer = window.setInterval(load, sessionActive ? 3000 : 15000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [open, sessionId, sessionActive])

  const latest = useMemo(() => (samples.length ? samples[samples.length - 1] : null), [samples])

  const downloadUrl = sessionId ? sessionAPI.exportTelemetryCSV(sessionId) : null

  return (
    <Panel title="Telemetry History">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <button
          onClick={() => setOpen(o => !o)}
          disabled={!sessionId}
          style={{
            padding: '6px 12px',
            background: 'transparent',
            color: 'var(--accent)',
            border: '1px solid var(--accent)',
            borderRadius: 4,
            cursor: sessionId ? 'pointer' : 'not-allowed',
            opacity: sessionId ? 1 : 0.4,
            fontFamily: 'Exo 2, sans-serif',
            fontSize: 11,
            letterSpacing: 1,
          }}
        >
          {open ? 'HIDE CHART' : 'SHOW CHART'}
        </button>
        {downloadUrl && (
          <a
            href={downloadUrl}
            download
            style={{
              fontSize: 10,
              letterSpacing: 1,
              color: 'var(--accent)',
              fontFamily: 'Share Tech Mono, monospace',
              textDecoration: 'none',
            }}
          >
            DOWNLOAD CSV ↓
          </a>
        )}
      </div>

      {!sessionId && (
        <div style={{ color: 'var(--dim)', fontSize: 12 }}>
          Start a session to begin recording telemetry samples.
        </div>
      )}

      {sessionId && open && (
        <>
          {loading && samples.length === 0 && (
            <div style={{ color: 'var(--dim)', fontSize: 12 }}>Loading…</div>
          )}
          {error && (
            <div style={{ color: 'var(--danger, #ff6b5b)', fontSize: 12 }}>{error}</div>
          )}

          {SERIES.map(series => (
            <div key={series.key} style={{ marginTop: 12 }}>
              <SectionLabel>
                <span style={{ color: series.color }}>■ </span>
                {series.label}
                {latest && typeof latest[series.key] === 'number' && (
                  <span style={{ marginLeft: 8, color: 'var(--dim)' }}>
                    latest {Number(latest[series.key]).toFixed(1)}
                  </span>
                )}
              </SectionLabel>
              <MiniChart samples={samples} series={series} />
            </div>
          ))}

          <div style={{ marginTop: 10, fontSize: 10, color: 'var(--dim)', fontFamily: 'Share Tech Mono, monospace' }}>
            {samples.length} samples · refreshes every {sessionActive ? '3' : '15'}s
          </div>
        </>
      )}
    </Panel>
  )
}
