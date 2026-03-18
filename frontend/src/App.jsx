import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import LoginPage from './pages/LoginPage'
import OperatorPage from './pages/OperatorPage'
import SupervisorPage from './pages/SupervisorPage'

// 路由守卫：未登录跳转到登录页
function PrivateRoute({ children, requiredRole }) {
  const { user, loading } = useAuth()
  if (loading) return <div style={{ color: 'var(--dim)', padding: 40 }}>Loading...</div>
  if (!user) return <Navigate to="/login" replace />
  if (requiredRole && user.role !== requiredRole) {
    return <Navigate to={user.role === 'supervisor' ? '/supervisor' : '/operator'} replace />
  }
  return children
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route path="/operator" element={
          <PrivateRoute requiredRole="operator">
            <OperatorPage />
          </PrivateRoute>
        } />

        <Route path="/supervisor" element={
          <PrivateRoute requiredRole="supervisor">
            <SupervisorPage />
          </PrivateRoute>
        } />

        {/* 默认跳转到登录 */}
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </AuthProvider>
  )
}
