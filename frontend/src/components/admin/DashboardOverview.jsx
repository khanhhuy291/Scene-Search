import React from 'react'
import { motion } from 'framer-motion'
import { Video, Cpu, HardDrive, Layers, RefreshCw, Activity } from 'lucide-react'
import { formatBytes } from '../../lib/formatBytes'

export const DashboardOverview = ({ telemetry, onRefresh, loading }) => {
  const corpus = telemetry?.corpus
  const workers = telemetry?.workers
  const storage = telemetry?.storage
  const qdrant = telemetry?.qdrant
  const jobs = telemetry?.recent_jobs || []
  const storageBytes = (storage?.buckets || []).reduce((sum, b) => sum + (b.bytes || 0), 0)

  const metrics = [
    {
      title: 'VIDEOS IN INDEX',
      value: corpus ? corpus.videos.toLocaleString() : '—',
      change: corpus ? `${corpus.keyframes.toLocaleString()} KEYFRAMES` : 'LOADING CATALOG',
      icon: Video,
      color: '#FF5500'
    },
    {
      title: 'CELERY WORKERS',
      value: workers ? String(workers.worker_count) : '—',
      change: workers?.reachable
        ? `${workers.queue_depth ?? 0} IN FLIGHT`
        : workers?.detail || 'BROKER OFFLINE',
      icon: Cpu,
      color: '#00D084'
    },
    {
      title: 'OBJECT STORAGE',
      value: formatBytes(storageBytes),
      change: storage?.reachable ? `${storage.buckets.length} BUCKETS COUNTED` : 'UNREACHABLE',
      icon: HardDrive,
      color: '#FFD700'
    },
    {
      title: 'QDRANT POINTS',
      value: qdrant?.points_count != null ? qdrant.points_count.toLocaleString() : '—',
      change: qdrant?.reachable ? `COLL: ${qdrant.collection}` : 'UNREACHABLE',
      icon: Layers,
      color: '#7C3AED'
    }
  ]

  return (
    <div className="space-y-6 font-mono animate-fadeIn">
      {/* Top Banner */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 p-6 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000]">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 bg-[#FF5500] text-black text-[10px] font-black uppercase border border-black shadow-[1px_1px_0px_0px_#000]">
              TELEMETRY V2
            </span>
            <span className="text-xs text-stone-500 font-bold">
              {telemetry?.generated_at ? `SYNC: ${new Date(telemetry.generated_at).toLocaleTimeString()}` : ''}
            </span>
          </div>
          <h2 className="text-2xl font-black uppercase tracking-tight text-black dark:text-white">
            METRICS & WORKER REALTIME MONITOR
          </h2>
        </div>

        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="flex items-center gap-2 px-5 py-2.5 bg-black hover:bg-[#FF5500] text-white hover:text-black text-xs font-black uppercase border-2 border-black shadow-[3px_3px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all cursor-pointer disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>SYNC METRICS</span>
        </button>
      </div>

      {/* 4 Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {metrics.map((m, idx) => {
          const Icon = m.icon
          return (
            <motion.div
              key={m.title}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.05 }}
              className="p-5 bg-white dark:bg-[#1C1A17] border-2 border-black shadow-[4px_4px_0px_0px_#000] space-y-2"
            >
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-black uppercase tracking-wider text-stone-500">
                  {m.title}
                </span>
                <div className="p-1.5 bg-black text-white border border-black">
                  <Icon className="w-3.5 h-3.5" style={{ color: m.color }} />
                </div>
              </div>
              <div className="text-3xl font-black text-black dark:text-white tracking-tight">
                {m.value}
              </div>
              <div className="text-[11px] font-black uppercase" style={{ color: m.color }}>
                {m.change}
              </div>
            </motion.div>
          )
        })}
      </div>

      {/* Ingestion Jobs Feed */}
      <div className="bg-white dark:bg-[#1C1A17] p-6 border-3 border-black shadow-[6px_6px_0px_0px_#000] space-y-4">
        <div className="flex items-center justify-between pb-3 border-b-2 border-black">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-[#FF5500]" />
            <h3 className="text-sm font-black uppercase tracking-tight text-black dark:text-white">
              RECENT INGESTION JOBS FEED
            </h3>
          </div>
          <span className="px-2 py-0.5 bg-black text-white text-[10px] font-bold uppercase">
            {telemetry?.job_total ?? 0} JOBS TOTAL
          </span>
        </div>

        {jobs.length === 0 ? (
          <p className="text-xs text-stone-500 py-4">[NO INGESTION JOBS RECORDED IN POSTGRES]</p>
        ) : (
          <div className="space-y-3">
            {jobs.map((task) => (
              <div
                key={task.task_id}
                className="p-4 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black shadow-[2px_2px_0px_0px_#000] flex flex-col sm:flex-row sm:items-center justify-between gap-4"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-black text-[#FF5500]">
                      #{task.task_id.slice(0, 8)}
                    </span>
                    <span className="text-xs font-bold text-black dark:text-white truncate">
                      {task.video_path}
                    </span>
                  </div>
                  {task.error && (
                    <p className="text-xs text-red-600 font-bold mt-1">[ERROR] {task.error}</p>
                  )}
                </div>

                <div className="w-48 space-y-1 shrink-0 font-mono">
                  <div className="flex justify-between text-[10px] font-black">
                    <span className="uppercase text-[#FF5500]">[{task.status}]</span>
                    <span className="text-black dark:text-white">{task.progress}%</span>
                  </div>
                  <div className="w-full bg-white dark:bg-stone-800 h-2.5 border border-black overflow-hidden">
                    <div className="bg-[#FF5500] h-full" style={{ width: `${task.progress}%` }} />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
