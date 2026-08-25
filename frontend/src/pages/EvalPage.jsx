import React, { useEffect, useState } from 'react'
import { BarChart3 } from 'lucide-react'
import { getEvalReport } from '../api/admin'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'

const bandMetrics = (report) => {
  const bands = report?.bands || {}
  const scored = Object.values(bands).filter((band) => band && band.scored)
  if (scored.length === 0) return null
  const avg = (key) => {
    const values = scored
      .map((band) => band[key])
      .filter((value) => typeof value === 'number' && !Number.isNaN(value))
    if (!values.length) return null
    return values.reduce((sum, value) => sum + value, 0) / values.length
  }
  return {
    precisionAt5: avg('precision_at_5'),
    precisionAt10: avg('precision_at_10'),
    recallAt50: avg('recall_at_50'),
    scoredBands: scored.length
  }
}

export const EvalPage = () => {
  const { token } = useAuth()
  const { addToast } = useToast()
  const [payload, setPayload] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!token) return
    let cancelled = false
    getEvalReport(token)
      .then((next) => {
        if (!cancelled) setPayload(next)
      })
      .catch((err) => {
        if (!cancelled) {
          setPayload({ available: false, detail: err.message })
          addToast(err.message || 'Failed to load eval report', 'error')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [addToast, token])

  const report = payload?.report
  const averages = bandMetrics(report)

  const metrics = [
    { label: 'PRECISION @ 5', value: averages?.precisionAt5 != null ? averages.precisionAt5.toFixed(2) : '—', color: '#FF5500' },
    { label: 'PRECISION @ 10', value: averages?.precisionAt10 != null ? averages.precisionAt10.toFixed(2) : '—', color: '#FF5500' },
    { label: 'RECALL @ 50', value: averages?.recallAt50 != null ? averages.recallAt50.toFixed(2) : '—', color: '#00D084' },
    { label: 'LATENCY P50', value: report?.latency_p50_ms != null ? `${Math.round(report.latency_p50_ms)} ms` : '—', color: '#FFD700' },
    { label: 'LATENCY P95', value: report?.latency_p95_ms != null ? `${Math.round(report.latency_p95_ms)} ms` : '—', color: '#FFD700' },
    { label: 'CONTROL SUITE', value: report ? `${report.controls_passed ?? 0} PASS / ${report.controls_failed ?? 0} FAIL` : '—', color: '#7C3AED' }
  ]

  return (
    <div className="max-w-[1700px] mx-auto px-4 sm:px-8 py-10 space-y-8 animate-fadeIn pb-32 font-sans">
      {/* Page Header */}
      <div className="border-b-2 border-black pb-6 space-y-1">
        <div className="inline-flex items-center gap-2 px-2.5 py-0.5 bg-white dark:bg-stone-900 border border-black font-mono text-[10px] font-black uppercase text-black dark:text-white shadow-[1.5px_1.5px_0px_0px_#000]">
          <BarChart3 className="w-3 h-3 text-[#FF5500]" />
          <span>BENCHMARKS // RETRIEVAL EVALUATION</span>
        </div>
        <h1 className="text-3xl sm:text-4xl font-black text-black dark:text-white uppercase tracking-tight">
          {report?.label || 'SYSTEM RETRIEVAL BENCHMARKS'}
        </h1>
        <p className="text-xs font-mono text-stone-600 dark:text-stone-400">
          {loading
            ? 'FETCHING LIVE BENCHMARK HARNESS OUTPUT...'
            : payload?.available
              ? `FROM ${payload.path} · GENERATED: ${payload.generated_at ? new Date(payload.generated_at).toLocaleString() : ''}`
              : payload?.detail || 'NO EVALUATION REPORT ON DISK'}
        </p>
      </div>

      {!payload?.available && !loading ? (
        <div className="p-8 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] font-mono text-xs text-stone-600 dark:text-stone-400 space-y-2">
          <p className="font-black text-black dark:text-white uppercase">
            [EVALUATION REPORT NOT YET COMPILED]
          </p>
          <p className="font-sans">
            This module ingests raw benchmarks from <code className="font-mono bg-stone-100 dark:bg-stone-800 px-1 py-0.5 border border-black text-black dark:text-white">reports/eval.json</code> generated during <code className="font-mono bg-stone-100 dark:bg-stone-800 px-1 py-0.5 border border-black text-black dark:text-white">make eval</code> runs.
          </p>
        </div>
      ) : (
        <div className="space-y-6 font-mono">
          {/* Metrics Grid */}
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {metrics.map((m) => (
              <div
                key={m.label}
                className="bg-white dark:bg-[#1C1A17] border-2 border-black shadow-[4px_4px_0px_0px_#000] p-5 space-y-2"
              >
                <span className="text-[10px] font-black uppercase tracking-wider text-stone-500">
                  {m.label}
                </span>
                <p className="text-3xl font-black text-black dark:text-white tracking-tight">{m.value}</p>
              </div>
            ))}
          </div>

          {report?.notes ? (
            <div className="p-5 bg-white dark:bg-[#1C1A17] border-2 border-black shadow-[3px_3px_0px_0px_#000] space-y-2">
              <span className="block text-[10px] font-black uppercase tracking-wider text-stone-500">
                EVALUATION NOTES & RUN CONFIGURATION
              </span>
              <p className="text-xs text-black dark:text-white font-bold leading-relaxed">
                {Array.isArray(report.notes) ? report.notes.join(' ') : report.notes}
              </p>
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}
