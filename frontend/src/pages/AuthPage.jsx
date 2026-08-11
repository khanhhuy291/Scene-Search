import React, { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { LoginCard } from '../components/auth/LoginCard'
import { RegisterCard } from '../components/auth/RegisterCard'
import { Infinity as InfinityIcon, Cpu, Layers } from 'lucide-react'

export const AuthPage = () => {
  const [mode, setMode] = useState('login')

  return (
    <div className="min-h-[calc(100vh-5rem)] flex items-center justify-center p-6 sm:p-12 relative overflow-hidden bg-[#F5F0E8] dark:bg-[#181512] transition-colors duration-300">
      <div className="w-full max-w-5xl grid grid-cols-1 lg:grid-cols-2 gap-12 items-center z-10">
        {/* Left Side: Brand Showcase */}
        <div className="hidden lg:flex flex-col space-y-6">
          <div className="inline-flex items-center gap-2 px-4 py-1 rounded-full bg-white dark:bg-[#25211e] border border-stone-200 dark:border-[#403933] text-orange-700 dark:text-[#a8c0b0] text-xs font-sans font-bold tracking-widest uppercase shadow-2xs w-fit">
            <InfinityIcon className="w-4 h-4 text-orange-700 dark:text-[#789b86] stroke-[2.2]" />
            <span>ELEGANT AI LAB ARCHITECTURE</span>
          </div>

          <h1 className="text-5xl lg:text-6xl font-serif font-normal text-stone-950 dark:text-[#f3ece4] uppercase tracking-tighter leading-tight">
            SEARCH INSIDE VIDEOS WITH NATURAL LANGUAGE
          </h1>

          <p className="text-stone-600 dark:text-[#a99d92] text-sm font-sans leading-relaxed tracking-wider">
            SceneSearch leverages ViT CLIP embeddings and Qdrant HNSW vector indexes to convert video frames into high-dimensional semantic vectors. Retrieve exact scene timestamps in milliseconds.
          </p>

          <div className="grid grid-cols-2 gap-4 pt-4">
            <div className="p-5 rounded-3xl bg-white dark:bg-[#25211e]/95 border border-stone-200 dark:border-[#403933] space-y-1 shadow-2xs">
              <div className="flex items-center gap-2 text-orange-700 dark:text-[#789b86] font-bold text-xs font-mono uppercase tracking-wider">
                <Cpu className="w-4 h-4" /> CLIP ViT-L/14
              </div>
              <p className="text-xs text-stone-500 dark:text-[#a99d92] font-sans">Zero-shot video frame vector encoding</p>
            </div>

            <div className="p-5 rounded-3xl bg-white dark:bg-[#25211e]/95 border border-stone-200 dark:border-[#403933] space-y-1 shadow-2xs">
              <div className="flex items-center gap-2 text-orange-700 dark:text-[#789b86] font-bold text-xs font-mono uppercase tracking-wider">
                <Layers className="w-4 h-4" /> QDRANT HNSW
              </div>
              <p className="text-xs text-stone-500 dark:text-[#a99d92] font-sans">Sub-10ms similarity search latency</p>
            </div>
          </div>
        </div>

        {/* Right Side: Animated Login / Register Card */}
        <div className="flex justify-center">
          <AnimatePresence mode="wait">
            {mode === 'login' ? (
              <LoginCard key="login" onSwitchToRegister={() => setMode('register')} />
            ) : (
              <RegisterCard key="register" onSwitchToLogin={() => setMode('login')} />
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}
