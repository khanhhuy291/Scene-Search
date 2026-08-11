import React, { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { CheckCircle2, Clock, Cpu, Database, Film, ArrowRight } from 'lucide-react'
import { useToast } from '../../context/ToastContext'

export const TaskProgressTracker = ({ activeTask, onComplete }) => {
  const { addToast } = useToast()
  const [progress, setProgress] = useState(5)
  const [currentStepIndex, setCurrentStepIndex] = useState(0)
  const [status, setStatus] = useState('Pending')
  const [extractedScenes, setExtractedScenes] = useState(0)

  const steps = [
    { name: 'Pending & Redis Queueing', desc: 'Validating payload and dispatching to Celery worker', icon: Clock },
    { name: 'Keyframe & Scene Detection', desc: 'PySceneDetect extracting keyframes at 30 FPS', icon: Film },
    { name: 'Multimodal CLIP Embedding', desc: 'Generating 512-dim visual embeddings via ViT-B/32', icon: Cpu },
    { name: 'Qdrant Vector Indexing', desc: 'Upserting vectors into HNSW index with Cosine metric', icon: Database }
  ]

  useEffect(() => {
    if (!activeTask) return

    const interval = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 100) {
          clearInterval(interval)
          setStatus('Completed')
          addToast(`Ingestion completed for ${activeTask.filename}! 42 scenes indexed.`, 'success')
          if (onComplete) onComplete()
          return 100
        }

        const next = prev + Math.floor(Math.random() * 12) + 6
        if (next < 25) {
          setStatus('Queued')
          setCurrentStepIndex(0)
        } else if (next < 55) {
          setStatus('Processing')
          setCurrentStepIndex(1)
          setExtractedScenes(12)
        } else if (next < 85) {
          setStatus('Processing')
          setCurrentStepIndex(2)
          setExtractedScenes(28)
        } else {
          setStatus('Processing')
          setCurrentStepIndex(3)
          setExtractedScenes(42)
        }
        return next > 100 ? 100 : next
      })
    }, 900)

    return () => clearInterval(interval)
  }, [activeTask])

  if (!activeTask) return null

  return (
    <div className="bg-white dark:bg-[#25211e]/95 p-8 sm:p-10 rounded-3xl border border-stone-200 dark:border-[#403933] shadow-2xs relative overflow-hidden space-y-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-stone-100 dark:border-[#403933] pb-6">
        <div className="pl-3 orange-accent-line">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-mono text-xs text-orange-700 dark:text-[#789b86] font-bold">TASK ID: {activeTask.id}</span>
            <span
              className={`px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold uppercase ${
                status === 'Completed'
                  ? 'bg-emerald-50 dark:bg-[#1d352b]/65 text-emerald-800 dark:text-[#a8c0b0] border border-emerald-200 dark:border-[#456f5b]/55'
                  : 'bg-orange-50 dark:bg-[#1d352b]/45 text-orange-800 dark:text-[#a8c0b0] border border-orange-200 dark:border-[#315c49]/45 animate-pulse'
              }`}
            >
              {status}
            </span>
          </div>
          <h3 className="text-2xl font-serif font-normal text-stone-950 dark:text-[#f3ece4] uppercase tracking-tight">
            {activeTask.filename}
          </h3>
          <p className="text-stone-500 dark:text-[#a99d92] text-xs font-mono mt-0.5">
            File Size: {activeTask.size} • Worker Node: cel_worker_gpu_02
          </p>
        </div>

        <div className="text-right font-mono">
          <div className="text-4xl font-serif font-normal text-orange-700 dark:text-[#789b86]">{progress}%</div>
          <div className="text-[11px] text-stone-500 dark:text-[#a99d92]">Target Latency: ~3.8s</div>
        </div>
      </div>

      {/* Main Progress Bar */}
      <div className="space-y-2">
        <div className="w-full bg-stone-100 dark:bg-[#181512] h-3 rounded-full overflow-hidden border border-stone-200 dark:border-[#403933] p-0.5">
          <motion.div
            className="h-full bg-orange-700 dark:bg-[#294c3e] rounded-full"
            initial={{ width: '0%' }}
            animate={{ width: `${progress}%` }}
            transition={{ ease: 'easeOut' }}
          />
        </div>
        <div className="flex justify-between text-xs font-mono text-stone-500 dark:text-[#a99d92]">
          <span>0s Elapsed</span>
          <span>Scenes Extracted: {extractedScenes} / 42</span>
          <span>100% Completed</span>
        </div>
      </div>

      {/* 4 Pipeline Step Indicators */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 pt-2">
        {steps.map((step, idx) => {
          const Icon = step.icon
          const isDone = currentStepIndex > idx || status === 'Completed'
          const isCurrent = currentStepIndex === idx && status !== 'Completed'

          return (
            <div
              key={step.name}
              className={`p-4 rounded-2xl border transition-all ${
                isDone
                  ? 'bg-emerald-50/60 dark:bg-[#1d352b]/65 border-emerald-200 dark:border-[#456f5b]/55 text-emerald-900 dark:text-[#a8c0b0]'
                  : isCurrent
                  ? 'bg-stone-950 dark:bg-[#332e2a] text-white dark:text-[#f3ece4] border-stone-950 dark:border-[#514841] shadow-md'
                  : 'bg-stone-50 dark:bg-[#181512]/60 border-stone-200 dark:border-[#403933] text-stone-400 dark:text-[#847970]'
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <Icon className={`w-5 h-5 ${isDone ? 'text-emerald-700 dark:text-[#789b86]' : isCurrent ? 'text-orange-400 dark:text-[#789b86]' : 'text-stone-400 dark:text-[#847970]'}`} />
                {isDone ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-700 dark:text-[#789b86]" />
                ) : isCurrent ? (
                  <div className="w-2.5 h-2.5 rounded-full bg-orange-400 dark:bg-[#789b86] animate-ping" />
                ) : (
                  <span className="text-[10px] font-mono text-stone-400 dark:text-[#847970]">STEP {idx + 1}</span>
                )}
              </div>
              <h4 className="text-xs font-bold font-sans tracking-wider uppercase mb-1">{step.name}</h4>
              <p className="text-[11px] opacity-80 leading-snug">{step.desc}</p>
            </div>
          )
        })}
      </div>

      {status === 'Completed' && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="p-5 rounded-2xl bg-emerald-50 dark:bg-[#1d352b]/65 border border-emerald-200 dark:border-[#456f5b]/55 flex items-center justify-between gap-4"
        >
          <div className="flex items-center gap-3">
            <div className="p-3 rounded-full bg-white dark:bg-[#25211e] text-emerald-700 dark:text-[#789b86] border border-emerald-200 dark:border-[#456f5b]/55">
              <CheckCircle2 className="w-6 h-6" />
            </div>
            <div>
              <h4 className="text-sm font-bold text-emerald-900 dark:text-[#c1d2c6]">
                Vector Ingestion & Scene Indexing Complete!
              </h4>
              <p className="text-xs text-emerald-700 dark:text-[#789b86] font-mono">
                42 scene segments stored in Qdrant collection <code className="text-stone-900 dark:text-[#ded3c8] font-bold">scenes_multimodal_v2</code>
              </p>
            </div>
          </div>

          <a
            href="/search"
            className="px-6 py-2.5 rounded-full bg-stone-950 dark:bg-[#315c49] text-white dark:text-[#f3ece4] font-bold text-xs tracking-widest uppercase hover:bg-orange-700 dark:hover:bg-[#789b86] transition-all flex items-center gap-2 shadow-sm shrink-0"
          >
            Explore Scenes <ArrowRight className="w-4 h-4 text-orange-300 dark:text-[#f3ece4]" />
          </a>
        </motion.div>
      )}
    </div>
  )
}
