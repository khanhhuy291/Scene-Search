const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

const parseResponse = async (response) => {
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload.detail || `Request failed (${response.status})`)
  }
  return payload
}

export const loginApi = async (email, password) => {
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password })
  })
  return parseResponse(response)
}

export const registerApi = async ({ email, password, displayName }) => {
  const response = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email,
      password,
      display_name: displayName
    })
  })
  return parseResponse(response)
}

export const getMeApi = async (token) => {
  const response = await fetch(`${API_BASE}/auth/me`, {
    headers: {
      Authorization: `Bearer ${token}`
    }
  })
  return parseResponse(response)
}

export const refreshTokenApi = async (refreshToken) => {
  const response = await fetch(`${API_BASE}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken })
  })
  return parseResponse(response)
}

export const logoutApi = async (token, refreshToken) => {
  const response = await fetch(`${API_BASE}/auth/logout`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`
    },
    body: JSON.stringify({ refresh_token: refreshToken })
  })
  return parseResponse(response)
}

export const updateProfileApi = async (displayName, token) => {
  const response = await fetch(`${API_BASE}/auth/profile`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`
    },
    body: JSON.stringify({ display_name: displayName })
  })
  return parseResponse(response)
}

export const changePasswordApi = async (currentPassword, newPassword, token) => {
  const response = await fetch(`${API_BASE}/auth/change-password`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`
    },
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword
    })
  })
  return parseResponse(response)
}

export const listUsersApi = async (token, limit = 50, offset = 0) => {
  const response = await fetch(`${API_BASE}/auth/users?limit=${limit}&offset=${offset}`, {
    headers: {
      Authorization: `Bearer ${token}`
    }
  })
  return parseResponse(response)
}

export const updateUserRoleApi = async (userId, role, token) => {
  const response = await fetch(`${API_BASE}/auth/users/${userId}/role`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`
    },
    body: JSON.stringify({ role })
  })
  return parseResponse(response)
}

export const updateUserStatusApi = async (userId, isActive, token) => {
  const response = await fetch(`${API_BASE}/auth/users/${userId}/status`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`
    },
    body: JSON.stringify({ is_active: isActive })
  })
  return parseResponse(response)
}
