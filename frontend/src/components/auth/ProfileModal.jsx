import React, { useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  X,
  User,
  Shield,
  KeyRound,
  Check,
  Copy,
  Lock,
  Calendar,
  Terminal
} from 'lucide-react'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'

export function ProfileModal({ isOpen, onClose }) {
  const { user, updateProfile, changePassword, token } = useAuth()
  const { addToast } = useToast()

  const [activeTab, setActiveTab] = useState('profile') // 'profile' | 'security' | 'api'
  const [displayName, setDisplayName] = useState('')
  const [isSavingProfile, setIsSavingProfile] = useState(false)

  // Change password form state
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [isSavingPassword, setIsSavingPassword] = useState(false)
  const [copiedId, setCopiedId] = useState(false)
  const [copiedToken, setCopiedToken] = useState(false)

  useEffect(() => {
    if (user) {
      setDisplayName(user.name || user.display_name || '')
    }
  }, [user, isOpen])

  // Close on Escape
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isOpen) {
        onClose()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  if (!isOpen || !user) return null

  const handleUpdateDisplayName = async (e) => {
    e.preventDefault()
    if (!displayName.trim()) {
      addToast('Display name cannot be empty', 'error')
      return
    }

    setIsSavingProfile(true)
    try {
      await updateProfile(displayName.trim())
      addToast('Profile name updated successfully', 'success')
    } catch (err) {
      addToast(err.message || 'Failed to update profile', 'error')
    } finally {
      setIsSavingProfile(false)
    }
  }

  const handleChangePasswordSubmit = async (e) => {
    e.preventDefault()
    if (!currentPassword) {
      addToast('Please enter your current password', 'error')
      return
    }
    if (newPassword.length < 6) {
      addToast('New password must be at least 6 characters', 'error')
      return
    }
    if (newPassword !== confirmPassword) {
      addToast('New passwords do not match', 'error')
      return
    }

    setIsSavingPassword(true)
    try {
      await changePassword(currentPassword, newPassword)
      addToast('Password updated successfully', 'success')
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (err) {
      addToast(err.message || 'Failed to change password', 'error')
    } finally {
      setIsSavingPassword(false)
    }
  }

  const handleCopyId = () => {
    if (user.id) {
      navigator.clipboard.writeText(user.id)
      setCopiedId(true)
      addToast('User UUID copied to clipboard', 'info')
      setTimeout(() => setCopiedId(false), 2000)
    }
  }

  const handleCopyToken = () => {
    if (token) {
      navigator.clipboard.writeText(token)
      setCopiedToken(true)
      addToast('Bearer access token copied', 'info')
      setTimeout(() => setCopiedToken(false), 2000)
    }
  }

  const modalContent = (
    <AnimatePresence>
      <div
        role="dialog"
        aria-modal="true"
        className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm overflow-y-auto"
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 15 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 15 }}
          transition={{ duration: 0.18, ease: 'easeOut' }}
          className="relative w-full max-w-2xl bg-[#F7F4EE] dark:bg-[#181614] border-3 border-black shadow-[10px_10px_0px_0px_#000] p-6 sm:p-8 font-mono text-black dark:text-white my-8"
        >
          {/* Header Bar */}
          <div className="flex items-center justify-between pb-4 border-b-3 border-black">
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 bg-[#FF5500] border border-black" />
              <h2 className="font-black text-sm sm:text-base uppercase tracking-wider">
                USER PROFILE // ACCOUNT SETTINGS
              </h2>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="p-1 bg-white dark:bg-stone-800 hover:bg-black hover:text-white border-2 border-black shadow-[2px_2px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all cursor-pointer"
              aria-label="Close Profile Modal"
            >
              <X className="w-5 h-5 stroke-[2.5]" />
            </button>
          </div>

          {/* User Hero Badge */}
          <div className="my-6 p-4 bg-white dark:bg-[#201D1A] border-2 border-black shadow-[4px_4px_0px_0px_#000] flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <img
                src={user.avatar}
                alt={user.name}
                className="w-14 h-14 rounded-full border-2 border-black object-cover bg-amber-100 dark:bg-stone-800"
              />
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <h3 className="font-black text-base text-black dark:text-white uppercase">
                    {user.name}
                  </h3>
                  <span
                    className={`px-2 py-0.5 text-[10px] font-black uppercase border border-black shadow-[1.5px_1.5px_0px_0px_#000] ${
                      user.role === 'admin'
                        ? 'bg-[#FF5500] text-black'
                        : 'bg-[#00D084] text-black'
                    }`}
                  >
                    [{user.role.toUpperCase()}]
                  </span>
                </div>
                <p className="text-xs text-stone-600 dark:text-stone-400 font-sans font-medium">
                  {user.email}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 text-[10px] font-mono">
              <span className="inline-flex items-center gap-1.5 px-2 py-1 bg-[#00D084]/20 border border-black text-black dark:text-white font-black">
                <span className="w-2 h-2 rounded-full bg-[#00D084] animate-ping" />
                ACTIVE
              </span>
              <button
                type="button"
                onClick={handleCopyId}
                className="px-2 py-1 bg-white dark:bg-stone-800 hover:bg-black hover:text-white border border-black font-bold uppercase transition-colors flex items-center gap-1 cursor-pointer"
                title="Copy User UUID"
              >
                {copiedId ? (
                  <Check className="w-3 h-3 text-[#00D084]" />
                ) : (
                  <Copy className="w-3 h-3" />
                )}
                <span>UUID</span>
              </button>
            </div>
          </div>

          {/* Navigation Tabs */}
          <div className="flex items-center gap-2 border-b-2 border-black pb-3 text-xs font-black uppercase">
            {[
              { id: 'profile', label: '[01 // GENERAL PROFILE]', icon: User },
              { id: 'security', label: '[02 // SECURITY & PASSWORD]', icon: KeyRound },
              { id: 'api', label: '[03 // PERMISSIONS & API]', icon: Shield }
            ].map((tab) => {
              const Icon = tab.icon
              const isActive = activeTab === tab.id
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveTab(tab.id)}
                  className={`px-3 py-2 border-2 transition-all cursor-pointer flex items-center gap-1.5 ${
                    isActive
                      ? 'bg-black text-white border-black shadow-[3px_3px_0px_0px_#FF5500]'
                      : 'bg-white dark:bg-stone-800 text-black dark:text-white border-black hover:bg-black hover:text-white'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">{tab.label}</span>
                  <span className="sm:hidden">{tab.id.toUpperCase()}</span>
                </button>
              )
            })}
          </div>

          {/* TAB 01: GENERAL PROFILE */}
          {activeTab === 'profile' && (
            <form onSubmit={handleUpdateDisplayName} className="mt-6 space-y-5">
              <div className="space-y-1.5">
                <label className="block text-xs font-black uppercase text-black dark:text-white">
                  DISPLAY NAME / FULL NAME:
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    placeholder="Enter your display name"
                    className="flex-1 bg-white dark:bg-stone-900 border-2 border-black p-2.5 text-xs font-bold text-black dark:text-white focus:outline-none focus:ring-2 focus:ring-[#FF5500] shadow-inner"
                    required
                  />
                  <button
                    type="submit"
                    disabled={isSavingProfile}
                    className="px-5 py-2.5 bg-black hover:bg-[#00D084] text-white hover:text-black font-mono text-xs font-black uppercase tracking-wider border-2 border-black shadow-[3px_3px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all disabled:opacity-50 cursor-pointer"
                  >
                    {isSavingProfile ? 'SAVING...' : 'SAVE NAME'}
                  </button>
                </div>
                <p className="text-[11px] text-stone-500 font-sans">
                  Updates your profile name across datasets, comments, and audit logs.
                </p>
              </div>

              <div className="space-y-1.5 pt-3 border-t border-black/10">
                <label className="block text-xs font-black uppercase text-black dark:text-white">
                  ACCOUNT EMAIL (AUTHENTICATION IDENTIFIER):
                </label>
                <input
                  type="email"
                  value={user.email || ''}
                  disabled
                  className="w-full bg-stone-200 dark:bg-stone-900/60 border-2 border-black/60 p-2.5 text-xs font-bold text-stone-600 dark:text-stone-400 cursor-not-allowed"
                />
                <div className="flex items-center gap-1.5 text-[10px] text-[#00D084] font-black">
                  <Check className="w-3.5 h-3.5" />
                  <span>PRIMARY VERIFIED EMAIL</span>
                </div>
              </div>

              <div className="p-4 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black flex items-center justify-between text-xs font-mono">
                <div className="flex items-center gap-2">
                  <Calendar className="w-4 h-4 text-[#FF5500]" />
                  <span className="font-bold">MEMBER STATUS:</span>
                </div>
                <span className="font-black text-[#00D084]">VERIFIED & ACTIVE</span>
              </div>
            </form>
          )}

          {/* TAB 02: SECURITY & PASSWORD */}
          {activeTab === 'security' && (
            <form onSubmit={handleChangePasswordSubmit} className="mt-6 space-y-4">
              <div className="space-y-1">
                <label className="block text-xs font-black uppercase text-black dark:text-white">
                  CURRENT PASSWORD:
                </label>
                <div className="relative">
                  <input
                    type="password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    placeholder="••••••••"
                    className="w-full bg-white dark:bg-stone-900 border-2 border-black p-2.5 text-xs font-mono text-black dark:text-white focus:outline-none focus:ring-2 focus:ring-[#FF5500]"
                    required
                  />
                  <Lock className="w-4 h-4 absolute right-3 top-3 text-stone-400 pointer-events-none" />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="block text-xs font-black uppercase text-black dark:text-white">
                    NEW PASSWORD:
                  </label>
                  <input
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="Min 6 characters"
                    className="w-full bg-white dark:bg-stone-900 border-2 border-black p-2.5 text-xs font-mono text-black dark:text-white focus:outline-none focus:ring-2 focus:ring-[#FF5500]"
                    required
                  />
                </div>

                <div className="space-y-1">
                  <label className="block text-xs font-black uppercase text-black dark:text-white">
                    CONFIRM NEW PASSWORD:
                  </label>
                  <input
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Repeat new password"
                    className="w-full bg-white dark:bg-stone-900 border-2 border-black p-2.5 text-xs font-mono text-black dark:text-white focus:outline-none focus:ring-2 focus:ring-[#FF5500]"
                    required
                  />
                </div>
              </div>

              <div className="pt-2">
                <button
                  type="submit"
                  disabled={isSavingPassword}
                  className="w-full py-2.5 bg-black hover:bg-[#FF5500] text-white hover:text-black font-mono text-xs font-black uppercase tracking-wider border-2 border-black shadow-[3px_3px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all disabled:opacity-50 cursor-pointer flex items-center justify-center gap-2"
                >
                  <KeyRound className="w-4 h-4" />
                  <span>{isSavingPassword ? 'CHANGING PASSWORD...' : 'UPDATE PASSWORD'}</span>
                </button>
              </div>
            </form>
          )}

          {/* TAB 03: PERMISSIONS & API */}
          {activeTab === 'api' && (
            <div className="mt-6 space-y-4">
              <div className="p-4 bg-white dark:bg-stone-900 border-2 border-black space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Shield className="w-4 h-4 text-[#FF5500]" />
                    <h4 className="text-xs font-black uppercase">
                      ROLE PRIVILEGES: [{user.role.toUpperCase()}]
                    </h4>
                  </div>
                  <span className="px-2 py-0.5 bg-[#FFD700] text-black text-[9px] font-black uppercase border border-black">
                    STANDARD SCOPE
                  </span>
                </div>
                <p className="text-xs text-stone-600 dark:text-stone-400 font-sans leading-relaxed">
                  {user.role === 'admin'
                    ? 'Full Administrative Access: Video Ingestion Station, Celery Worker Inspector, User Account Provisioning & Role Delegation, Corpus Health Telemetry.'
                    : 'ML Engineer Access: Multimodal Neural Discovery, Frame-Level Annotation, Query Provenance Logs, Dataset Staging & One-Click ZIP/JSONL Export.'}
                </p>
              </div>

              {/* Bearer Token Quick Copy */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-black uppercase text-black dark:text-white flex items-center gap-1.5">
                    <Terminal className="w-3.5 h-3.5 text-[#00D084]" />
                    <span>JWT BEARER AUTHENTICATION TOKEN:</span>
                  </label>
                  <button
                    type="button"
                    onClick={handleCopyToken}
                    className="px-2 py-0.5 bg-white dark:bg-stone-800 hover:bg-black hover:text-white border border-black text-[10px] font-black uppercase flex items-center gap-1 cursor-pointer"
                  >
                    {copiedToken ? (
                      <Check className="w-3 h-3 text-[#00D084]" />
                    ) : (
                      <Copy className="w-3 h-3" />
                    )}
                    <span>{copiedToken ? 'COPIED' : 'COPY TOKEN'}</span>
                  </button>
                </div>
                <pre className="p-3 bg-black text-[#00D084] border-2 border-black text-[10px] truncate">
                  {token ? `Bearer ${token}` : 'No active session token'}
                </pre>
              </div>
            </div>
          )}

          {/* Footer Actions */}
          <div className="mt-8 pt-4 border-t-2 border-black flex justify-end">
            <button
              type="button"
              onClick={onClose}
              className="px-5 py-2 bg-white dark:bg-stone-800 hover:bg-black hover:text-white text-black dark:text-white font-mono text-xs font-black uppercase border-2 border-black shadow-[2px_2px_0px_0px_#000] cursor-pointer"
            >
              CLOSE
            </button>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  )

  return typeof document !== 'undefined' ? createPortal(modalContent, document.body) : modalContent
}
