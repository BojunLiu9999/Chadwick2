/**
 * LoginPage.jsx
 * 登录成功后根据角色跳转到 /operator 或 /supervisor
 */
import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import styles from './LoginPage.module.css'

const DEMO_ACCOUNTS = [
  { username: 'student_01', password: 'pass123',  role: 'operator',   label: 'OPERATOR' },
  { username: 'student_02', password: 'pass123',  role: 'operator',   label: 'OPERATOR' },
  { username: 'staff_jim',  password: 'admin456', role: 'supervisor', label: 'SUPERVISOR' },
  { username: 'staff_baden',password: 'admin456', role: 'supervisor', label: 'SUPERVISOR' },
]

export default function LoginPage() {
  const { login } = useAuth()
  const navigate  = useNavigate()

  const [selectedRole, setSelectedRole] = useState('operator')
  const [username, setUsername]         = useState('')
  const [password, setPassword]         = useState('')
  const [error, setError]               = useState('')
  const [loading, setLoading]           = useState(false)

  const handleLogin = async () => {
    if (!username || !password) { setError('Please enter username and password'); return }
    setError('')
    setLoading(true)
    try {
      const user = await login(username, password, selectedRole)
      navigate(user.role === 'supervisor' ? '/supervisor' : '/operator', { replace: true })
    } catch (err) {
      setError(typeof err === 'string' ? err : 'Username, password or role incorrect')
      setPassword('')
      setTimeout(() => setError(''), 5000)
    } finally {
      setLoading(false)
    }
  }

  const fillDemo = (account) => {
    setUsername(account.username)
    setPassword(account.password)
    setSelectedRole(account.role)
    setError('')
  }

  return (
    <div className={styles.page}>
      <div className={styles.bgGrid} />

      <div className={styles.card}>
        {/* Robot icon */}
        <div className={styles.robotIcon}>🤖</div>
        <h1 className={styles.title}>CHADWICK II</h1>
        <p className={styles.subtitle}>HUMANOID ROBOTICS COMMAND CENTER · USYD TECHLAB</p>

        {/* Role selector */}
        <p className={styles.fieldLabel}>SELECT ROLE</p>
        <div className={styles.roleGrid}>
          <button
            className={`${styles.roleCard} ${selectedRole === 'operator' ? styles.roleOp : ''}`}
            onClick={() => setSelectedRole('operator')}
          >
            <span className={styles.roleIcon}>🕹️</span>
            <span className={styles.roleName}>OPERATOR</span>
            <span className={styles.roleDesc}>Student / Lab user</span>
          </button>
          <button
            className={`${styles.roleCard} ${selectedRole === 'supervisor' ? styles.roleSv : ''}`}
            onClick={() => setSelectedRole('supervisor')}
          >
            <span className={styles.roleIcon}>🛡️</span>
            <span className={styles.roleName}>SUPERVISOR</span>
            <span className={styles.roleDesc}>Staff / Researcher</span>
          </button>
        </div>

        {/* Username */}
        <div className={styles.field}>
          <label className={styles.fieldLabel}>UNIVERSITY ID / USERNAME</label>
          <input
            className={styles.input}
            type="text"
            value={username}
            placeholder="e.g. student_01"
            onChange={e => { setUsername(e.target.value); setError('')}}
            autoComplete="off"
          />
        </div>

        {/* Password */}
        <div className={styles.field}>
          <label className={styles.fieldLabel}>PASSWORD</label>
          <input
            className={styles.input}
            type="password"
            value={password}
            placeholder="••••••••"
            onChange={e => { setPassword(e.target.value); setError('')}}
            onKeyDown={e => e.key === 'Enter' && handleLogin()}
          />
        </div>

        {error && <div className={styles.error}>⛔ {error}</div>}

        <button
          className={styles.loginBtn}
          onClick={handleLogin}
          disabled={loading}
        >
          {loading ? 'AUTHENTICATING...' : '⟶  AUTHENTICATE'}
        </button>

        {/* Demo accounts */}
        <div className={styles.demoSection}>
          <p className={styles.demoTitle}>— DEMO ACCOUNTS (click to autofill) —</p>
          {DEMO_ACCOUNTS.map(a => (
            <div key={a.username} className={styles.demoRow} onClick={() => fillDemo(a)}>
              <span className={styles.demoUser}>{a.username}</span>
              <span className={styles.demoPass}>{a.password}</span>
              <span className={styles.demoRole}>{a.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
