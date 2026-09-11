import React from 'react'
import { Check, Ban, X, AlertTriangle, ArrowRight, Layers, Cpu, Clock } from 'lucide-react'
import { humanizeConcept } from '../../lib/searchApi'
import { useLanguage } from '../../context/LanguageContext'

export const QueryInterpretationStrip = ({
  query = '',
  result,
  onRemoveConcept,
  onRunQuery
}) => {
  const { t } = useLanguage()
  if (!result || (!result.interpretedQuery && !query && result.totalVideos === 0)) {
    return null
  }

  const interpreted = result.interpretedQuery || query
  const required = result.requiredConcepts || []
  const excluded = result.excludedConcepts || []
  const softTerms = result.unmatchedTerms || []

  // Check if we can suggest a negation pair
  const hasExclusion = excluded.length > 0 || /\b(without|no|except)\b/i.test(query)
  const pairedQuery = hasExclusion
    ? query.replace(/\s+(without|no|except)\s+[\w\s,]+$/i, '').trim()
    : `${query.trim()} without pedestrians`

  return (
    <div className="bg-white dark:bg-[#1A1815] border-2 border-black dark:border-[#2E2A25] p-4 shadow-[4px_4px_0px_0px_#000] dark:shadow-[4px_4px_0px_0px_#FF5500] font-mono text-xs space-y-3">
      {/* Line 1: Interpreted Query & Soft Terms */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[10px] font-black uppercase tracking-wider text-stone-500 dark:text-stone-400 min-w-[100px]">
          {t('strip.query')}
        </span>
        <span className="font-mono font-bold text-black dark:text-white text-sm">
          “{interpreted}”
        </span>
        {softTerms.length > 0 && (
          <span
            className="px-2 py-0.5 border border-dashed border-stone-400 dark:border-stone-600 text-stone-600 dark:text-stone-300 text-[10px] uppercase"
            title="Ranked on similarity, but not strictly filtered"
          >
            {t('strip.soft_only')} · {softTerms.map(humanizeConcept).join(', ')}
          </span>
        )}
      </div>

      {/* Line 2: Enforced Constraints */}
      <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-black/10 dark:border-white/10">
        <span className="text-[10px] font-black uppercase tracking-wider text-stone-500 dark:text-stone-400 min-w-[100px]">
          ENFORCED
        </span>
        {required.length === 0 && excluded.length === 0 ? (
          <span className="text-stone-400 text-[11px] italic">No strict concept constraints extracted</span>
        ) : (
          <>
            {required.map((concept) => (
              <span
                key={`req-${concept}`}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-[#00D084] text-black border border-black text-[10px] font-black uppercase shadow-[1.5px_1.5px_0px_0px_#000]"
              >
                <Check className="w-3 h-3 stroke-[3]" />
                <span>must have · {humanizeConcept(concept)}</span>
                {onRemoveConcept && (
                  <button
                    type="button"
                    onClick={() => onRemoveConcept('require', concept)}
                    className="ml-1 p-0.5 hover:bg-black hover:text-white transition-colors cursor-pointer"
                    title={`Remove requirement for ${concept}`}
                  >
                    <X className="w-2.5 h-2.5" />
                  </button>
                )}
              </span>
            ))}
            {excluded.map((concept) => (
              <span
                key={`exc-${concept}`}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-red-100 dark:bg-red-950/70 text-red-900 dark:text-red-300 border border-red-600 text-[10px] font-black uppercase shadow-[1.5px_1.5px_0px_0px_#000]"
              >
                <Ban className="w-3 h-3 stroke-[3]" />
                <span>must not have · {humanizeConcept(concept)}</span>
                {onRemoveConcept && (
                  <button
                    type="button"
                    onClick={() => onRemoveConcept('exclude', concept)}
                    className="ml-1 p-0.5 hover:bg-black hover:text-white transition-colors cursor-pointer"
                    title={`Remove exclusion for ${concept}`}
                  >
                    <X className="w-2.5 h-2.5" />
                  </button>
                )}
              </span>
            ))}
          </>
        )}
      </div>

      {/* Line 3: System Pipeline Stats & Pair Switcher */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-black/10 dark:border-white/10 text-[11px] text-stone-600 dark:text-stone-300">
        <div className="flex flex-wrap items-center gap-3">
          <span>
            <strong className="text-black dark:text-white font-bold">{result.totalVideos}</strong> videos
            {' · '}
            <strong className="text-black dark:text-white font-bold">{result.totalKeyframes}</strong> keyframes scanned
          </span>
          <span>•</span>
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3 text-[#FF5500]" />
            server <strong className="text-black dark:text-white font-bold">{Math.round(result.tookMs)} ms</strong>
          </span>
          <span>•</span>
          <span className="flex items-center gap-1">
            <Cpu className="w-3 h-3 text-[#00D084]" />
            index <strong className="text-black dark:text-white font-bold">{result.modelVersion || 'siglip-b16-224-v1'}</strong>
          </span>
          {result.signalsUsed?.length > 0 && (
            <>
              <span>•</span>
              <span className="flex items-center gap-1">
                <Layers className="w-3 h-3 text-[#FFD700]" />
                signals <strong className="text-black dark:text-white font-bold">{result.signalsUsed.join(', ')}</strong>
              </span>
            </>
          )}
        </div>

        {onRunQuery && pairedQuery && pairedQuery !== query && (
          <button
            type="button"
            onClick={() => onRunQuery(pairedQuery)}
            className="px-2.5 py-1 bg-white dark:bg-stone-800 hover:bg-black hover:text-white text-black dark:text-white border border-black shadow-[1.5px_1.5px_0px_0px_#000] text-[10px] font-bold uppercase transition-all flex items-center gap-1 cursor-pointer ml-auto"
          >
            <span>{hasExclusion ? 'Run without exclusion' : 'Add exclusion ("without pedestrians")'}</span>
            <ArrowRight className="w-3 h-3 text-[#FF5500]" />
          </button>
        )}
      </div>

      {/* Degraded Alert Line */}
      {result.degraded && (
        <div className="flex items-start gap-2.5 p-3 bg-amber-500/10 border-2 border-amber-500 text-amber-950 dark:text-amber-200 text-xs font-mono shadow-[2px_2px_0px_0px_#f59e0b]">
          <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
          <div className="leading-relaxed">
            <strong>DEGRADED MODE REPORTED (degraded: true):</strong> The retrieval engine is matching on{' '}
            <strong className="underline">{result.signalsUsed?.join(', ') || 'text captions'}</strong> instead of primary multimodal visual embeddings. Results remain useful via lexical/cross-modal search, and the engine explicitly reports this degraded state to maintain verification integrity.
          </div>
        </div>
      )}
    </div>
  )
}
