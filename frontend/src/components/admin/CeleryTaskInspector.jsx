import React, { useMemo, useState } from 'react'
import { Cpu, Server, Activity, RefreshCw, Search, Copy, Check, Clock, Terminal } from 'lucide-react'
import { useToast } from '../../context/ToastContext'

export const CeleryTaskInspector = ({ telemetry, onRefresh, loading }) => {
  const { addToast } = useToast()
  const [logFilter, setLogFilter] = useState('ALL')
  const [logSearch, setLogSearch] = useState('')
  const [copied, setCopied] = useState(false)

  const workers = telemetry?.workers?.workers || []

  const jobRows = useMemo(() => {
    const jobs = telemetry?.recent_jobs || []
    return jobs.filter((job) => {
      const blob = `${job.task_id} ${job.video_path} ${job.status} ${job.error || ''}`
      const matchesLevel =
        logFilter === 'ALL' ||
        (logFilter === 'ERROR' && job.status === 'failed') ||
        (logFilter === 'WARN' && job.status === 'retrying') ||
        (logFilter === 'INFO' && job.status !== 'failed')
      const matchesSearch = blob.toLowerCase().includes(logSearch.toLowerCase())
      return matchesLevel && matchesSearch
    })
  }, [telemetry?.recent_jobs, logFilter, logSearch])

  const handleCopyLogs = () => {
    const text = jobRows
      .map((job) => `[${job.status.toUpperCase()}] [${job.task_id}] ${job.video_path}${job.error ? ` — ${job.error}` : ''}`)
      .join('\n')
    navigator.clipboard.writeText(text)
    setCopied(true)
    addToast('Copied recent ingestion jobs', 'info')
    setTimeout(() => setCopied(false), 2000)
  }

  const busy = workers.filter((w) => w.status === 'BUSY').length

  return (
    <div className="space-y-6 font-mono animate-fadeIn">
      {/* Top Banner */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 p-6 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000]">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 bg-[#FF5500] text-black text-[10px] font-black uppercase border border-black shadow-[1px_1px_0px_0px_#000]">
              BROKER // {telemetry?.workers?.broker || 'UNKNOWN'}
            </span>
            <span
              className={`text-xs font-black uppercase flex items-center gap-1 ${
                telemetry?.workers?.reachable ? 'text-[#00D084]' : 'text-red-600'
              }`}
            >
              <span
                className={`w-2 h-2 rounded-full ${
                  telemetry?.workers?.reachable ? 'bg-[#00D084] animate-ping' : 'bg-red-600'
                }`}
              />
              {telemetry?.workers?.reachable ? '[INSPECT ONLINE]' : '[NO WORKERS]'}
            </span>
          </div>
          <h2 className="text-2xl font-black uppercase tracking-tight text-black dark:text-white">
            CELERY TELEMETRY & WORKER POOL
          </h2>
        </div>

        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="flex items-center gap-2 px-5 py-2.5 bg-black hover:bg-[#FF5500] text-white hover:text-black text-xs font-black uppercase border-2 border-black shadow-[3px_3px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all cursor-pointer disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>REFRESH POOL</span>
        </button>
      </div>

      {/* 4 Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-5 bg-white dark:bg-[#1C1A17] border-2 border-black shadow-[4px_4px_0px_0px_#000] space-y-1">
          <div className="flex justify-between items-center text-[10px] font-black text-stone-500 uppercase tracking-widest">
            <span>ACTIVE WORKERS</span>
            <Server className="w-4 h-4 text-[#FF5500]" />
          </div>
          <div className="text-3xl font-black text-black dark:text-white tracking-tight">
            {telemetry?.workers?.worker_count ?? 0}
          </div>
          <p className="text-[11px] text-[#FF5500] font-black uppercase">{busy} NODES BUSY</p>
        </div>

        <div className="p-5 bg-white dark:bg-[#1C1A17] border-2 border-black shadow-[4px_4px_0px_0px_#000] space-y-1">
          <div className="flex justify-between items-center text-[10px] font-black text-stone-500 uppercase tracking-widest">
            <span>IN FLIGHT JOBS</span>
            <Cpu className="w-4 h-4 text-[#00D084]" />
          </div>
          <div className="text-3xl font-black text-black dark:text-white tracking-tight">
            {telemetry?.workers?.queue_depth ?? 0}
          </div>
          <p className="text-[11px] text-[#00D084] font-black uppercase">ACTIVE + RESERVED</p>
        </div>

        <div className="p-5 bg-white dark:bg-[#1C1A17] border-2 border-black shadow-[4px_4px_0px_0px_#000] space-y-1">
          <div className="flex justify-between items-center text-[10px] font-black text-stone-500 uppercase tracking-widest">
            <span>INGESTION JOBS</span>
            <Activity className="w-4 h-4 text-[#FFD700]" />
          </div>
          <div className="text-3xl font-black text-black dark:text-white tracking-tight">
            {telemetry?.job_total ?? 0}
          </div>
          <p className="text-[11px] text-stone-600 dark:text-stone-400 font-bold uppercase">STORED IN POSTGRES</p>
        </div>

        <div className="p-5 bg-white dark:bg-[#1C1A17] border-2 border-black shadow-[4px_4px_0px_0px_#000] space-y-1">
          <div className="flex justify-between items-center text-[10px] font-black text-stone-500 uppercase tracking-widest">
            <span>LAST INSPECT</span>
            <Clock className="w-4 h-4 text-black dark:text-white" />
          </div>
          <div className="text-lg font-black text-black dark:text-white mt-2">
            {telemetry?.generated_at ? new Date(telemetry.generated_at).toLocaleTimeString() : '—'}
          </div>
          <p className="text-[11px] text-stone-500 font-bold uppercase">HEARTBEAT OK</p>
        </div>
      </div>

      {/* Worker Pool Table */}
      <div className="bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] overflow-hidden">
        <div className="p-4 border-b-2 border-black flex items-center justify-between">
          <h3 className="text-xs font-black uppercase tracking-tight text-black dark:text-white">
            CELERY WORKER NODE POOL ({workers.length})
          </h3>
        </div>

        {workers.length === 0 ? (
          <p className="p-6 text-xs text-stone-500">
            [NO WORKERS ANSWERED INSPECT] // Start one with <code className="bg-black text-white px-1">make worker</code> to process jobs.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-[#F7F4EE] dark:bg-stone-900 text-black dark:text-white uppercase tracking-wider text-[11px] font-black border-b-2 border-black">
                  <th className="py-3 px-4">WORKER NODE</th>
                  <th className="py-3 px-4">STATUS</th>
                  <th className="py-3 px-4">CONCURRENCY</th>
                  <th className="py-3 px-4">ACTIVE PAYLOAD</th>
                  <th className="py-3 px-4 text-right">PROCESSED</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-black/10">
                {workers.map((w) => (
                  <tr key={w.id} className="hover:bg-[#F7F4EE] dark:hover:bg-stone-900 transition-colors">
                    <td className="py-3 px-4 font-black text-black dark:text-white">{w.id}</td>
                    <td className="py-3 px-4">
                      <span
                        className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 text-[10px] font-black uppercase border ${
                          w.status === 'BUSY'
                            ? 'bg-[#FF5500] text-black border-black shadow-[1px_1px_0px_0px_#000]'
                            : 'bg-[#00D084] text-black border-black shadow-[1px_1px_0px_0px_#000]'
                        }`}
                      >
                        {w.status}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-stone-700 dark:text-stone-300 font-bold">
                      {w.active_count} / {w.concurrency_max ?? '—'}
                    </td>
                    <td className="py-3 px-4 text-stone-700 dark:text-stone-300 truncate max-w-xs">
                      {w.active_tasks?.[0] || 'Awaiting dispatch...'}
                    </td>
                    <td className="py-3 px-4 text-right font-black text-black dark:text-white">
                      {w.processed != null ? `${w.processed} JOBS` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Jobs Log Inspector */}
      <div className="bg-white dark:bg-[#1C1A17] p-6 border-3 border-black shadow-[6px_6px_0px_0px_#000] space-y-4">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b-2 border-black pb-4">
          <div className="flex items-center gap-2">
            <Terminal className="w-4 h-4 text-[#FF5500]" />
            <h3 className="text-xs font-black uppercase tracking-tight text-black dark:text-white">
              INGESTION TASK LOG TERMINAL
            </h3>
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center bg-[#F7F4EE] dark:bg-stone-900 p-1 border-2 border-black text-[10px]">
              {['ALL', 'INFO', 'WARN', 'ERROR'].map((lvl) => (
                <button
                  key={lvl}
                  type="button"
                  onClick={() => setLogFilter(lvl)}
                  className={`px-3 py-1 font-black uppercase transition-all cursor-pointer ${
                    logFilter === lvl
                      ? 'bg-black text-white'
                      : 'text-stone-700 dark:text-stone-300 hover:text-black'
                  }`}
                >
                  {lvl}
                </button>
              ))}
            </div>

            <div className="relative">
              <Search className="w-3.5 h-3.5 text-black absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="FILTER JOBS..."
                value={logSearch}
                onChange={(e) => setLogSearch(e.target.value)}
                className="bg-[#F7F4EE] dark:bg-stone-900 text-black dark:text-white text-xs pl-8 pr-3 py-1.5 border-2 border-black uppercase font-bold outline-none w-36"
              />
            </div>

            <button
              type="button"
              onClick={handleCopyLogs}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-black hover:bg-[#FF5500] text-white hover:text-black border-2 border-black text-xs font-black uppercase shadow-[2px_2px_0px_0px_#000] cursor-pointer"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-[#00D084]" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copied ? 'COPIED' : 'COPY'}</span>
            </button>
          </div>
        </div>

        <div className="p-4 bg-black text-stone-200 border-2 border-black shadow-inner min-h-28 text-xs font-mono space-y-1.5">
          {jobRows.length === 0 ? (
            <p className="text-stone-500">[NO MATCHING JOBS RECORDED]</p>
          ) : (
            jobRows.map((job) => (
              <div key={job.task_id} className="flex items-start gap-2 hover:bg-stone-900 p-1">
                <span
                  className={`px-1 text-[10px] font-black uppercase border ${
                    job.status === 'failed'
                      ? 'bg-red-600 text-white border-red-400'
                      : job.status === 'completed'
                      ? 'bg-[#00D084] text-black border-[#00D084]'
                      : 'bg-[#FFD700] text-black border-[#FFD700]'
                  }`}
                >
                  {job.status.toUpperCase()}
                </span>
                <span className="text-[#FF5500] font-black">
                  [{job.task_id.slice(0, 8)}]
                </span>
                <span className="text-white break-all">
                  {job.video_path}
                  {job.error ? ` — ${job.error}` : ''}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
