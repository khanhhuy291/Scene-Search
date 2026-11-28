import React from 'react'
import { Clock, Layers } from 'lucide-react'

export const QueryInterpretationStrip = ({ query = '', result }) => {
  if (!result) return null
  return (
    <div className="bg-white dark:bg-[#1A1815] border-2 border-black dark:border-[#2E2A25] p-4 font-mono text-xs space-y-3">
      <p className="font-bold text-black dark:text-white">“{result.interpretedQuery || query}”</p>
      <div className="flex flex-wrap items-center gap-3 text-stone-600 dark:text-stone-300">
        <span>{result.totalVideos} videos · {result.totalKeyframes} candidate moments</span>
        <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{Math.round(result.tookMs)} ms</span>
        <span className="flex items-center gap-1"><Layers className="w-3 h-3" />{result.signalsUsed?.join(' + ')}</span>
      </div>
    </div>
  )
}
