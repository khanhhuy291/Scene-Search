import React, { createContext, useContext, useState, useEffect } from 'react'

const AuthContext = createContext(null)

const MOCK_USERS_SEED = [
  {
    id: 'usr_admin_01',
    name: 'Alex Mercer',
    email: 'admin@scenesearch.ai',
    role: 'admin',
    status: 'active',
    avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=150&q=80',
    created: '2026-01-15'
  },
  {
    id: 'usr_dev_02',
    name: 'Elena Rostova',
    email: 'dev@scenesearch.ai',
    role: 'user',
    status: 'active',
    avatar: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=150&q=80',
    created: '2026-02-10'
  },
  {
    id: 'usr_research_03',
    name: 'Dr. Hiroshi Sato',
    email: 'hiroshi@ai.research.io',
    role: 'user',
    status: 'active',
    avatar: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=150&q=80',
    created: '2026-03-01'
  },
  {
    id: 'usr_guest_04',
    name: 'Sarah Connor',
    email: 'sarah@skynet-audit.org',
    role: 'user',
    status: 'suspended',
    avatar: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=150&q=80',
    created: '2026-04-12'
  }
]

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null)
  const [token, setToken] = useState(null)
  const [usersList, setUsersList] = useState(MOCK_USERS_SEED)
  const [isLoading, setIsLoading] = useState(true)

  // Load initial auth state from localStorage
  useEffect(() => {
    try {
      const savedToken = localStorage.getItem('scenesearch_jwt')
      const savedUser = localStorage.getItem('scenesearch_user')
      if (savedToken && savedUser) {
        setToken(savedToken)
        setUser(JSON.parse(savedUser))
      } else {
        // Default demo login as Admin for seamless initial testing experience
        const defaultAdmin = MOCK_USERS_SEED[0]
        const mockJWT = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.mock_token_admin_01'
        setToken(mockJWT)
        setUser(defaultAdmin)
        localStorage.setItem('scenesearch_jwt', mockJWT)
        localStorage.setItem('scenesearch_user', JSON.stringify(defaultAdmin))
      }
    } catch (e) {
      console.error('Error loading stored auth session', e)
    } finally {
      setIsLoading(false)
    }
  }, [])

  const login = async (email, password) => {
    setIsLoading(true)
    // Simulate FastAPI JWT OAuth2 token endpoint response delay
    await new Promise((res) => setTimeout(res, 600))

    const existingUser = usersList.find((u) => u.email.toLowerCase() === email.toLowerCase())

    if (existingUser) {
      if (existingUser.status === 'suspended') {
        setIsLoading(false)
        throw new Error('Account suspended. Please contact your system administrator.')
      }
      const fakeJWT = `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.${existingUser.id}_token`
      setUser(existingUser)
      setToken(fakeJWT)
      localStorage.setItem('scenesearch_jwt', fakeJWT)
      localStorage.setItem('scenesearch_user', JSON.stringify(existingUser))
      setIsLoading(false)
      return existingUser
    } else {
      // Allow seamless demo login for any new credentials
      const newUserObj = {
        id: `usr_${Date.now().toString().slice(-4)}`,
        name: email.split('@')[0].replace('.', ' '),
        email,
        role: email.includes('admin') ? 'admin' : 'user',
        status: 'active',
        avatar: `https://api.dicebear.com/7.x/bottts/svg?seed=${email}`,
        created: new Date().toISOString().split('T')[0]
      }
      const fakeJWT = `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.${newUserObj.id}_token`
      setUser(newUserObj)
      setToken(fakeJWT)
      setUsersList((prev) => [newUserObj, ...prev])
      localStorage.setItem('scenesearch_jwt', fakeJWT)
      localStorage.setItem('scenesearch_user', JSON.stringify(newUserObj))
      setIsLoading(false)
      return newUserObj
    }
  }

  const register = async (name, email, password, role = 'user') => {
    setIsLoading(true)
    await new Promise((res) => setTimeout(res, 700))

    const newUserObj = {
      id: `usr_${Date.now().toString().slice(-4)}`,
      name,
      email,
      role,
      status: 'active',
      avatar: `https://api.dicebear.com/7.x/bottts/svg?seed=${name}`,
      created: new Date().toISOString().split('T')[0]
    }
    const fakeJWT = `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.${newUserObj.id}_token`

    setUser(newUserObj)
    setToken(fakeJWT)
    setUsersList((prev) => [newUserObj, ...prev])
    localStorage.setItem('scenesearch_jwt', fakeJWT)
    localStorage.setItem('scenesearch_user', JSON.stringify(newUserObj))
    setIsLoading(false)
    return newUserObj
  }

  const logout = () => {
    setUser(null)
    setToken(null)
    localStorage.removeItem('scenesearch_jwt')
    localStorage.removeItem('scenesearch_user')
  }

  const toggleUserRole = (userId) => {
    setUsersList((prev) =>
      prev.map((u) => {
        if (u.id === userId) {
          const updatedRole = u.role === 'admin' ? 'user' : 'admin'
          // If current logged in user modified themselves, update local state
          if (user && user.id === userId) {
            const updatedUser = { ...user, role: updatedRole }
            setUser(updatedUser)
            localStorage.setItem('scenesearch_user', JSON.stringify(updatedUser))
          }
          return { ...u, role: updatedRole }
        }
        return u
      })
    )
  }

  const toggleUserStatus = (userId) => {
    setUsersList((prev) =>
      prev.map((u) => {
        if (u.id === userId) {
          const updatedStatus = u.status === 'active' ? 'suspended' : 'active'
          return { ...u, status: updatedStatus }
        }
        return u
      })
    )
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        usersList,
        isLoading,
        isAuthenticated: !!user,
        isAdmin: user?.role === 'admin',
        login,
        register,
        logout,
        toggleUserRole,
        toggleUserStatus
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
