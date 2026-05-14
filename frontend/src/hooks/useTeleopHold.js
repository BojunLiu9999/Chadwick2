import { useCallback, useEffect, useRef } from 'react'

/**
 * Press-and-hold teleop driver.
 *
 * While a directional button is held we re-send the same locomotion command
 * every `repeatMs` so the backend keeps driving (and the auto-STOP watchdog
 * stays fed). On release / mouse-leave / touch-end / unmount we send STOP.
 *
 * The hook owns exactly one interval and one "active command" ref. Pressing a
 * second button while another is held swaps the interval cleanly without
 * emitting a STOP in between — the backend reads the new motion as continued
 * driving, not a fresh start.
 */
export function useTeleopHold({ sendCommand, repeatMs = 250 }) {
  const intervalRef = useRef(null)
  const activeCmdRef = useRef(null)
  // Keep latest sendCommand in a ref so unmount-cleanup never closes over a
  // stale reference and never re-fires when the parent re-renders.
  const sendRef = useRef(sendCommand)
  useEffect(() => {
    sendRef.current = sendCommand
  }, [sendCommand])

  const stopMove = useCallback(() => {
    if (intervalRef.current !== null) {
      window.clearInterval(intervalRef.current)
      intervalRef.current = null
    }
    if (activeCmdRef.current !== null) {
      activeCmdRef.current = null
      sendRef.current('STOP')
    }
  }, [])

  const startMove = useCallback(
    command => {
      // Replace any existing interval — covers the case where a second button
      // is pressed while the first is still held (no STOP between them).
      if (intervalRef.current !== null) {
        window.clearInterval(intervalRef.current)
        intervalRef.current = null
      }
      activeCmdRef.current = command
      sendRef.current(command)
      intervalRef.current = window.setInterval(() => {
        sendRef.current(command)
      }, repeatMs)
    },
    [repeatMs],
  )

  // Unmount safety: don't let the page tear down while a hold is still active.
  useEffect(() => {
    return () => {
      if (intervalRef.current !== null) {
        window.clearInterval(intervalRef.current)
        intervalRef.current = null
      }
      if (activeCmdRef.current !== null) {
        activeCmdRef.current = null
        sendRef.current('STOP')
      }
    }
  }, [])

  return { startMove, stopMove }
}
