/**
 * Voice chat hook — manages mic capture, AudioWorklet downsampling, the
 * /api/ws/voice WebSocket session, and the live transcript state.
 *
 * Wake-word gating ("Chadwick") happens server-side: VoiceLive's system
 * prompt makes the model stay silent until it hears the wake word, so the
 * transcript here only fills in when the operator addresses Chadwick.
 */
import { useCallback, useEffect, useRef, useState } from 'react'

const WS_URL = import.meta.env.VITE_VOICE_WS_URL || 'ws://localhost:8000/api/ws/voice'
const TARGET_RATE = 24000
const WORKLET_URL = '/voice-pcm-worklet.js'

export function useVoiceChat() {
  const [enabled, setEnabled] = useState(false)
  const [status, setStatus] = useState('idle') // idle | connecting | listening | error
  const [error, setError] = useState('')
  const [partialText, setPartialText] = useState('') // streaming assistant text
  const [transcript, setTranscript] = useState([])   // [{role, text, ts}]

  const wsRef = useRef(null)
  const audioCtxRef = useRef(null)
  const workletNodeRef = useRef(null)
  const micStreamRef = useRef(null)
  const sourceNodeRef = useRef(null)

  const teardown = useCallback(async () => {
    setStatus('idle')
    setPartialText('')

    try { workletNodeRef.current?.port?.close?.() } catch (_) {}
    try { workletNodeRef.current?.disconnect() } catch (_) {}
    try { sourceNodeRef.current?.disconnect() } catch (_) {}
    workletNodeRef.current = null
    sourceNodeRef.current = null

    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach(t => { try { t.stop() } catch (_) {} })
      micStreamRef.current = null
    }
    if (audioCtxRef.current) {
      try { await audioCtxRef.current.close() } catch (_) {}
      audioCtxRef.current = null
    }
    if (wsRef.current) {
      try { wsRef.current.close() } catch (_) {}
      wsRef.current = null
    }
  }, [])

  const start = useCallback(async () => {
    const token = localStorage.getItem('chadwick_token')
    if (!token) {
      setError('Not logged in')
      setStatus('error')
      return false
    }
    setError('')
    setStatus('connecting')

    let stream
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
        video: false,
      })
    } catch (e) {
      setError(`Microphone access denied: ${e.message || e}`)
      setStatus('error')
      return false
    }
    micStreamRef.current = stream

    let audioCtx
    try {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)()
      await audioCtx.audioWorklet.addModule(WORKLET_URL)
    } catch (e) {
      setError(`Audio worklet load failed: ${e.message || e}`)
      setStatus('error')
      await teardown()
      return false
    }
    audioCtxRef.current = audioCtx

    const source = audioCtx.createMediaStreamSource(stream)
    const worklet = new AudioWorkletNode(audioCtx, 'pcm-downsampler', {
      processorOptions: { targetRate: TARGET_RATE, chunkSamples: 960 },
    })
    sourceNodeRef.current = source
    workletNodeRef.current = worklet
    source.connect(worklet)
    // Don't connect worklet to destination — we don't want mic loopback.

    const ws = new WebSocket(WS_URL)
    ws.binaryType = 'arraybuffer'
    wsRef.current = ws

    ws.onopen = () => {
      ws.send(JSON.stringify({ token }))
    }

    ws.onmessage = ev => {
      let msg
      try { msg = JSON.parse(ev.data) } catch (_) { return }

      if (msg.type === 'ready') {
        setStatus('listening')
        worklet.port.onmessage = e => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(e.data)
          }
        }
      } else if (msg.type === 'user_transcript') {
        if (msg.text && msg.text.trim()) {
          setTranscript(prev => [...prev, { role: 'you', text: msg.text, ts: Date.now() }])
        }
      } else if (msg.type === 'assistant_text_delta') {
        setPartialText(prev => prev + (msg.text || ''))
      } else if (msg.type === 'response_done') {
        const finalText = (msg.assistant_text || '').trim()
        if (finalText) {
          setTranscript(prev => [...prev, { role: 'robot', text: finalText, ts: Date.now() }])
        }
        setPartialText('')
      } else if (msg.type === 'error') {
        setError(msg.text || 'Voice error')
      }
    }

    ws.onerror = () => {
      setError('Voice socket error')
      setStatus('error')
    }
    ws.onclose = () => {
      if (enabled) setStatus('idle')
    }

    return true
  }, [enabled, teardown])

  // Toggle effect: when `enabled` flips, start or stop the pipeline.
  useEffect(() => {
    let cancelled = false
    if (enabled) {
      start().then(ok => {
        if (!ok && !cancelled) setEnabled(false)
      })
    } else {
      teardown()
    }
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled])

  useEffect(() => () => { teardown() }, [teardown])

  const toggle = useCallback(() => setEnabled(v => !v), [])
  const clearTranscript = useCallback(() => setTranscript([]), [])

  return { enabled, status, error, partialText, transcript, toggle, clearTranscript }
}
