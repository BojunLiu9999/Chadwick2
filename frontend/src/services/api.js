/**
 * API helpers for backend communication.
 */
import axios from 'axios'

const BASE_URL = '/api'

const http = axios.create({ baseURL: BASE_URL })

http.interceptors.request.use(config => {
  const token = localStorage.getItem('chadwick_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  res => res.data,
  err => {
    if (err.response?.status === 401) {
      return Promise.reject(err.response?.data?.detail || 'Username, password or role incorrect')
    }
    return Promise.reject(err.response?.data?.detail || 'Request failed')
  },
)

export const authAPI = {
  login: (username, password, role) => http.post('/auth/login', { username, password, role }),
  logout: () => http.post('/auth/logout'),
  me: () => http.get('/auth/me'),
}

export const robotAPI = {
  getStatus: () => http.get('/robot/status'),
  connect: () => http.post('/robot/connect'),
  disconnect: () => http.post('/robot/disconnect'),
  sendCommand: (command, params) => http.post('/robot/command', { command, params }),
  eStop: () => http.post('/robot/estop'),
  releaseEstop: () => http.post('/robot/estop/release'),
  setArmed: armed => http.post(`/robot/arm?armed=${armed}`),
  getSafetyConfig: () => http.get('/robot/safety-config'),
  updateSafetyConfig: config => http.put('/robot/safety-config', config),
}

export const sessionAPI = {
  start: mode => http.post('/session/start', { mode }),
  pause: () => http.post('/session/pause'),
  stop: () => http.post('/session/stop'),
  addTag: (tag, note) => http.post('/session/tag', { tag, note }),
  getCurrent: () => http.get('/session/current'),
  getLogs: sessionId => http.get('/session/logs', { params: { session_id: sessionId } }),
  exportCSV: sessionId => `${BASE_URL}/session/${sessionId}/export?format=csv`,
  exportJSON: sessionId => `${BASE_URL}/session/${sessionId}/export?format=json`,
}
