import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Mail, Lock, ArrowRight } from 'lucide-react'
import { FloatingInput } from '../common/FloatingInput'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'

export const LoginCard = ({ onSwitchToRegister }) => {
  const { login, homePath } = useAuth()
  const { addToast } = useToast()
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState({})
  const [isSubmitting, setIsSubmitting] = useState(false)

  const validate = () => {
    const errs = {}
    if (!email) {
      errs.email = 'Email address is required'
    } else if (!/\S+@\S+\.\S+/.test(email)) {
      errs.email = 'Please enter a valid email format'
    }

    if (!password) {
      errs.password = 'Password is required'
    } else if (password.length < 6) {
      errs.password = 'Password must be at least 6 characters'
    }

    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!validate()) return

    setIsSubmitting(true)
    try {
      const signedIn = await login(email, password)
      addToast('Signed in successfully!', 'success')
      navigate(signedIn?.role === 'admin' ? '/ingest' : homePath || '/search', { replace: true })
    } catch (err) {
      addToast(err.message || 'Login failed', 'error')
      setErrors({ auth: err.message })
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -15 }}
      className="w-full max-w-md bg-white dark:bg-[#25211e]/95 p-8 sm:p-10 rounded-3xl border border-stone-200 dark:border-[#403933] shadow-xl space-y-6"
    >
      <div className="text-center space-y-1">
        <h2 className="text-3xl font-serif font-normal text-stone-950 dark:text-[#f3ece4] uppercase tracking-tight">
          WELCOME BACK
        </h2>
        <p className="text-stone-500 dark:text-[#a99d92] text-xs font-sans tracking-widest uppercase">
          Sign in to access video vector search & ingestion pipelines
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-2">
        <FloatingInput
          id="email"
          name="email"
          type="email"
          label="Email Address"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={errors.email}
          icon={Mail}
          required
        />

        <FloatingInput
          id="password"
          name="password"
          type="password"
          label="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.password}
          icon={Lock}
          required
        />

        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full py-3.5 rounded-full bg-stone-950 dark:bg-[#315c49] hover:bg-orange-700 dark:hover:bg-[#789b86] text-white dark:text-[#f3ece4] font-bold text-xs tracking-widest uppercase transition-all shadow-md flex items-center justify-center gap-2 cursor-pointer mt-4"
        >
          {isSubmitting ? (
            <div className="w-4 h-4 border-2 border-white dark:border-stone-950 border-t-transparent rounded-full animate-spin" />
          ) : (
            <>
              SIGN IN <ArrowRight className="w-4 h-4 text-orange-300 dark:text-[#f3ece4]" />
            </>
          )}
        </button>
      </form>

      <div className="text-center pt-2 border-t border-stone-100 dark:border-[#403933]">
        <p className="text-xs text-stone-500 dark:text-[#a99d92]">
          Don't have an account?{' '}
          <button
            type="button"
            onClick={onSwitchToRegister}
            className="text-orange-700 dark:text-[#789b86] font-bold uppercase tracking-wider hover:underline"
          >
            Create Account
          </button>
        </p>
      </div>
    </motion.div>
  )
}
