import React, { useCallback, useEffect, useRef, useState } from 'react'
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  Clock3,
  Copy,
  Database,
  ExternalLink,
  FileVideo,
  RefreshCw,
  ShieldCheck,
  Trash2
} from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { deleteVideo, getIngestionJob } from '../api/ingestion'
import { JobStatusBadge } from '../components/ingestion/JobStatusBadge'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'

const stages = [
  { threshold: 5, label: 'Acquire', description: 'Download from restricted raw storage' },
  { threshold: 15, label: 'Decode & Privacy', description: 'Sample frames and verify anonymization' },
  { threshold: 50, label: 'Build Scenes', description: 'Group frames into temporal scenes' },
  { threshold: 65, label: 'Embed Vectors', description: 'Generate normalized SigLIP/ViT vectors' },
  { threshold: 75, label: 'Render Previews', description: 'Publish privacy-safe scene previews' },
  { threshold: 85, label: 'Persist Vectors', description: 'Upsert PostgreSQL and Qdrant records' },
  { threshold: 100, label: 'Finalize Index', description: 'Commit durable completion state' }
]

const formatDate = (value) =>
  value
    ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'medium' }).format(
        new Date(value)
      )
    : '—'
const duration = (start, end) =>
  start && end ? `${Math.max(0, Math.round((new Date(end) - new Date(start)) / 1000))}s` : '—'

