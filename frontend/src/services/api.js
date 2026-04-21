/**
 * api.js
 * 所有与后端通信的函数都在这里
 * 组员只需调用这些函数，不用关心 HTTP 细节
 *
 * 使用方式：
 *   import { robotAPI } from '../services/api'
 *   const status = await robotAPI.getStatus()
 */
import axios from 'axios'

const BASE_URL = '/api'   // vite.config.js 已配置代理到 localhost:8000

// ── Axios 实例：自动带上 JWT Token ──
const http = axios.create({ baseURL: BASE_URL })

http.interceptors.request.use(config => {
  const token = localStorage.getItem('chadwick_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  res => res.data,
  err => {
    if (err.response?.status === 401) {
      return  Promise.reject(err.response?.data?.detail || 'Username, password or role incorrect')
    }
    return Promise.reject(err.response?.data?.detail || 'Request failed')
  }
)

// ── 认证 ──
export const authAPI = {
  login:  (username, password, role) => http.post('/auth/login', { username, password, role }),
  logout: ()                          => http.post('/auth/logout'),
  me:     ()                          => http.get('/auth/me'),
}

// ── 机器人控制 ──
export const robotAPI = {
  getStatus:         ()            => http.get('/robot/status'),
  connect:           ()            => http.post('/robot/connect'),
  disconnect:        ()            => http.post('/robot/disconnect'),
  sendCommand:       (command, params) => http.post('/robot/command', { command, params }),
  eStop:             ()            => http.post('/robot/estop'),
  releaseEstop:      ()            => http.post('/robot/estop/release'),
  setArmed:          (armed)       => http.post(`/robot/arm?armed=${armed}`),
  getSafetyConfig:   ()            => http.get('/robot/safety-config'),
  updateSafetyConfig:(config)      => http.put('/robot/safety-config', config),
}

// ── 会话管理 ──
export const sessionAPI = {
  start:      (mode)       => http.post('/session/start', { mode }),
  stop:       ()           => http.post('/session/stop'),
  addTag:     (tag, note)  => http.post('/session/tag', { tag, note }),
  getCurrent: ()           => http.get('/session/current'),
  getLogs:    (sessionId)  => http.get('/session/logs', { params: { session_id: sessionId } }),
  exportCSV:  (sessionId)  => `${BASE_URL}/session/${sessionId}/export?format=csv`,
  exportJSON: (sessionId)  => `${BASE_URL}/session/${sessionId}/export?format=json`,
}
