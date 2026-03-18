/**
 * AuthContext.jsx
 * 全局登录状态管理
 * 所有页面通过 useAuth() 获取当前用户信息和登录/登出方法
 */
import React, { createContext, useContext, useState, useEffect } from 'react'
import { authAPI } from '../services/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser]       = useState(null)   // { username, display_name, role }
  const [token, setToken]     = useState(null)
  const [loading, setLoading] = useState(true)   // 初始化时检查本地Token

  // 页面刷新时，从 localStorage 恢复登录状态
  useEffect(() => {
    const savedToken = localStorage.getItem('chadwick_token')
    const savedUser  = localStorage.getItem('chadwick_user')
    if (savedToken && savedUser) {
      setToken(savedToken)
      setUser(JSON.parse(savedUser))
    }
    setLoading(false)
  }, [])

  const login = async (username, password, role) => {
    const data = await authAPI.login(username, password, role)
    setToken(data.access_token)
    setUser(data.user)
    localStorage.setItem('chadwick_token', data.access_token)
    localStorage.setItem('chadwick_user',  JSON.stringify(data.user))
    return data.user
  }

  const logout = async () => {
    try { await authAPI.logout() } catch (_) {}
    setToken(null)
    setUser(null)
    localStorage.removeItem('chadwick_token')
    localStorage.removeItem('chadwick_user')
  }

  return (
    <AuthContext.Provider value={{ user, token, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
