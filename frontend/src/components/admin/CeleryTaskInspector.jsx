import React, { useState } from 'react'
import { motion } from 'framer-motion'
import {
  Cpu,
  Server,
  Activity,
  Zap,
  RefreshCw,
  Terminal,
  Search,
  Copy,
  Check,
  Clock,
  Trash2
} from 'lucide-react'
import { useToast } from '../../context/ToastContext'

export const CeleryTaskInspector = () => {
  const { addToast } = useToast()

  const [logFilter, setLogFilter] = useState('ALL')
  const [logSearch, setLogSearch] = useState('')
  const [copied, setCopied] = useState(false)

  const workers = [
    {
      id: 'cel_worker_gpu_01',
      node: 'node-eu-central-01',
      type: 'NVIDIA RTX 4090 (GPU)',
      status: 'BUSY',
      concurrency: '4 / 4 Threads',
      currentTask: 'video_ingest_task[#891] (cyberpunk_city_drive_4k.mp4)',
      vram: '14.2 / 24 GB',
      processed: 1420
    },
    {
      id: 'cel_worker_gpu_02',
      node: 'node-eu-central-01',
      type: 'NVIDIA RTX 4090 (GPU)',
      status: 'BUSY',
      concurrency: '4 / 4 Threads',
      currentTask: 'video_ingest_task[#889] (surveillance_feed_cam04.mp4)',
      vram: '9.8 / 24 GB',
      processed: 1180
    },
    {
      id: 'cel_worker_cpu_01',
      node: 'node-eu-central-02',
      type: 'AMD EPYC 7763 (CPU)',
      status: 'ONLINE',
      concurrency: '1 / 8 Threads',
      currentTask: 'audio_whisper_transcribe_task[#888]',
      vram: '1.2 / 64 GB RAM',
      processed: 3840
    },
    {
      id: 'cel_worker_cpu_02',
      node: 'node-eu-central-02',
      type: 'AMD EPYC 7763 (CPU)',
      status: 'IDLE',
      concurrency: '0 / 8 Threads',
      currentTask: 'Waiting for task dispatch...',
      vram: '0.8 / 64 GB RAM',
      processed: 2950
    }
  ]

  const mockLogs = [
    { id: 1, time: '14:05:01.120', level: 'INFO', node: 'cel_worker_gpu_01', msg: 'Connected to Redis broker redis://redis:6379/0. Task pool ready.' },
    { id: 2, time: '14:05:02.450', level: 'INFO', node: 'cel_worker_gpu_01', msg: 'Task video_ingest_task[task-891] received. Payload: cyberpunk_city_drive_4k.mp4 (248.5 MB)' },
    { id: 3, time: '14:05:03.110', level: 'INFO', node: 'cel_worker_gpu_01', msg: '[PySceneDetect] Scene boundary detection started. Found 42 keyframe scenes.' },
    { id: 4, time: '14:05:04.890', level: 'INFO', node: 'cel_worker_gpu_01', msg: '[CLIP ViT-B/32] Batched 42 keyframe tensors into CUDA memory. Running forward inference pass.' },
    { id: 5, time: '14:05:06.210', level: 'WARN', node: 'cel_worker_cpu_01', msg: 'High CPU memory pressure detected on node-eu-central-02 (78% memory threshold).' },
    { id: 6, time: '14:05:07.540', level: 'INFO', node: 'cel_worker_gpu_02', msg: '[Qdrant Upsert] Collection scenes_multimodal_v2 upsert payload 28 vectors. Cosine metric metric OK.' },
    { id: 7, time: '14:05:08.902', level: 'ERROR', node: 'cel_worker_cpu_02', msg: 'Task audio_transcribe[#872] timeout after 30s. Retrying task (Attempt 2/3).' },
    { id: 8, time: '14:05:10.015', level: 'INFO', node: 'cel_worker_gpu_01', msg: 'Task video_ingest_task[task-891] succeeded in 7.56s. Memory cleared.' }
  ]

  const filteredLogs = mockLogs.filter((log) => {
    const matchesLevel = logFilter === 'ALL' || log.level === logFilter
    const matchesSearch = log.msg.toLowerCase().includes(logSearch.toLowerCase()) || log.node.toLowerCase().includes(logSearch.toLowerCase())
    return matchesLevel && matchesSearch
  })

  const handleCopyLogs = () => {
    const text = filteredLogs.map((l) => `[${l.time}] [${l.level}] [${l.node}] ${l.msg}`).join('\n')
    navigator.clipboard.writeText(text)
    setCopied(true)
    addToast('Celery worker log telemetry copied to clipboard', 'info')
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="space-y-8 animate-fadeIn">
      {/* Banner Header */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 p-8 bg-white dark:bg-[#25211e]/95 rounded-3xl border border-stone-200 dark:border-[#403933] shadow-2xs">
        <div className="pl-3 orange-accent-line">
          <div className="flex items-center gap-2 mb-1">
            <span className="px-3 py-0.5 rounded-full bg-stone-100 dark:bg-[#315c49]/12 text-orange-700 dark:text-[#a8c0b0] border border-stone-200 dark:border-[#315c49]/35 text-[10px] font-sans font-bold uppercase tracking-widest">
              BROKER: REDIS://REDIS:6379/0
            </span>
            <span className="text-emerald-700 dark:text-[#789b86] text-xs font-mono font-bold flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-emerald-600 dark:bg-[#789b86] animate-pulse" />
              CONNECTED (1.2ms)
            </span>
          </div>
          <h2 className="text-3xl font-serif font-normal text-stone-950 dark:text-[#f3ece4] uppercase tracking-tighter mt-1">
            Celery Telemetry & Workers
          </h2>
          <p className="text-stone-500 dark:text-[#a99d92] text-xs font-sans uppercase tracking-wider mt-1">
            Distributed task queue telemetry, worker pool concurrency, and execution logs.
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={() => addToast('Refreshed Celery worker state', 'success')}
            className="flex items-center gap-2 px-4 py-2.5 rounded-full bg-stone-100 dark:bg-[#332e2a] border border-stone-300 dark:border-[#514841] text-stone-800 dark:text-[#ded3c8] text-xs font-bold uppercase tracking-wider cursor-pointer"
          >
            <RefreshCw className="w-3.5 h-3.5 text-orange-700 dark:text-[#789b86]" /> REFRESH STATE
          </button>
          <button
            type="button"
            onClick={() => addToast('Purged dead letter queue', 'success')}
            className="flex items-center gap-2 px-4 py-2.5 rounded-full bg-rose-50 dark:bg-[#3b2424]/70 border border-rose-200 dark:border-[#593534] text-rose-700 dark:text-[#d6a09c] hover:bg-rose-700 hover:text-white text-xs font-bold uppercase tracking-wider cursor-pointer"
          >
            <Trash2 className="w-3.5 h-3.5" /> PURGE DEAD QUEUE
          </button>
          <button
            type="button"
            onClick={() => addToast('Worker pool scaled to 24 threads', 'success')}
            className="flex items-center gap-2 px-5 py-2.5 rounded-full bg-stone-950 dark:bg-[#315c49] text-white dark:text-[#f3ece4] font-bold text-xs uppercase tracking-widest shadow-sm cursor-pointer"
          >
            <Zap className="w-3.5 h-3.5 text-orange-300 dark:text-[#f3ece4]" /> SCALE WORKERS
          </button>
        </div>
      </div>

      {/* 4 Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <div className="p-6 bg-white dark:bg-[#25211e]/95 rounded-3xl border border-stone-200 dark:border-[#403933] shadow-2xs space-y-2">
          <div className="flex justify-between items-center text-[10px] font-sans font-bold text-stone-500 dark:text-[#a99d92] uppercase tracking-widest">
            <span>ACTIVE WORKERS</span>
            <Server className="w-4 h-4 text-orange-700 dark:text-[#789b86]" />
          </div>
          <div className="text-3xl font-serif font-normal text-stone-950 dark:text-[#f3ece4]">4 Nodes</div>
          <p className="text-[11px] text-orange-700 dark:text-[#789b86] font-mono font-bold">24 Concurrency Threads</p>
        </div>

        <div className="p-6 bg-white dark:bg-[#25211e]/95 rounded-3xl border border-stone-200 dark:border-[#403933] shadow-2xs space-y-2">
          <div className="flex justify-between items-center text-[10px] font-sans font-bold text-stone-500 dark:text-[#a99d92] uppercase tracking-widest">
            <span>QUEUE DEPTH</span>
            <Cpu className="w-4 h-4 text-orange-700 dark:text-[#789b86]" />
          </div>
          <div className="text-3xl font-serif font-normal text-stone-950 dark:text-[#f3ece4]">18 Tasks</div>
          <p className="text-[11px] text-orange-700 dark:text-[#789b86] font-mono font-bold">12 Processing / 6 Queued</p>
        </div>

        <div className="p-6 bg-white dark:bg-[#25211e]/95 rounded-3xl border border-stone-200 dark:border-[#403933] shadow-2xs space-y-2">
          <div className="flex justify-between items-center text-[10px] font-sans font-bold text-stone-500 dark:text-[#a99d92] uppercase tracking-widest">
            <span>THROUGHPUT</span>
            <Activity className="w-4 h-4 text-emerald-700 dark:text-[#789b86]" />
          </div>
          <div className="text-3xl font-serif font-normal text-stone-950 dark:text-[#f3ece4]">42.5 / min</div>
          <p className="text-[11px] text-emerald-700 dark:text-[#789b86] font-mono font-bold">Success Rate: 99.8%</p>
        </div>

        <div className="p-6 bg-white dark:bg-[#25211e]/95 rounded-3xl border border-stone-200 dark:border-[#403933] shadow-2xs space-y-2">
          <div className="flex justify-between items-center text-[10px] font-sans font-bold text-stone-500 dark:text-[#a99d92] uppercase tracking-widest">
            <span>AVG LATENCY</span>
            <Clock className="w-4 h-4 text-orange-700 dark:text-[#789b86]" />
          </div>
          <div className="text-3xl font-serif font-normal text-stone-950 dark:text-[#f3ece4]">3.42s</div>
          <p className="text-[11px] text-orange-700 dark:text-[#789b86] font-mono font-bold">CLIP + Qdrant Index</p>
        </div>
      </div>

      {/* Worker Pool Table */}
      <div className="bg-white dark:bg-[#25211e]/95 rounded-3xl border border-stone-200 dark:border-[#403933] overflow-hidden shadow-2xs p-6 space-y-4">
        <div className="flex items-center justify-between border-b border-stone-100 dark:border-[#403933] pb-4">
          <div className="flex items-center gap-3 pl-3 orange-accent-line">
            <h3 className="text-xl font-serif font-normal text-stone-950 dark:text-[#f3ece4] uppercase tracking-tight">
              Celery Worker Pool Nodes
            </h3>
          </div>
          <span className="px-3 py-1 rounded-full bg-emerald-50 dark:bg-[#315c49]/18 text-emerald-800 dark:text-[#789b86] border border-emerald-200 dark:border-[#456f5b]/45 text-xs font-mono font-bold">
            All 4 Nodes Healthy
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-stone-50 dark:bg-[#181512] text-stone-500 dark:text-[#a99d92] uppercase tracking-widest font-sans text-[10px] font-bold border-b border-stone-200 dark:border-[#403933]">
                <th className="py-3 px-4">WORKER NODE</th>
                <th className="py-3 px-4">HARDWARE TYPE</th>
                <th className="py-3 px-4">STATUS</th>
                <th className="py-3 px-4">CONCURRENCY</th>
                <th className="py-3 px-4">ACTIVE PAYLOAD</th>
                <th className="py-3 px-4 text-right">PROCESSED</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 dark:divide-[#403933] font-mono">
              {workers.map((w) => (
                <tr key={w.id} className="hover:bg-stone-50/60 dark:hover:bg-stone-950/40 transition-colors">
                  <td className="py-3 px-4">
                    <div className="font-bold text-stone-950 dark:text-[#ded3c8]">{w.id}</div>
                    <div className="text-[10px] text-stone-500 dark:text-[#a99d92]">{w.node}</div>
                  </td>

                  <td className="py-3 px-4 text-stone-700 dark:text-[#c8bbb0]">{w.type}</td>

                  <td className="py-3 px-4">
                    <span
                      className={`inline-flex items-center gap-1.5 px-3 py-0.5 rounded-full text-[10px] font-bold ${
                        w.status === 'BUSY'
                          ? 'bg-orange-50 dark:bg-[#315c49]/12 text-orange-800 dark:text-[#a8c0b0] border border-orange-200 dark:border-[#315c49]/35'
                          : w.status === 'ONLINE'
                          ? 'bg-emerald-50 dark:bg-[#315c49]/12 text-emerald-800 dark:text-[#a8c0b0] border border-emerald-200 dark:border-[#315c49]/35'
                          : 'bg-stone-100 dark:bg-[#332e2a] text-stone-600 dark:text-[#a99d92]'
                      }`}
                    >
                      <span className={`w-1.5 h-1.5 rounded-full ${w.status === 'BUSY' ? 'bg-orange-700 dark:bg-[#789b86] animate-pulse' : 'bg-emerald-600 dark:bg-[#789b86]'}`} />
                      {w.status}
                    </span>
                  </td>

                  <td className="py-3 px-4 text-stone-700 dark:text-[#c8bbb0]">{w.concurrency}</td>
                  <td className="py-3 px-4 text-stone-700 dark:text-[#c8bbb0] max-w-xs truncate">{w.currentTask}</td>
                  <td className="py-3 px-4 text-right font-bold text-orange-700 dark:text-[#789b86]">{w.processed} jobs</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Terminal Log Viewer */}
      <div className="bg-white dark:bg-[#25211e]/95 p-6 rounded-3xl border border-stone-200 dark:border-[#403933] shadow-2xs space-y-4">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-stone-100 dark:border-[#403933] pb-4">
          <div className="flex items-center gap-3 pl-3 orange-accent-line">
            <h3 className="text-xl font-serif font-normal text-stone-950 dark:text-[#f3ece4] uppercase tracking-tight">
              Live Execution Logs
            </h3>
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center bg-stone-100 dark:bg-[#181512] p-1 rounded-full border border-stone-200 dark:border-[#403933] text-[10px] font-mono">
              {['ALL', 'INFO', 'WARN', 'ERROR'].map((lvl) => (
                <button
                  key={lvl}
                  type="button"
                  onClick={() => setLogFilter(lvl)}
                  className={`px-3 py-1 rounded-full font-bold uppercase transition-all ${
                    logFilter === lvl
                      ? 'bg-stone-950 dark:bg-[#332e2a] text-white dark:text-[#f3ece4]'
                      : 'text-stone-600 dark:text-[#a99d92] hover:text-stone-950 dark:hover:text-stone-200'
                  }`}
                >
                  {lvl}
                </button>
              ))}
            </div>

            <div className="relative">
              <Search className="w-3.5 h-3.5 text-stone-400 dark:text-[#847970] absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Filter logs..."
                value={logSearch}
                onChange={(e) => setLogSearch(e.target.value)}
                className="bg-stone-50 dark:bg-[#181512] text-stone-950 dark:text-[#f3ece4] text-xs font-mono rounded-full pl-8 pr-3 py-1.5 border border-stone-300 dark:border-[#403933] focus:border-stone-950 dark:focus:border-[#789b86] outline-none w-36"
              />
            </div>

            <button
              type="button"
              onClick={handleCopyLogs}
              className="flex items-center gap-1.5 px-4 py-1.5 rounded-full bg-stone-100 dark:bg-[#332e2a] border border-stone-300 dark:border-[#514841] hover:bg-stone-200 dark:hover:bg-[#433b35] text-stone-800 dark:text-[#ded3c8] text-xs font-mono cursor-pointer"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-700 dark:text-[#789b86]" /> : <Copy className="w-3.5 h-3.5 text-stone-600 dark:text-[#a99d92]" />}
              {copied ? 'COPIED' : 'COPY'}
            </button>
          </div>
        </div>

        <div className="p-4 rounded-2xl bg-stone-900 dark:bg-[#181512] font-mono text-xs text-stone-300 border border-stone-800 shadow-inner">
          {filteredLogs.map((log) => (
            <div key={log.id} className="flex items-start gap-3 hover:bg-stone-800/80 dark:hover:bg-[#2d2824]/90 p-1 rounded transition-colors">
              <span className="text-stone-400 dark:text-[#847970] shrink-0 text-[11px] font-mono">{log.time}</span>
              <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${log.level === 'INFO' ? 'text-emerald-400' : log.level === 'WARN' ? 'text-amber-400' : 'text-rose-400'}`}>
                {log.level}
              </span>
              <span className="text-orange-400 dark:text-[#789b86] font-bold text-[11px]">[{log.node}]</span>
              <span className="text-stone-200 dark:text-[#ded3c8]">{log.msg}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
