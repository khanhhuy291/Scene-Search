import React, { useState } from 'react'
import { motion } from 'framer-motion'
import { Mail, Lock, User, ArrowRight } from 'lucide-react'
import { FloatingInput } from '../common/FloatingInput'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'

export const RegisterCard = ({ onSwitchToLogin }) => {
  const { register } = useAuth()
  const { addToast } = useToast()

  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('user')
  const [errors, setErrors] = useState({})
  const [isSubmitting, setIsSubmitting] = useState(false)

  const getPasswordStrength = (pass) => {
    if (!pass) return { score: 0, label: 'None', color: 'bg-stone-200 dark:bg-[#332e2a]' }
    if (pass.length < 6) return { score: 1, label: 'Weak', color: 'bg-rose-500' }
    if (pass.length < 10) return { score: 2, label: 'Medium', color: 'bg-amber-500' }
    return { score: 3, label: 'Strong', color: 'bg-emerald-500' }
  }

  const strength = getPasswordStrength(password)

  const validate = () => {
    const errs = {}
    if (!name.trim()) errs.name = 'Full name is required'
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
      await register(name, email, password, role)
      addToast('Account created successfully!', 'success')
    } catch (err) {
      addToast(err.message || 'Registration failed', 'error')
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
          CREATE ACCOUNT
        </h2>
        <p className="text-stone-500 dark:text-[#a99d92] text-xs font-sans tracking-widest uppercase">
          Join SceneSearch multimodal video intelligence lab
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-1">
        <FloatingInput
          id="name"
          name="name"
          label="Full Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          error={errors.name}
          icon={User}
          required
        />

        <FloatingInput
          id="reg_email"
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
          id="reg_password"
          name="password"
          type="password"
          label="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.password}
          icon={Lock}
          required
        />

        {/* Password Strength Indicator */}
        {password && (
          <div className="space-y-1 px-1 pb-3">
            <div className="flex justify-between items-center text-[10px] font-mono">
              <span className="text-stone-500 dark:text-[#a99d92]">Strength:</span>
              <span className="font-bold text-stone-900 dark:text-[#ded3c8] uppercase">{strength.label}</span>
            </div>
            <div className="w-full bg-stone-100 dark:bg-[#332e2a] h-1.5 rounded-full overflow-hidden border border-stone-200 dark:border-[#514841]">
              <div className={`h-full ${strength.color} transition-all`} style={{ width: `${(strength.score / 3) * 100}%` }} />
            </div>
          </div>
        )}

        {/* Role Selector */}
        <div className="mb-4">
          <label className="block text-[10px] font-sans font-bold uppercase tracking-widest text-stone-500 dark:text-[#a99d92] mb-1">
            ACCOUNT PRIVILEGE ROLE
          </label>
          <div className="grid grid-cols-2 gap-2 font-mono text-xs">
            <button
              type="button"
              onClick={() => setRole('user')}
              className={`py-2 px-3 rounded-2xl border text-center font-bold transition-all ${
                role === 'user'
                  ? 'bg-stone-950 text-white border-stone-950 dark:bg-[#315c49]/18 dark:text-[#a8c0b0] dark:border-[#315c49]/45'
                  : 'bg-stone-50 dark:bg-[#181512] border-stone-200 dark:border-[#403933] text-stone-600 dark:text-[#a99d92]'
              }`}
            >
              Standard User
            </button>
            <button
              type="button"
              onClick={() => setRole('admin')}
              className={`py-2 px-3 rounded-2xl border text-center font-bold transition-all ${
                role === 'admin'
                  ? 'bg-stone-950 text-white border-stone-950 dark:bg-[#315c49]/18 dark:text-[#a8c0b0] dark:border-[#315c49]/45'
                  : 'bg-stone-50 dark:bg-[#181512] border-stone-200 dark:border-[#403933] text-stone-600 dark:text-[#a99d92]'
              }`}
            >
              Administrator
            </button>
          </div>
        </div>

        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full py-3.5 rounded-full bg-stone-950 dark:bg-[#315c49] hover:bg-orange-700 dark:hover:bg-[#789b86] text-white dark:text-[#f3ece4] font-bold text-xs tracking-widest uppercase transition-all shadow-md flex items-center justify-center gap-2 cursor-pointer mt-4"
        >
          {isSubmitting ? (
            <div className="w-4 h-4 border-2 border-white dark:border-stone-950 border-t-transparent rounded-full animate-spin" />
          ) : (
            <>
              REGISTER NOW <ArrowRight className="w-4 h-4 text-orange-300 dark:text-[#f3ece4]" />
            </>
          )}
        </button>
      </form>

      <div className="text-center pt-2 border-t border-stone-100 dark:border-[#403933]">
        <p className="text-xs text-stone-500 dark:text-[#a99d92]">
          Already have an account?{' '}
          <button
            type="button"
            onClick={onSwitchToLogin}
            className="text-orange-700 dark:text-[#789b86] font-bold uppercase tracking-wider hover:underline"
          >
            Sign In
          </button>
        </p>
      </div>
    </motion.div>
  )
}
