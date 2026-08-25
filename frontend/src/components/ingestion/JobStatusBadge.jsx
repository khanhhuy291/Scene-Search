import React from 'react'

const styles = {
  queued: 'bg-sky-100 text-sky-950 border-black',
  pending: 'bg-stone-100 text-stone-900 border-black',
  processing: 'bg-[#FFD700] text-black border-black',
  retrying: 'bg-[#FF5500] text-white border-black',
  completed: 'bg-[#00D084] text-black border-black',
  failed: 'bg-red-600 text-white border-black',
  cancelled: 'bg-stone-200 text-stone-900 border-black'
}

export const JobStatusBadge = ({ status }) => (
  <span
    className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 border font-mono text-[10px] font-black uppercase tracking-wider shadow-[1.5px_1.5px_0px_0px_#000] ${
      styles[status] || styles.pending
    }`}
  >
    <span
      className={`w-1.5 h-1.5 rounded-full bg-current ${
        ['processing', 'retrying'].includes(status) ? 'animate-ping' : ''
      }`}
    />
    [{status.toUpperCase()}]
  </span>
)
