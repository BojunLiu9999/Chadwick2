const EVENT_ALIASES = {
  SESSION_START: 'SESSION_STARTED',
  SESSION_END: 'SESSION_STOPPED',
  'E-STOP': 'ESTOP_TRIGGERED',
  MOTION_ARM: 'MOTION_ARMED',
  MOTION_DISARM: 'MOTION_DISARMED',
}

const ENTRY_LEVELS = {
  INFO: 'info',
  CMD: 'info',
  TAG: 'info',
  WARN: 'warning',
  ERR: 'error',
}

const EVENT_SOURCES = {
  ROBOT_CONNECTED: 'robot',
  ROBOT_DISCONNECTED: 'robot',
  ROBOT_READY: 'robot',
  SESSION_STARTED: 'session',
  SESSION_PAUSED: 'session',
  SESSION_STOPPED: 'session',
  TAG_ADDED: 'session',
  ESTOP_TRIGGERED: 'safety',
  ESTOP_RELEASED: 'safety',
  MOTION_ARMED: 'safety',
  MOTION_DISARMED: 'safety',
  TELEMETRY_WARNING: 'telemetry',
}

function parseDetail(detail) {
  if (!detail) {
    return null
  }

  try {
    const parsed = JSON.parse(detail)
    return parsed && typeof parsed === 'object' ? parsed : null
  } catch {
    return null
  }
}

function toUnifiedEvent(entry) {
  if (entry.entry_type === 'TAG') {
    return 'TAG_ADDED'
  }
  return EVENT_ALIASES[entry.event] || entry.event
}

function humanizeMode(mode) {
  if (!mode) {
    return null
  }

  return mode
    .split('_')
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function buildMessage(event, detail, data) {
  switch (event) {
    case 'SESSION_STARTED':
      return data?.mode ? `Session started (${humanizeMode(data.mode)})` : 'Session started'
    case 'SESSION_PAUSED':
      return 'Session paused'
    case 'SESSION_STOPPED':
      return data?.duration_seconds
        ? `Session stopped (${Math.round(data.duration_seconds)}s)`
        : 'Session stopped'
    case 'TAG_ADDED':
      return data?.tag ? `Tag added: ${data.tag}` : 'Tag added'
    case 'ESTOP_TRIGGERED':
      return 'E-Stop activated'
    case 'ESTOP_RELEASED':
      return 'E-Stop released'
    case 'MOTION_ARMED':
      return 'Motion armed'
    case 'MOTION_DISARMED':
      return 'Motion disarmed'
    default:
      return detail || event
  }
}

export function normalizeSessionLog(entry) {
  const data = parseDetail(entry.detail)
  const unifiedEvent = toUnifiedEvent(entry)
  const mergedData = unifiedEvent === 'TAG_ADDED'
    ? { tag: entry.event, note: entry.detail, ...data }
    : data

  return {
    timestamp: entry.timestamp,
    session_id: entry.session_id,
    operator: entry.operator,
    level: ENTRY_LEVELS[entry.entry_type] || 'info',
    event: unifiedEvent,
    message: buildMessage(unifiedEvent, entry.detail, mergedData),
    source: EVENT_SOURCES[unifiedEvent] || 'robot',
    data: mergedData || {},
  }
}

export function normalizeSessionLogs(entries = []) {
  return entries.map(normalizeSessionLog)
}

export function isSessionPaused(entries = []) {
  return entries.some(entry => entry.event === 'SESSION_PAUSED')
}

export function formatLogTime(timestamp) {
  if (!timestamp) {
    return '--:--:--'
  }

  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) {
    return '--:--:--'
  }

  return date.toLocaleTimeString('en-GB', { hour12: false })
}
