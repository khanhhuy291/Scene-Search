import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { AuthProvider, useAuth } from '../context/AuthContext'
import { loginApi } from '../api/auth'

vi.mock('../api/auth', () => ({
  loginApi: vi.fn(),
  registerApi: vi.fn(),
  getMeApi: vi.fn(),
  logoutApi: vi.fn(),
  refreshTokenApi: vi.fn(),
  listUsersApi: vi.fn(),
  updateUserRoleApi: vi.fn(),
  updateUserStatusApi: vi.fn(),
  updateProfileApi: vi.fn(),
  changePasswordApi: vi.fn()
}))

function SessionStatus() {
  const { user, isLoading } = useAuth()
  return <span>{isLoading ? 'loading' : user ? 'signed in' : 'guest'}</span>
}

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
})

it('starts as a guest without submitting hard-coded demo credentials', async () => {
  render(<AuthProvider><SessionStatus /></AuthProvider>)

  await waitFor(() => expect(screen.getByText('guest')).toBeInTheDocument())
  expect(loginApi).not.toHaveBeenCalled()
})
