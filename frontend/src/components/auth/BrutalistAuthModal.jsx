import React, { useState, useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  X,
  Mail,
  Lock,
  User,
  ArrowRight,
  AlertCircle,
  Eye,
  EyeOff
} from 'lucide-react'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'

export function BrutalistAuthModal({ isOpen, initialMode = 'login', redirectOnSuccess = false, onClose }) {
  const [mode, setMode] = useState(initialMode) // 'login' | 'register'
  const { login, register, homePath } = useAuth()
  const { addToast } = useToast()
  const navigate = useNavigate()

  // Form State
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [errors, setErrors] = useState({})
  const [isSubmitting, setIsSubmitting] = useState(false)
  const inputRef = useRef(null)

  useEffect(() => {
    setMode(initialMode)
  }, [initialMode])

  useEffect(() => {
    if (isOpen) {
      setErrors({})
      setTimeout(() => inputRef.current?.focus(), 150)
    }
  }, [isOpen, mode])

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isOpen) {
        onClose?.()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  const getPasswordStrength = (pass) => {
    if (!pass) return { score: 0, label: 'NONE', color: 'bg-stone-300' }
    if (pass.length < 8) return { score: 1, label: 'WEAK (< 8 CHARS)', color: 'bg-[#FF5500]' }
    if (pass.length < 12) return { score: 2, label: 'MEDIUM', color: 'bg-[#FFD700]' }
    return { score: 3, label: 'STRONG', color: 'bg-[#00D084]' }
  }

  const strength = getPasswordStrength(password)

  const validate = () => {
    const errs = {}
    if (mode === 'register' && !name.trim()) {
      errs.name = 'Full name is required'
    }

    if (!email) {
      errs.email = 'Email address is required'
    } else if (!/\S+@\S+\.\S+/.test(email)) {
      errs.email = 'Please enter a valid email address'
    }

    if (!password) {
      errs.password = 'Password is required'
    } else if (password.length < (mode === 'register' ? 8 : 6)) {
      errs.password = `Password must be at least ${mode === 'register' ? 8 : 6} characters`
    }

    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!validate()) return

    setIsSubmitting(true)
    try {
      if (mode === 'login') {
        const signedIn = await login(email, password)
        addToast('Signed in successfully! Welcome back.', 'success')
        onClose?.()
        if (redirectOnSuccess) {
          navigate(signedIn?.role === 'admin' ? '/ingest' : homePath || '/search', { replace: true })
        }
      } else {
        const created = await register(name, email, password)
        addToast('Account created successfully! Welcome to SceneSearch.', 'success')
        onClose?.()
        if (redirectOnSuccess) {
          navigate(created?.role === 'admin' ? '/ingest' : homePath || '/search', { replace: true })
        }
      }
    } catch (err) {
      addToast(err.message || 'Authentication failed', 'error')
      setErrors({ auth: err.message })
    } finally {
      setIsSubmitting(false)
    }
  }

  if (!isOpen) return null

  const modalContent = (
    <AnimatePresence>
      <div
        role="dialog"
        aria-modal="true"
        className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
      >  {/* Backdrop */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="fixed inset-0 bg-black/60 backdrop-blur-sm transition-opacity"
        />

        {/* Brutalist Modal Container */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 20 }}
          transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
          className="relative w-full max-w-lg bg-[#F7F4EE] border-3 border-black shadow-[10px_10px_0px_0px_#000] p-6 sm:p-8 z-10 my-auto text-black overflow-hidden font-sans"
        >
          {/* Top Decorative Header Bar */}
          <div className="flex items-center justify-between pb-4 border-b-2 border-black mb-6">
            <div className="flex items-center gap-2">
              <div className="w-3.5 h-3.5 bg-[#FF5500] border border-black" />
              <span className="font-mono font-black text-xs sm:text-sm uppercase tracking-widest text-black">
                SCENESEARCH // AUTH PORTAL
              </span>
            </div>
            <button
              onClick={onClose}
              className="px-2.5 py-1 bg-black text-white hover:bg-[#FF5500] hover:text-black font-mono text-xs font-bold uppercase tracking-wider border border-black transition-colors flex items-center gap-1 cursor-pointer"
            >
              <span>ESC</span>
              <X className="w-3.5 h-3.5 stroke-[2.5]" />
            </button>
          </div>

          {/* Brutalist Tab Selector */}
          <div className="grid grid-cols-2 gap-2 p-1 bg-[#E8E2D2] border-2 border-black mb-6 font-mono text-xs font-black uppercase">
            <button
              type="button"
              onClick={() => {
                setMode('login')
                setErrors({})
              }}
              className={`py-2.5 px-3 border transition-all text-center cursor-pointer ${
                mode === 'login'
                  ? 'bg-black text-white border-black shadow-[2px_2px_0px_0px_#FF5500]'
                  : 'bg-transparent text-stone-700 border-transparent hover:text-black hover:bg-white/50'
              }`}
            >
              [01 // SIGN IN]
            </button>
            <button
              type="button"
              onClick={() => {
                setMode('register')
                setErrors({})
              }}
              className={`py-2.5 px-3 border transition-all text-center cursor-pointer ${
                mode === 'register'
                  ? 'bg-black text-white border-black shadow-[2px_2px_0px_0px_#FF5500]'
                  : 'bg-transparent text-stone-700 border-transparent hover:text-black hover:bg-white/50'
              }`}
            >
              [02 // CREATE ACCOUNT]
            </button>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Global Error Banner */}
            {errors.auth && (
              <div className="p-3 bg-red-100 border-2 border-red-600 text-red-900 font-mono text-xs font-bold flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
                <span>{errors.auth}</span>
              </div>
            )}

            {/* Name Field (Register mode only) */}
            {mode === 'register' && (
              <div>
                <label className="block font-mono text-xs font-black uppercase tracking-wider text-black mb-1">
                  FULL NAME <span className="text-[#FF5500]">*</span>
                </label>
                <div className="relative">
                  <div className="absolute left-3.5 top-1/2 -translate-y-1/2 text-stone-500 pointer-events-none">
                    <User className="w-4 h-4" />
                  </div>
                  <input
                    ref={inputRef}
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Alex Morgan"
                    className="w-full bg-white border-2 border-black pl-10 pr-4 py-2.5 font-mono text-sm font-bold text-black outline-none placeholder:text-stone-400 placeholder:font-normal focus:border-[#FF5500] focus:shadow-[3px_3px_0px_0px_#FF5500] transition-all"
                  />
                </div>
                {errors.name && (
                  <p className="font-mono text-[11px] font-bold text-red-600 mt-1 flex items-center gap-1">
                    <AlertCircle className="w-3 h-3" /> {errors.name}
                  </p>
                )}
              </div>
            )}

            {/* Email Field */}
            <div>
              <label className="block font-mono text-xs font-black uppercase tracking-wider text-black mb-1">
                EMAIL ADDRESS <span className="text-[#FF5500]">*</span>
              </label>
              <div className="relative">
                <div className="absolute left-3.5 top-1/2 -translate-y-1/2 text-stone-500 pointer-events-none">
                  <Mail className="w-4 h-4" />
                </div>
                <input
                  ref={mode === 'login' ? inputRef : undefined}
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@scenesearch.ai"
                  className="w-full bg-white border-2 border-black pl-10 pr-4 py-2.5 font-mono text-sm font-bold text-black outline-none placeholder:text-stone-400 placeholder:font-normal focus:border-[#FF5500] focus:shadow-[3px_3px_0px_0px_#FF5500] transition-all"
                />
              </div>
              {errors.email && (
                <p className="font-mono text-[11px] font-bold text-red-600 mt-1 flex items-center gap-1">
                  <AlertCircle className="w-3 h-3" /> {errors.email}
                </p>
              )}
            </div>

            {/* Password Field */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block font-mono text-xs font-black uppercase tracking-wider text-black">
                  PASSWORD <span className="text-[#FF5500]">*</span>
                </label>
                {mode === 'register' && password && (
                  <span className="font-mono text-[10px] font-extrabold uppercase">
                    STRENGTH: <span className="text-black underline">{strength.label}</span>
                  </span>
                )}
              </div>
              <div className="relative">
                <div className="absolute left-3.5 top-1/2 -translate-y-1/2 text-stone-500 pointer-events-none">
                  <Lock className="w-4 h-4" />
                </div>
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className="w-full bg-white border-2 border-black pl-10 pr-11 py-2.5 font-mono text-sm font-bold text-black outline-none placeholder:text-stone-400 placeholder:font-normal focus:border-[#FF5500] focus:shadow-[3px_3px_0px_0px_#FF5500] transition-all"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-stone-600 hover:text-black p-1 font-mono text-xs cursor-pointer"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              {errors.password && (
                <p className="font-mono text-[11px] font-bold text-red-600 mt-1 flex items-center gap-1">
                  <AlertCircle className="w-3 h-3" /> {errors.password}
                </p>
              )}

              {/* Password Strength Bar in Register Mode */}
              {mode === 'register' && password && (
                <div className="mt-2 h-1.5 w-full bg-stone-200 border border-black">
                  <div
                    className={`h-full ${strength.color} transition-all duration-300`}
                    style={{ width: `${(strength.score / 3) * 100}%` }}
                  />
                </div>
              )}
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full mt-2 py-3 bg-black hover:bg-[#FF5500] text-white hover:text-black font-mono text-sm font-black uppercase tracking-widest border-2 border-black shadow-[4px_4px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
            >
              {isSubmitting ? (
                <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
              ) : (
                <>
                  <span>{mode === 'login' ? 'AUTHENTICATE ↵' : 'REGISTER ACCOUNT ↵'}</span>
                  <ArrowRight className="w-4 h-4 stroke-[3]" />
                </>
              )}
            </button>
          </form>

          {/* Footer note */}
          <div className="mt-6 pt-4 border-t-2 border-black/20 text-center">
            <p className="font-mono text-xs text-stone-600">
              {mode === 'login' ? "DON'T HAVE AN ACCOUNT? " : 'ALREADY REGISTERED? '}
              <button
                type="button"
                onClick={() => {
                  setMode(mode === 'login' ? 'register' : 'login')
                  setErrors({})
                }}
                className="font-black text-black uppercase underline hover:text-[#FF5500] cursor-pointer"
              >
                {mode === 'login' ? 'CREATE ONE NOW' : 'SIGN IN INSTEAD'}
              </button>
            </p>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  )

  return typeof document !== 'undefined' ? createPortal(modalContent, document.body) : modalContent
}
