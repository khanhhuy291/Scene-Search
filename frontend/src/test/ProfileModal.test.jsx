import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ProfileModal } from '../components/auth/ProfileModal'
import { AuthProvider } from '../context/AuthContext'
import { ToastProvider } from '../context/ToastContext'

// Mock API
vi.mock('../api/auth', () => ({
  updateProfileApi: vi.fn().mockImplementation((displayName) =>
    Promise.resolve({
      id: 'usr_test_123',
      email: 'engineer@scenesearch.ai',
      display_name: displayName,
      role: 'engineer',
      is_active: true
    })
  ),
  changePasswordApi: vi.fn().mockResolvedValue({ message: 'Password changed successfully' }),
  loginApi: vi.fn(),
  registerApi: vi.fn(),
  getMeApi: vi.fn().mockResolvedValue({
    id: 'usr_test_123',
    email: 'engineer@scenesearch.ai',
    display_name: 'Test Engineer',
    role: 'engineer',
    is_active: true
  }),
  refreshTokenApi: vi.fn(),
  logoutApi: vi.fn(),
  listUsersApi: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  updateUserRoleApi: vi.fn(),
  updateUserStatusApi: vi.fn()
}))

describe('ProfileModal & Account Settings Component', () => {
  it('renders profile modal tabs, allows display name update and tab navigation', async () => {
    // Setup initial auth session in localStorage
    localStorage.setItem(
      'scenesearch_user',
      JSON.stringify({
        id: 'usr_test_123',
        email: 'engineer@scenesearch.ai',
        name: 'Test Engineer',
        role: 'engineer'
      })
    )
    localStorage.setItem('scenesearch_jwt', 'mock_jwt_token_123')

    const onClose = vi.fn()

    render(
      <ToastProvider>
        <AuthProvider>
          <ProfileModal isOpen={true} onClose={onClose} />
        </AuthProvider>
      </ToastProvider>
    )

    // Check modal title and user details
    expect(screen.getByText(/USER PROFILE \/\/ ACCOUNT SETTINGS/i)).toBeInTheDocument()
    expect(screen.getByText(/Test Engineer/i)).toBeInTheDocument()
    expect(screen.getByText(/engineer@scenesearch.ai/i)).toBeInTheDocument()
    expect(screen.getByText(/\[ENGINEER\]/i)).toBeInTheDocument()

    // Test tab navigation to Security & Password
    const securityTab = screen.getByRole('button', { name: /SECURITY & PASSWORD/i })
    fireEvent.click(securityTab)
    expect(screen.getByText(/^CURRENT PASSWORD:$/i)).toBeInTheDocument()
    expect(screen.getByText(/^NEW PASSWORD:$/i)).toBeInTheDocument()
    expect(screen.getByText(/^CONFIRM NEW PASSWORD:$/i)).toBeInTheDocument()

    // Test tab navigation to API & Permissions
    const apiTab = screen.getByRole('button', { name: /PERMISSIONS & API/i })
    fireEvent.click(apiTab)
    expect(screen.getByText(/ROLE PRIVILEGES: \[ENGINEER\]/i)).toBeInTheDocument()
    expect(screen.getByText(/JWT BEARER AUTHENTICATION TOKEN:/i)).toBeInTheDocument()

    // Switch back to profile
    const profileTab = screen.getByRole('button', { name: /GENERAL PROFILE/i })
    fireEvent.click(profileTab)

    // Edit display name
    const input = screen.getByPlaceholderText(/Enter your display name/i)
    fireEvent.change(input, { target: { value: 'Senior ML Engineer' } })

    const saveBtn = screen.getByRole('button', { name: /SAVE NAME/i })
    fireEvent.click(saveBtn)

    await waitFor(() => {
      expect(screen.getByText(/Senior ML Engineer/i)).toBeInTheDocument()
    })
  })
})
