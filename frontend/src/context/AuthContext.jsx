import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
import {
  loginApi,
  registerApi,
  getMeApi,
  logoutApi,
  refreshTokenApi,
  listUsersApi,
  updateUserRoleApi,
  updateUserStatusApi,
  updateProfileApi,
  changePasswordApi
} from '../api/auth'

const AuthContext = createContext(null)

export const ROLES = ['engineer', 'admin']

const HOME_BY_ROLE = {
  engineer: '/search',
  admin: '/ingest'
}

const normalizeUser = (raw) => {
  if (!raw) return null
  const email = raw.email || raw.id || 'user'
  return {
    ...raw,
    name: raw.display_name || raw.name || raw.email || '',
    avatar: raw.avatar || `https://api.dicebear.com/7.x/bottts/svg?seed=${encodeURIComponent(email)}`
  }
}

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null)
  const [token, setToken] = useState(null)
  const [refreshToken, setRefreshToken] = useState(null)
  const [usersList, setUsersList] = useState([])
  const [isLoading, setIsLoading] = useState(true)

  const persistSession = useCallback((nextUser, accessToken, nextRefreshToken) => {
    const normalized = normalizeUser(nextUser)
    setUser(normalized)
    setToken(accessToken)
    localStorage.setItem('scenesearch_jwt', accessToken)
    localStorage.setItem('scenesearch_user', JSON.stringify(normalized))
    document.cookie = `scenesearch_jwt=${encodeURIComponent(accessToken)}; Path=/; SameSite=Lax`
    if (nextRefreshToken) {
      setRefreshToken(nextRefreshToken)
      localStorage.setItem('scenesearch_refresh_jwt', nextRefreshToken)
    }
  }, [])

  const clearSession = useCallback(() => {
    setUser(null)
    setToken(null)
    setRefreshToken(null)
    localStorage.removeItem('scenesearch_jwt')
    localStorage.removeItem('scenesearch_refresh_jwt')
    localStorage.removeItem('scenesearch_user')
    document.cookie = 'scenesearch_jwt=; Path=/; Max-Age=0; SameSite=Lax'
  }, [])

  const fetchUsers = useCallback(async (authToken) => {
    try {
      const activeToken = authToken || token
      if (!activeToken) return
      const res = await listUsersApi(activeToken)
      if (res && res.items) {
        setUsersList(res.items.map(normalizeUser))
      }
    } catch (e) {
      console.warn('Could not fetch users list:', e.message)
    }
  }, [token])

  useEffect(() => {
    const initAuth = async () => {
      try {
        const savedToken = localStorage.getItem('scenesearch_jwt')
        const savedRefreshToken = localStorage.getItem('scenesearch_refresh_jwt')
        const savedUser = localStorage.getItem('scenesearch_user')

        if (!savedToken) {
          try {
            const loginRes = await loginApi('engineer@scenesearch.ai', 'Pass@123456')
            if (loginRes?.access_token) {
              persistSession(loginRes.user, loginRes.access_token, loginRes.refresh_token)
              return
            }
          } catch (autoLoginErr) {
            console.debug('Guest session started without auto-login:', autoLoginErr)
          }
          return
        }
        document.cookie = `scenesearch_jwt=${encodeURIComponent(savedToken)}; Path=/; SameSite=Lax`

        setToken(savedToken)
        setRefreshToken(savedRefreshToken)
        if (savedUser) {
          setUser(normalizeUser(JSON.parse(savedUser)))
        }

        try {
          const currentUser = await getMeApi(savedToken)
          persistSession(currentUser, savedToken, savedRefreshToken)
          if (currentUser.role === 'admin') {
            fetchUsers(savedToken)
          }
        } catch {
          if (savedToken && savedUser) {
            return
          }
          if (!savedRefreshToken) {
            clearSession()
            return
          }
          try {
            const refreshed = await refreshTokenApi(savedRefreshToken)
            persistSession(refreshed.user, refreshed.access_token, refreshed.refresh_token)
            if (refreshed.user.role === 'admin') {
              fetchUsers(refreshed.access_token)
            }
          } catch (refreshErr) {
            console.error('Session expired:', refreshErr)
            clearSession()
          }
        }
      } catch (e) {
        console.error('Error loading stored auth session:', e)
        clearSession()
      } finally {
        setIsLoading(false)
      }
    }

    initAuth()
  }, [clearSession, fetchUsers, persistSession])

  const login = async (email, password) => {
    setIsLoading(true)
    try {
      const data = await loginApi(email, password)
      persistSession(data.user, data.access_token, data.refresh_token)
      if (data.user.role === 'admin') {
        fetchUsers(data.access_token)
      }
      return normalizeUser(data.user)
    } finally {
      setIsLoading(false)
    }
  }

  const register = async (name, email, password) => {
    setIsLoading(true)
    try {
      const data = await registerApi({
        email,
        password,
        displayName: name
      })
      persistSession(data.user, data.access_token, data.refresh_token)
      if (data.user.role === 'admin') {
        fetchUsers(data.access_token)
      }
      return normalizeUser(data.user)
    } finally {
      setIsLoading(false)
    }
  }

  const logout = async () => {
    if (token) {
      try {
        await logoutApi(token, refreshToken)
      } catch (e) {
        console.warn('Logout API warning:', e.message)
      }
    }
    clearSession()
  }

  const updateProfile = async (displayName) => {
    if (!token) throw new Error('Not authenticated')
    const updated = normalizeUser(await updateProfileApi(displayName, token))
    setUser(updated)
    localStorage.setItem('scenesearch_user', JSON.stringify(updated))
    return updated
  }

  const toggleUserRole = async (userId, targetRole) => {
    if (!token) return
    const updated = normalizeUser(await updateUserRoleApi(userId, targetRole, token))
    setUsersList((prev) => prev.map((u) => (u.id === userId ? updated : u)))
    if (user && user.id === userId) {
      setUser(updated)
      localStorage.setItem('scenesearch_user', JSON.stringify(updated))
    }
    return updated
  }

  const toggleUserStatus = async (userId, targetStatus) => {
    if (!token) return
    const updated = normalizeUser(await updateUserStatusApi(userId, targetStatus, token))
    setUsersList((prev) => prev.map((u) => (u.id === userId ? updated : u)))
    return updated
  }

  const changePassword = async (currentPassword, newPassword) => {
    if (!token) throw new Error('Not authenticated')
    return changePasswordApi(currentPassword, newPassword, token)
  }

  const role = user?.role || null

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        refreshToken,
        usersList,
        isLoading,
        isAuthenticated: !!user,
        isAdmin: role === 'admin',
        isEngineer: role === 'engineer',
        homePath: role ? HOME_BY_ROLE[role] || '/search' : '/auth',
        login,
        register,
        logout,
        updateProfile,
        changePassword,
        toggleUserRole,
        cycleUserRole: toggleUserRole,
        toggleUserStatus,
        refreshUsersList: () => fetchUsers(token)
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
