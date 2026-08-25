import React from 'react'
import { ChevronRight, Inbox, RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'
import { JobStatusBadge } from './JobStatusBadge'

const date = (value) =>
  value
    ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(
        new Date(value)
      )
    : '—'

export const JobTable = ({ jobs, loading, onRefresh }) => (
  <section className="bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] overflow-hidden font-mono">
    <div className="px-6 py-4 flex items-center justify-between border-b-2 border-black bg-[#F7F4EE] dark:bg-stone-900">
      <div>
        <h2 className="text-sm font-black uppercase text-black dark:text-white">
          INGESTION JOBS REPOSITORY
        </h2>
        <p className="text-[10px] text-stone-500 font-bold uppercase mt-0.5">
          DURABLE STATE FROM POSTGRESQL QUEUE
        </p>
      </div>
      <button
        type="button"
        onClick={onRefresh}
        className="p-2 bg-white dark:bg-stone-800 border-2 border-black hover:bg-black hover:text-white text-black dark:text-white shadow-[2px_2px_0px_0px_#000] cursor-pointer transition-all"
        aria-label="Refresh jobs"
      >
        <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
      </button>
    </div>

    {!loading && jobs.length === 0 ? (
      <div className="py-16 text-center space-y-2">
        <Inbox className="w-8 h-8 mx-auto text-stone-400" />
        <p className="font-black text-sm uppercase text-black dark:text-white">
          [NO INGESTION JOBS RECORDED]
        </p>
        <p className="text-xs text-stone-500 font-sans">
          Upload a video file above to trigger the Celery ingestion worker pipeline.
        </p>
      </div>
    ) : (
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead className="text-[10px] uppercase tracking-wider text-stone-500 bg-[#F7F4EE] dark:bg-stone-900 border-b-2 border-black font-black">
            <tr>
              <th className="px-6 py-3">VIDEO SOURCE PATH</th>
              <th className="px-4 py-3">PIPELINE STATUS</th>
              <th className="px-4 py-3">PROGRESS</th>
              <th className="px-4 py-3">CREATED AT</th>
              <th className="w-16 px-4 py-3 text-right">ACTION</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-black/10">
            {jobs.map((job) => (
              <tr key={job.task_id} className="hover:bg-[#F7F4EE] dark:hover:bg-stone-900 transition-colors">
                <td className="px-6 py-4">
                  <p className="font-black text-black dark:text-white text-xs max-w-xs truncate">
                    {job.video_path || 'UNTITLED VIDEO'}
                  </p>
                  <p className="text-[10px] text-stone-500 mt-0.5">
                    TASK: {job.task_id.slice(0, 8)} · V: {job.pipeline_version || 'legacy'}
                  </p>
                </td>
                <td className="px-4 py-4">
                  <JobStatusBadge status={job.status} />
                </td>
                <td className="px-4 py-4">
                  <div className="w-28 space-y-1">
                    <div className="flex justify-between text-[10px] font-black">
                      <span>{job.progress}%</span>
                    </div>
                    <div className="h-2 bg-[#F7F4EE] dark:bg-stone-800 border border-black overflow-hidden">
                      <div
                        className="h-full bg-[#FF5500]"
                        style={{ width: `${job.progress}%` }}
                      />
                    </div>
                  </div>
                </td>
                <td className="px-4 py-4 text-xs font-bold text-stone-600 dark:text-stone-400 whitespace-nowrap">
                  {date(job.created_at)}
                </td>
                <td className="px-4 py-4 text-right">
                  <Link
                    to={`/ingest/jobs/${job.task_id}`}
                    className="inline-flex items-center gap-1 px-2.5 py-1 bg-black hover:bg-[#FF5500] text-white hover:text-black font-black text-[10px] uppercase border border-black shadow-[2px_2px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all"
                    aria-label="Open job"
                  >
                    <span>VIEW</span>
                    <ChevronRight className="w-3 h-3" />
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )}
  </section>
)
