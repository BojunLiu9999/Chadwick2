import { useCallback, useEffect, useRef, useState } from 'react'

import { cameraAPI } from '../services/api'

const DEFAULT_CAMERA = {
  enabled: false,
  connected: false,
  mode: 'browser',
  label: 'HEAD_CAM_01',
  resolution: '1280x720',
  fps: 30,
  stream_url: '',
  status_message: '',
}

function stopMediaStream(stream) {
  if (!stream) {
    return
  }

  stream.getTracks().forEach(track => track.stop())
}

function formatCameraError(error) {
  const message = typeof error === 'string' ? error : error?.message || 'Camera connection failed'

  if (message === 'Permission denied') {
    return 'Camera permission denied by browser'
  }

  return message
}

export function useCameraFeed() {
  const [camera, setCamera] = useState(DEFAULT_CAMERA)
  const [mediaStream, setMediaStream] = useState(null)
  // frameUrl is now the MJPEG stream URL for unitree_sdk mode, or empty
  // for browser/video modes that don't use <img src=…>. No blob churn, no
  // setInterval polling — the browser handles multipart/x-mixed-replace
  // natively, decoding each JPEG part as it arrives on the single open
  // connection.
  const [frameUrl, setFrameUrl] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const streamRef = useRef(null)

  const releaseCurrentStream = useCallback(() => {
    stopMediaStream(streamRef.current)
    streamRef.current = null
    setMediaStream(null)
  }, [])

  const buildMjpegUrl = useCallback(() => {
    const token = localStorage.getItem('chadwick_token') || ''
    // Token has to go in the query string — <img> can't carry an
    // Authorization header. The backend documents the same trade-off.
    return `/api/camera/stream.mjpg?token=${encodeURIComponent(token)}`
  }, [])

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    releaseCurrentStream()
    setFrameUrl('')

    try {
      const status = await cameraAPI.getStatus()
      setCamera(status)

      if (!status.enabled) {
        throw new Error(status.status_message || 'Camera source is not configured')
      }

      if (status.mode === 'browser') {
        if (!navigator.mediaDevices?.getUserMedia) {
          throw new Error('Browser camera API is unavailable')
        }

        const stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: 'environment',
          },
          audio: false,
        })

        streamRef.current = stream
        setMediaStream(stream)
      } else if (status.mode === 'unitree_sdk') {
        // Point the <img> at the long-lived multipart stream. The browser
        // opens one HTTP request and decodes frames inline as they arrive.
        setFrameUrl(buildMjpegUrl())
      }
    } catch (cameraError) {
      setError(formatCameraError(cameraError))
    } finally {
      setLoading(false)
    }
  }, [buildMjpegUrl, releaseCurrentStream])

  useEffect(() => {
    refresh()

    return () => {
      releaseCurrentStream()
      setFrameUrl('')
    }
  }, [refresh, releaseCurrentStream])

  return {
    camera,
    mediaStream,
    frameUrl,
    loading,
    error,
    refresh,
  }
}