export const IngestionJobPage = () => {
  const { taskId } = useParams()
  const navigate = useNavigate()
  const { addToast } = useToast()
  const { token, user } = useAuth()
  const isEngineer = user?.role === 'engineer' || user?.role === 'admin'
  const [job, setJob] = useState(null)
  const [error, setError] = useState('')
  const [refreshing, setRefreshing] = useState(true)
  const [deleting, setDeleting] = useState(false)
  const pollingStartedAt = useRef(Date.now())

  const load = useCallback(async () => {
    try {
      setJob(await getIngestionJob(taskId, { token }))
      setError('')
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setRefreshing(false)
    }
  }, [taskId, token])

  useEffect(() => {
    pollingStartedAt.current = Date.now()
    load()
  }, [load])

  const jobStatus = job?.status
  useEffect(() => {
    if (!jobStatus || ['completed', 'failed', 'cancelled'].includes(jobStatus)) return undefined

    let cancelled = false
    let timer
    const pollingDelay = () => {
      const elapsed = Date.now() - pollingStartedAt.current
      if (elapsed < 30_000) return 2_000
      if (elapsed < 300_000) return 5_000
      return 15_000
    }
    const schedule = () => {
      if (cancelled || document.hidden) return
      timer = window.setTimeout(async () => {
        await load()
        schedule()
      }, pollingDelay())
    }
    const handleVisibilityChange = () => {
      window.clearTimeout(timer)
      if (!document.hidden) load().finally(schedule)
    }

    schedule()
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [jobStatus, load])

  const copyId = async () => {
    await navigator.clipboard.writeText(taskId)
    addToast('Job ID copied to clipboard', 'info')
  }

  const handleDelete = async () => {
    if (!job?.video_id || !window.confirm('Delete this video, its queued work, previews, and search vectors? This cannot be undone.')) return
    setDeleting(true)
    try {
      await deleteVideo(job.video_id, token)
      addToast('Video and ingestion artifacts deleted.', 'success')
      navigate('/ingest')
    } catch (requestError) {
      addToast(requestError.message, 'error')
      setDeleting(false)
    }
  }

  if (error && !job) {
    return (
      <main className="max-w-3xl mx-auto px-6 py-20 font-mono">
        <div className="bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[8px_8px_0px_0px_#000] p-8 text-center space-y-4">
          <AlertTriangle className="w-10 h-10 text-red-600 mx-auto" />
          <h1 className="text-xl font-black uppercase text-black dark:text-white">
            UNABLE TO RETRIEVE INGESTION TASK
          </h1>
          <p className="text-xs text-red-600 font-bold">{error}</p>
          <div className="flex justify-center gap-3 pt-4 border-t-2 border-black">
            <Link
              to="/ingest"
              className="px-5 py-2 bg-white dark:bg-stone-800 border-2 border-black text-xs font-black uppercase shadow-[2px_2px_0px_0px_#000]"
            >
              BACK TO JOBS
            </Link>
            <button
              onClick={load}
              className="px-5 py-2 bg-black text-white hover:bg-[#FF5500] hover:text-black border-2 border-black text-xs font-black uppercase shadow-[2px_2px_0px_0px_#000]"
            >
              RETRY
            </button>
          </div>
        </div>
      </main>
    )
  }

  if (!job) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center gap-3 font-mono text-black dark:text-white">
        <div className="w-8 h-8 border-3 border-black border-t-[#FF5500] animate-spin" />
        <span className="text-xs font-black uppercase">FETCHING TASK TELEMETRY...</span>
      </div>
    )
  }

  const result = job.result || {}
  const metrics = result.metrics || {}

  return (
    <main className="max-w-[1700px] mx-auto px-4 sm:px-8 py-10 pb-32 space-y-8 animate-fadeIn font-mono text-black dark:text-white">
      <Link
        to="/ingest"
        className="inline-flex items-center gap-2 text-xs font-black uppercase tracking-wider text-stone-600 dark:text-stone-400 hover:text-black dark:hover:text-white"
      >
        <ArrowLeft className="w-4 h-4 text-[#FF5500]" /> BACK TO ALL INGESTION JOBS
      </Link>

      {/* Main Header Card */}
      <header className="bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] p-6 lg:p-8 space-y-6">
        <div className="flex flex-col lg:flex-row justify-between gap-6">
          <div className="flex gap-4 min-w-0">
            <div className="w-12 h-12 bg-black text-white border-2 border-black flex items-center justify-center shrink-0 shadow-[2px_2px_0px_0px_#FF5500]">
              <FileVideo className="w-6 h-6 text-[#FF5500]" />
            </div>

            <div className="min-w-0 space-y-1">
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="text-2xl sm:text-3xl font-black uppercase truncate">
                  {job.video_path || 'INGESTION JOB'}
                </h1>
                <JobStatusBadge status={job.status} />
              </div>

              <button
                onClick={copyId}
                className="inline-flex items-center gap-1.5 text-xs text-stone-500 hover:text-[#FF5500] font-bold cursor-pointer"
              >
                <span>TASK UUID: {job.task_id}</span>
                <Copy className="w-3 h-3" />
              </button>
            </div>
          </div>

          <div className="flex gap-2 self-start">
            <button
              onClick={() => {
                setRefreshing(true)
                load()
              }}
              className="inline-flex items-center gap-2 px-4 py-2 bg-[#F7F4EE] dark:bg-stone-800 hover:bg-black hover:text-white border-2 border-black text-xs font-black uppercase shadow-[2px_2px_0px_0px_#000] transition-all cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
              <span>REFRESH</span>
            </button>
            {isEngineer && job?.video_id && (
              <button
                disabled={deleting}
                onClick={handleDelete}
                className="inline-flex items-center gap-2 px-4 py-2 bg-red-100 hover:bg-red-600 text-red-900 hover:text-white border-2 border-red-600 text-xs font-black uppercase shadow-[2px_2px_0px_0px_#000] transition-all cursor-pointer disabled:opacity-50"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>{deleting ? 'DELETING...' : 'DELETE VIDEO'}</span>
              </button>
            )}
          </div>
        </div>

        {/* Progress Bar */}
        <div className="space-y-1.5 pt-4 border-t-2 border-black/20">
          <div className="flex justify-between text-xs font-black uppercase">
            <span>
              {job.status === 'completed'
                ? 'PIPELINE COMPLETE'
                : job.status === 'failed'
                ? 'PIPELINE TERMINATED'
                : 'PIPELINE PROCESSING IN CELERY'}
            </span>
            <span className="text-[#FF5500]">{job.progress}%</span>
          </div>

          <div className="h-3 bg-[#F7F4EE] dark:bg-stone-800 border-2 border-black overflow-hidden">
            <div
              className={`h-full transition-all duration-300 ${
                job.status === 'failed'
                  ? 'bg-red-600'
                  : job.status === 'completed'
                  ? 'bg-[#00D084]'
                  : 'bg-[#FF5500]'
              }`}
              style={{ width: `${job.progress}%` }}
            />
          </div>
        </div>
      </header>

      {/* Error Card */}
      {job.status === 'failed' && (
        <section className="bg-red-100 dark:bg-red-950/40 border-3 border-red-600 shadow-[6px_6px_0px_0px_#000] p-6 flex gap-4">
          <AlertTriangle className="w-6 h-6 text-red-600 shrink-0 mt-1" />
          <div className="space-y-1">
            <p className="font-black text-sm uppercase text-red-900 dark:text-red-300">
              INGESTION PIPELINE EXCEPTION
            </p>
            <p className="text-xs text-red-800 dark:text-red-400">
              {job.error || 'The worker did not provide an error trace.'}
            </p>
            {job.error_code && (
              <code className="inline-block mt-2 px-2 py-0.5 bg-black text-white text-xs border border-red-500 font-bold">
                {job.error_code}
              </code>
            )}
          </div>
        </section>
      )}

      {/* Main Grid: Left Stages + Right Specs */}
      <div className="grid lg:grid-cols-[1.35fr_0.65fr] gap-6">
        {/* Stages Timeline */}
        <section className="bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] p-6 space-y-4">
          <h2 className="text-sm font-black uppercase pb-3 border-b-2 border-black">
            PIPELINE EXECUTION STAGES
          </h2>

          <div className="space-y-2">
            {stages.map((stage, index) => {
              const done = job.progress >= stage.threshold
              const active =
                !done &&
                index === stages.findIndex((item) => job.progress < item.threshold) &&
                !['failed', 'completed'].includes(job.status)

              return (
                <div
                  key={stage.label}
                  className={`flex items-start gap-4 p-3 border-2 transition-all ${
                    done
                      ? 'bg-[#F7F4EE] dark:bg-stone-900 border-black'
                      : active
                      ? 'bg-black text-white border-black shadow-[3px_3px_0px_0px_#FF5500]'
                      : 'bg-white dark:bg-[#1C1A17] border-black/30 opacity-60'
                  }`}
                >
                  <div
                    className={`w-6 h-6 border flex items-center justify-center text-xs font-black shrink-0 ${
                      done
                        ? 'bg-[#00D084] text-black border-black'
                        : active
                        ? 'bg-[#FF5500] text-black border-white'
                        : 'bg-stone-200 text-stone-600 border-black'
                    }`}
                  >
                    {done ? <Check className="w-3.5 h-3.5 stroke-[3]" /> : active ? '▶' : index + 1}
                  </div>

                  <div>
                    <p className="text-xs font-black uppercase">{stage.label}</p>
                    <p className="text-[11px] opacity-80 mt-0.5">{stage.description}</p>
                  </div>
                </div>
              )
            })}
          </div>
        </section>

        {/* Right Metadata */}
        <div className="space-y-6">
          <section className="bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] p-6 space-y-4">
            <h2 className="text-sm font-black uppercase pb-3 border-b-2 border-black">
              JOB TELEMETRY METADATA
            </h2>

            <dl className="space-y-3 text-xs">
              {[
                ['VIDEO ID', job.video_id],
                ['PIPELINE V', job.pipeline_version],
                ['CREATED', formatDate(job.created_at)],
                ['STARTED', formatDate(job.started_at)],
                ['FINISHED', formatDate(job.finished_at)],
                ['ELAPSED', duration(job.started_at, job.finished_at)]
              ].map(([label, value]) => (
                <div key={label} className="flex justify-between items-center gap-4 pb-2 border-b border-black/10">
                  <dt className="text-stone-500 font-bold">{label}</dt>
                  <dd className="font-black text-right truncate max-w-[200px]">{value || '—'}</dd>
                </div>
              ))}
            </dl>
          </section>

          <section className="bg-black text-white border-3 border-black shadow-[6px_6px_0px_0px_#FF5500] p-6 space-y-2">
            <div className="flex items-center gap-2 text-[#00D084]">
              <ShieldCheck className="w-5 h-5" />
              <h2 className="text-xs font-black uppercase">PRIVACY COMPLIANCE BOUNDARY</h2>
            </div>
            <p className="text-xs text-stone-300 leading-relaxed font-sans">
              Raw high-resolution media remains isolated in restricted object storage. Only sanitized keyframes and privacy-verified previews are published to public vector search.
            </p>
          </section>
        </div>
      </div>

      {/* Completed Output Results */}
      {job.status === 'completed' && (
        <section className="bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] p-6 lg:p-8 space-y-6">
          <div className="flex items-center justify-between pb-4 border-b-2 border-black">
            <div>
              <span className="px-2 py-0.5 bg-[#00D084] text-black text-[10px] font-black uppercase border border-black shadow-[1px_1px_0px_0px_#000]">
                PIPELINE SUCCESS
              </span>
              <h2 className="text-xl font-black uppercase tracking-tight mt-1">
                INDEXED VECTOR OUTPUT
              </h2>
            </div>

            <Link
              to="/search"
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-black hover:bg-[#FF5500] text-white hover:text-black text-xs font-black uppercase border-2 border-black shadow-[3px_3px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all"
            >
              <span>SEARCH THIS VIDEO</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </Link>
          </div>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              ['SAMPLED FRAMES', metrics.sampled_frames ?? result.frames_indexed, '#FF5500'],
              ['SCENES CREATED', metrics.scenes_created ?? result.scenes_indexed ?? result.segments_indexed, '#00D084'],
              ['QDRANT VECTORS', metrics.qdrant_points_upserted ?? result.vectors_indexed ?? result.points_indexed, '#FFD700'],
              ['PREVIEWS READY', result.previews_created ?? 0, '#7C3AED']
            ].map(([label, value, color]) => (
              <div
                key={label}
                className="p-5 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black shadow-[3px_3px_0px_0px_#000] space-y-1"
              >
                <span className="text-[10px] font-black uppercase tracking-wider text-stone-500">
                  {label}
                </span>
                <p className="text-3xl font-black" style={{ color }}>
                  {value ?? '—'}
                </p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Footer Info */}
      <footer className="text-xs text-stone-500 flex flex-wrap gap-6 pt-4 border-t-2 border-black">
        <span className="flex items-center gap-1.5 font-bold">
          <Database className="w-4 h-4 text-[#FF5500]" /> POSTGRESQL STATE AUTHORITATIVE
        </span>
        <span className="flex items-center gap-1.5 font-bold">
          <Clock3 className="w-4 h-4 text-[#00D084]" /> UPDATED: {formatDate(job.updated_at)}
        </span>
      </footer>
    </main>
  )
}
