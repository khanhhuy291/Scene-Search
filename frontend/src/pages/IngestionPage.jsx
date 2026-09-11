import React, { useCallback, useEffect, useState } from 'react'
import { Activity, AlertTriangle, CheckCircle2, Clock3, Cpu, Database, LoaderCircle, Power, UploadCloud } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { listIngestionJobs, uploadVideo } from '../api/ingestion'
import { getEmbeddingModelStatus, loadEmbeddingModel, unloadEmbeddingModel } from '../api/admin'
import { JobTable } from '../components/ingestion/JobTable'
import { VideoDropzone } from '../components/ingestion/VideoDropzone'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'

export const IngestionPage = () => {
  const navigate = useNavigate()
  const { addToast } = useToast()
  const { token } = useAuth()
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [loadError, setLoadError] = useState('')
  const [modelStatus, setModelStatus] = useState(null)
  const [modelAction, setModelAction] = useState('')
  const [modelError, setModelError] = useState('')

  const loadJobs = useCallback(async () => {
    setLoading(true)
    setLoadError('')
    try {
      setJobs((await listIngestionJobs({ status: filter, token })).items)
    } catch (error) {
      setLoadError(error.message)
    } finally {
      setLoading(false)
    }
  }, [filter, token])

  useEffect(() => {
    loadJobs()
  }, [loadJobs])

  const refreshModelStatus = useCallback(async () => {
    try {
      setModelStatus(await getEmbeddingModelStatus(token))
      setModelError('')
    } catch (error) {
      setModelError(error.message)
    }
  }, [token])

  useEffect(() => {
    refreshModelStatus()
  }, [refreshModelStatus])

  const changeModelState = async (action) => {
    setModelAction(action)
    setModelError('')
    try {
      const result = action === 'load'
        ? await loadEmbeddingModel(token)
        : await unloadEmbeddingModel(token)
      setModelStatus(result)
      addToast(
        action === 'load' ? 'Qwen embedding model is ready.' : 'Qwen model unloaded; GPU memory released.',
        'success'
      )
    } catch (error) {
      setModelError(error.message)
      addToast(error.message, 'error')
      await refreshModelStatus()
    } finally {
      setModelAction('')
    }
  }

  const handleUpload = async (file) => {
    setUploading(true)
    setUploadProgress(0)
    try {
      const job = await uploadVideo(file, setUploadProgress, token)
      addToast('Upload complete. The ingestion worker has been queued.', 'success')
      navigate(`/ingest/jobs/${job.task_id}`)
    } catch (error) {
      addToast(error.message, 'error')
    } finally {
      setUploading(false)
    }
  }

  const counts = jobs.reduce(
    (result, job) => ({ ...result, [job.status]: (result[job.status] || 0) + 1 }),
    {}
  )

  return (
    <main className="max-w-[1700px] mx-auto px-4 sm:px-8 py-10 pb-32 space-y-8 animate-fadeIn font-sans">
      {/* Header */}
      <header className="flex flex-col lg:flex-row lg:items-end justify-between gap-5 border-b-2 border-black pb-6">
        <div className="space-y-1">
          <div className="inline-flex items-center gap-2 px-2.5 py-0.5 bg-white dark:bg-stone-900 border border-black font-mono text-[10px] font-black uppercase text-black dark:text-white shadow-[1.5px_1.5px_0px_0px_#000]">
            <UploadCloud className="w-3 h-3 text-[#FF5500]" />
            <span>OPERATIONS // INGESTION PIPELINE</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-black text-black dark:text-white uppercase tracking-tight">
            VIDEO INGESTION MANAGEMENT
          </h1>
          <p className="text-xs font-mono text-stone-600 dark:text-stone-400 max-w-2xl">
            Load Qwen3-VL on demand, upload video footage, and index 2048-dimensional scene embeddings in Qdrant.
          </p>
        </div>

        <div className="flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-stone-900 border-2 border-black font-mono text-[11px] font-bold shadow-[2px_2px_0px_0px_#000]">
          <span className="w-2 h-2 rounded-full bg-[#00D084] animate-ping" />
          <span className="text-black dark:text-white">POSTGRES + CELERY QUEUE // LIVE</span>
        </div>
      </header>

      {/* Metrics Stats Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 font-mono">
        {[
          ['TOTAL JOBS', jobs.length, Database, '#FF5500'],
          ['IN PROGRESS', (counts.processing || 0) + (counts.retrying || 0), Activity, '#FFD700'],
          ['COMPLETED', counts.completed || 0, CheckCircle2, '#00D084'],
          ['NEEDS ATTENTION', counts.failed || 0, AlertTriangle, '#EF4444']
        ].map(([label, value, Icon, accentColor]) => (
          <div
            key={label}
            className="bg-white dark:bg-[#1C1A17] border-2 border-black shadow-[4px_4px_0px_0px_#000] p-5 space-y-2"
          >
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-black uppercase tracking-wider text-stone-500">
                {label}
              </span>
              <Icon className="w-4 h-4" style={{ color: accentColor }} />
            </div>
            <p className="text-3xl font-black text-black dark:text-white tracking-tight">{value}</p>
          </div>
        ))}
      </div>

      {/* Qwen model lifecycle */}
      <section className="bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] p-5 font-mono">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className={`w-11 h-11 border-2 border-black flex items-center justify-center ${
              ['ready', 'busy'].includes(modelStatus?.state) ? 'bg-[#00D084]' : 'bg-stone-200 dark:bg-stone-700'
            }`}>
              <Cpu className="w-6 h-6 text-black" />
            </div>
            <div>
              <p className="text-[10px] font-black uppercase text-stone-500">GPU MODEL LIFECYCLE</p>
              <h2 className="text-lg font-black uppercase text-black dark:text-white">
                QWEN3-VL EMBEDDING · {modelStatus?.state?.toUpperCase() || 'UNKNOWN'}
              </h2>
              <p className="text-[11px] text-stone-500">
                {modelStatus?.gpu_memory_reserved_mb != null
                  ? `CUDA reserved: ${modelStatus.gpu_memory_reserved_mb} MB · 2048 dimensions`
                  : 'Load the model before starting ingestion or Qwen search.'}
              </p>
            </div>
          </div>
          <button
            type="button"
            disabled={modelAction || ['loading', 'unloading', 'busy'].includes(modelStatus?.state)}
            onClick={() => changeModelState(['ready', 'busy'].includes(modelStatus?.state) ? 'unload' : 'load')}
            className={`px-5 py-3 border-2 border-black font-black text-xs uppercase flex items-center justify-center gap-2 shadow-[3px_3px_0px_0px_#000] disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer ${
              ['ready', 'busy'].includes(modelStatus?.state)
                ? 'bg-red-100 text-red-900 hover:bg-red-600 hover:text-white'
                : 'bg-[#00D084] text-black hover:bg-black hover:text-white'
            }`}
          >
            {modelAction ? <LoaderCircle className="w-4 h-4 animate-spin" /> : <Power className="w-4 h-4" />}
            {modelAction === 'load' ? 'LOADING MODEL…' : modelAction === 'unload' ? 'UNLOADING…' : ['ready', 'busy'].includes(modelStatus?.state) ? 'UNLOAD MODEL' : 'LOAD MODEL'}
          </button>
        </div>
        {modelError && (
          <p className="mt-4 p-3 border-2 border-red-600 bg-red-100 dark:bg-red-950/40 text-xs font-bold text-red-900 dark:text-red-300">
            {modelError}
          </p>
        )}
      </section>

      {/* Video Upload Dropzone */}
      <VideoDropzone
        onUpload={handleUpload}
        uploading={uploading}
        uploadProgress={uploadProgress}
        disabled={!['ready', 'busy'].includes(modelStatus?.state)}
      />

      {/* Status Filter Buttons */}
      <div className="flex flex-wrap gap-2 font-mono text-xs">
        {['all', 'queued', 'processing', 'completed', 'failed'].map((status) => (
          <button
            type="button"
            key={status}
            onClick={() => setFilter(status)}
            className={`px-4 py-2 border-2 font-black uppercase transition-all cursor-pointer ${
              filter === status
                ? 'bg-black text-white border-black shadow-[2px_2px_0px_0px_#FF5500]'
                : 'bg-white dark:bg-stone-800 text-black dark:text-stone-200 border-black/60 hover:border-black hover:bg-black hover:text-white'
            }`}
          >
            [{status.toUpperCase()}]
          </button>
        ))}
      </div>

      {/* Error Banner */}
      {loadError && (
        <div className="p-4 bg-red-100 dark:bg-red-950/40 border-2 border-red-600 font-mono text-xs font-bold text-red-900 dark:text-red-300 flex items-center gap-3 shadow-[3px_3px_0px_0px_#000]">
          <AlertTriangle className="w-5 h-5 text-red-600 shrink-0" />
          <span className="flex-1">{loadError}</span>
          <button onClick={loadJobs} className="font-black underline uppercase cursor-pointer">
            RETRY
          </button>
        </div>
      )}

      {/* Jobs Table */}
      <JobTable jobs={jobs} loading={loading} onRefresh={loadJobs} />

      <p className="text-xs font-mono text-stone-500 flex items-center gap-2 pt-2">
        <Clock3 className="w-4 h-4 text-[#FF5500]" />
        <span>Processing jobs auto-refresh on their detail page every two seconds.</span>
      </p>
    </main>
  )
}
