import React, { useState, useEffect, useRef } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  Mail,
  Lock,
  User,
  ShieldCheck,
  ArrowRight,
  AlertCircle,
  Eye,
  EyeOff,
  Zap,
  ArrowLeft,
  Terminal,
  Cpu,
  Layers
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'

export function AuthPage() {
  const [searchParams] = useSearchParams()
  const initialMode = searchParams.get('mode') === 'register' ? 'register' : 'login'
  const [mode, setMode] = useState(initialMode)
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
    setErrors({})
    inputRef.current?.focus()
  }, [mode])

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
        navigate(signedIn?.role === 'admin' ? '/ingest' : homePath || '/search', { replace: true })
      } else {
        const created = await register(name, email, password)
        addToast('Account created successfully! Welcome to SceneSearch.', 'success')
        navigate(created?.role === 'admin' ? '/ingest' : homePath || '/search', { replace: true })
      }
    } catch (err) {
      addToast(err.message || 'Authentication failed', 'error')
      setErrors({ auth: err.message })
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleAutofill = (role) => {
    if (role === 'admin') {
      setEmail('admin@scenesearch.ai')
      setPassword('Pass@123456')
      addToast('Filled Demo Admin credentials', 'info')
    } else {
      setEmail('engineer@scenesearch.ai')
      setPassword('Pass@123456')
      addToast('Filled Demo Engineer credentials', 'info')
    }
    setErrors({})
  }

  return (
    <div className="min-h-screen bg-[#F7F4EE] text-[#111111] font-sans relative flex flex-col justify-between selection:bg-black selection:text-white">
      {/* Top Navbar */}
      <header className="border-b-2 border-black px-6 sm:px-10 py-4 flex items-center justify-between bg-[#F7F4EE]">
        <Link to="/" className="flex items-center gap-2 group">
          <div className="w-8 h-8 bg-black text-white flex items-center justify-center font-mono font-black text-lg tracking-tighter border border-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] group-hover:translate-x-0.5 group-hover:translate-y-0.5 group-hover:shadow-none transition-all">
            S
          </div>
          <span className="font-mono font-extrabold text-lg uppercase tracking-tight">
            SCENESEARCH<span className="text-[#FF5500]">.</span>
          </span>
        </Link>

        <Link
          to="/"
          className="font-mono text-xs font-bold uppercase tracking-wider text-stone-700 hover:text-black flex items-center gap-1.5 px-3 py-1.5 border border-black/30 hover:border-black bg-white shadow-[2px_2px_0px_0px_rgba(0,0,0,0.8)] hover:shadow-none transition-all"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>BACK TO HOME</span>
        </Link>
      </header>

      {/* Main Container */}
      <main className="flex-1 max-w-5xl w-full mx-auto p-6 sm:p-10 my-auto grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
        {/* Left Side: Brutalist Architecture Spec */}
        <div className="lg:col-span-5 space-y-6">
          <div className="inline-flex items-center gap-2 px-3 py-1 bg-white border-2 border-black shadow-[2px_2px_0px_0px_#000] font-mono text-[11px] font-black uppercase tracking-wider text-black">
            <Terminal className="w-3.5 h-3.5 text-[#FF5500]" />
            <span>AUTHENTICATION PROTOCOL // v2.4</span>
          </div>

          <h1 className="text-4xl sm:text-5xl font-black uppercase tracking-tight leading-[0.95] text-black">
            ACCESS <br />
            <span className="text-[#FF5500]">MULTIMODAL</span> <br />
            INTELLIGENCE.
          </h1>

          <p className="font-sans text-sm text-stone-700 font-medium leading-relaxed">
            Direct access to the real-time vector search index, custom evaluation suite, and video dataset pipeline.
          </p>

          <div className="space-y-3 pt-2">
            <div className="p-3.5 bg-white border-2 border-black shadow-[3px_3px_0px_0px_#000] flex items-start gap-3">
              <Cpu className="w-5 h-5 text-[#FF5500] shrink-0 mt-0.5" />
              <div>
                <h2 className="font-mono font-black text-xs uppercase tracking-tight text-black">
                  ViT CLIP + SIGLIP EMBEDDINGS
                </h2>
                <p className="font-sans text-xs text-stone-600">Zero-shot multi-vector neural frame indexing</p>
              </div>
            </div>

            <div className="p-3.5 bg-white border-2 border-black shadow-[3px_3px_0px_0px_#000] flex items-start gap-3">
              <Layers className="w-5 h-5 text-[#00D084] shrink-0 mt-0.5" />
              <div>
                <h2 className="font-mono font-black text-xs uppercase tracking-tight text-black">
                  QDRANT HNSW VECTOR ENGINE
                </h2>
                <p className="font-sans text-xs text-stone-600">Sub-10ms similarity queries across millions of scenes</p>
              </div>
            </div>
          </div>
        </div>

        {/* Right Side: Brutalist Auth Card */}
        <div className="lg:col-span-7">
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-[#F7F4EE] border-3 border-black shadow-[8px_8px_0px_0px_#000] p-6 sm:p-8 relative"
          >
            {/* Tab Selector */}
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

            {/* Demo Autofill Section (Available in Login Mode) */}
            {mode === 'login' && (
              <div className="mb-6 p-3.5 bg-white border-2 border-black shadow-[3px_3px_0px_0px_#000]">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-mono text-[10px] font-black uppercase tracking-wider text-stone-500 flex items-center gap-1">
                    <Zap className="w-3 h-3 text-[#FF5500] fill-[#FF5500]" />
                    1-CLICK DEMO AUTOFILL:
                  </span>
                  <span className="font-mono text-[9px] font-bold text-[#FF5500] uppercase">
                    READY TO TEST
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => handleAutofill('admin')}
                    className="px-3 py-1.5 bg-[#F7F4EE] hover:bg-black hover:text-white text-black font-mono text-[11px] font-bold border border-black shadow-[2px_2px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all flex items-center justify-center gap-1.5 cursor-pointer"
                  >
                    <ShieldCheck className="w-3.5 h-3.5 text-[#FF5500]" />
                    <span>ADMIN (INGEST)</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleAutofill('engineer')}
                    className="px-3 py-1.5 bg-[#F7F4EE] hover:bg-black hover:text-white text-black font-mono text-[11px] font-bold border border-black shadow-[2px_2px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all flex items-center justify-center gap-1.5 cursor-pointer"
                  >
                    <User className="w-3.5 h-3.5 text-[#00D084]" />
                    <span>ENGINEER (DATASET)</span>
                  </button>
                </div>
              </div>
            )}

            {/* Form */}
            <form onSubmit={handleSubmit} className="space-y-4">
              {errors.auth && (
                <div className="p-3 bg-red-100 border-2 border-red-600 text-red-900 font-mono text-xs font-bold flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
                  <span>{errors.auth}</span>
                </div>
              )}

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

                {mode === 'register' && password && (
                  <div className="mt-2 h-1.5 w-full bg-stone-200 border border-black">
                    <div
                      className={`h-full ${strength.color} transition-all duration-300`}
                      style={{ width: `${(strength.score / 3) * 100}%` }}
                    />
                  </div>
                )}
              </div>

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
      </main>

      {/* Footer info */}
      <footer className="border-t-2 border-black/20 px-6 py-4 bg-[#F7F4EE] text-center font-mono text-xs text-stone-600">
        SCENESEARCH // ZERO-TRUST MULTIMODAL VECTOR INTELLIGENCE
      </footer>
    </div>
  )
}
