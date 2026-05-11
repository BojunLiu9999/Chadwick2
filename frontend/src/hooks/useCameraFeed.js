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
  const [frameUrl, setFrameUrl] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const streamRef = useRef(null)
  const frameUrlRef = useRef('')
  const pollRef = useRef(null)
  const isFetchingFrameRef = useRef(false)

  const releaseCurrentStream = useCallback(() => {
    stopMediaStream(streamRef.current)
    streamRef.current = null
    setMediaStream(null)
  }, [])

  const releaseCurrentFrame = useCallback(() => {
    if (frameUrlRef.current) {
      URL.revokeObjectURL(frameUrlRef.current)
      frameUrlRef.current = ''
    }
    setFrameUrl('')
  }, [])

  const stopFramePolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  const loadUnitreeFrame = useCallback(async ({ surfaceErrors = false } = {}) => {
    if (isFetchingFrameRef.current) {
      return
    }

    isFetchingFrameRef.current = true

    try {
      const frameBlob = await cameraAPI.getFrame()
      const nextFrameUrl = URL.createObjectURL(frameBlob)

      if (frameUrlRef.current) {
        URL.revokeObjectURL(frameUrlRef.current)
      }

      frameUrlRef.current = nextFrameUrl
      setFrameUrl(nextFrameUrl)
      setError('')
    } catch (cameraError) {
      if (surfaceErrors || !frameUrlRef.current) {
        setError(formatCameraError(cameraError))
      }
    } finally {
      isFetchingFrameRef.current = false
    }
  }, [])

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    stopFramePolling()
    releaseCurrentStream()
    releaseCurrentFrame()

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
        await loadUnitreeFrame({ surfaceErrors: true })
      }
    } catch (cameraError) {
      setError(formatCameraError(cameraError))
    } finally {
      setLoading(false)
    }
  }, [loadUnitreeFrame, releaseCurrentFrame, releaseCurrentStream, stopFramePolling])

  useEffect(() => {
    refresh()

    return () => {
      stopFramePolling()
      releaseCurrentStream()
      releaseCurrentFrame()
    }
  }, [refresh, releaseCurrentFrame, releaseCurrentStream, stopFramePolling])

  useEffect(() => {
    if (camera.mode !== 'unitree_sdk' || !camera.enabled) {
      return undefined
    }

    const fps = Math.max(1, Math.min(Number(camera.fps) || 1, 4))
    const intervalMs = Math.max(250, Math.round(1000 / fps))

    pollRef.current = setInterval(() => {
      loadUnitreeFrame({ surfaceErrors: false })
    }, intervalMs)

    return () => {
      stopFramePolling()
    }
  }, [camera.enabled, camera.fps, camera.mode, loadUnitreeFrame, stopFramePolling])

  return {
    camera,
    mediaStream,
    frameUrl,
    loading,
    error,
    refresh,
  }
}
