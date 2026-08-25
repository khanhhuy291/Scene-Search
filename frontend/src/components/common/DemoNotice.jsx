import { FlaskConical } from 'lucide-react'

export function DemoNotice() {
  return (
    <div
      role="status"
      className="flex items-center justify-center gap-2 bg-[#FFD700] text-black border-b-2 border-black px-4 py-1.5 text-center font-mono text-[11px] font-black uppercase tracking-wider"
    >
      <FlaskConical aria-hidden="true" className="h-3.5 w-3.5 shrink-0 stroke-[2.5]" />
      <span>
        [DEMO ENV] Dataset drafts stay in this browser; downloads pull clips from live media API. Auth is JWT. Search hits live index.
      </span>
    </div>
  )
}
