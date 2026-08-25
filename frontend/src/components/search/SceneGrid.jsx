import React, { useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, Check, Ban, Loader2, Plus } from 'lucide-react'
import { SceneCard } from './SceneCard'
import { explainEmptyResult, humanizeConcept } from '../../lib/searchApi'
import { useAuth } from '../../context/AuthContext'
import { useDataset } from '../../context/DatasetContext'
import { useToast } from '../../context/ToastContext'

const ConceptChip = ({ concept, kind, onRemove }) => {
  const isExclusion = kind === 'exclude'
  const Icon = isExclusion ? Ban : Check

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-[10px] font-mono font-black uppercase tracking-wider border-2 ${
        isExclusion
          ? 'bg-red-100 dark:bg-red-950/60 text-red-900 dark:text-red-300 border-red-600'
          : 'bg-[#00D084] text-black border-black shadow-[1.5px_1.5px_0px_0px_#000]'
      }`}
    >
      <Icon className="w-3 h-3 stroke-[3]" />
      {isExclusion ? 'NO ' : ''}
      {humanizeConcept(concept)}
      <button
        type="button"
        onClick={() => onRemove(kind, concept)}
        title={`Remove the "${humanizeConcept(concept)}" constraint`}
        className="ml-1 p-0.5 hover:bg-black hover:text-white transition-colors cursor-pointer"
      >
        <X className="w-3 h-3" />
      </button>
    </span>
  )
}

export const SceneGrid = ({
  scenes = [],
  query = '',
  result,
  searchMeta = null,
  isSearching = false,
  isLoadingMore = false,
  onLoadMore,
  onRemoveConcept
}) => {
  const [sortBy, setSortBy] = useState('relevance')
  const { isEngineer } = useAuth()
  const { addItems, isSelected } = useDataset()
  const { addToast } = useToast()

  const sortedScenes = useMemo(() => {
    if (sortBy === 'relevance') return scenes
    const copy = [...scenes]
    if (sortBy === 'moments') copy.sort((a, b) => b.keyframesMatched - a.keyframesMatched)
    if (sortBy === 'timestamp') copy.sort((a, b) => a.startSeconds - b.startSeconds)
    return copy
  }, [scenes, sortBy])

  const unselectedCount = useMemo(
    () => scenes.filter((scene) => !isSelected(scene.id)).length,
    [scenes, isSelected]
  )

  const handleAddAll = () => {
    try {
      const { added, skipped } = addItems(scenes, searchMeta || {})
      if (added === 0) {
        addToast(
          skipped > 0 ? 'All visible results are already in your draft' : 'Nothing to add',
          'info'
        )
      } else {
        addToast(
          `Added ${added} moment${added === 1 ? '' : 's'} to draft${skipped ? ` (${skipped} already in draft)` : ''}`,
          'success'
        )
      }
    } catch (err) {
      addToast(err.message, 'error')
    }
  }

  const hasConstraints =
    (result?.requiredConcepts?.length ?? 0) > 0 || (result?.excludedConcepts?.length ?? 0) > 0

  if (isSearching && scenes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-20 font-mono text-black dark:text-white">
        <div className="w-10 h-10 border-3 border-black border-t-[#FF5500] animate-spin" />
        <span className="text-xs font-black uppercase tracking-widest">
          SCANNING QDRANT VECTOR SPACE...
        </span>
      </div>
    )
  }

  if (scenes.length === 0) {
    return (
      <div className="text-center py-16 space-y-4 p-8 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] font-mono">
        <p className="text-base font-black text-black dark:text-white uppercase">
          {result?.belowThreshold ? '[NO FOOTAGE MATCHING THRESHOLD IN CORPUS]' : '[ZERO RESULTS MATCHED]'}
        </p>
        <p className="text-xs font-sans text-stone-600 dark:text-stone-400 max-w-lg mx-auto leading-relaxed">
          {explainEmptyResult({
            query,
            belowThreshold: result?.belowThreshold,
            unconfirmedConcepts: result?.unconfirmedConcepts,
            excludedConcepts: result?.excludedConcepts
          })}
        </p>
        {hasConstraints && (
          <div className="flex items-center gap-2 flex-wrap justify-center pt-2">
            {result.requiredConcepts.map((concept) => (
              <ConceptChip
                key={`require-${concept}`}
                concept={concept}
                kind="require"
                onRemove={onRemoveConcept}
              />
            ))}
            {result.excludedConcepts.map((concept) => (
              <ConceptChip
                key={`exclude-${concept}`}
                concept={concept}
                kind="exclude"
                onRemove={onRemoveConcept}
              />
            ))}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-6 font-sans">
      {/* Degraded / Threshold Notices */}
      {(result.degraded || result.belowThreshold || (result.unmatchedTerms?.length ?? 0) > 0) && (
        <div className="flex flex-wrap gap-2 font-mono text-[10px] font-black uppercase">
          {result.degraded && (
            <span className="px-2.5 py-1 bg-amber-100 border border-black text-amber-950 shadow-[1.5px_1.5px_0px_0px_#000]">
              DEGRADED · SIGLIP ONLY
            </span>
          )}
          {result.belowThreshold && (
            <span className="px-2.5 py-1 bg-stone-200 border border-black text-stone-900 shadow-[1.5px_1.5px_0px_0px_#000]">
              BELOW SIMILARITY THRESHOLD
            </span>
          )}
          {result.unmatchedTerms?.length > 0 && (
            <span className="px-2.5 py-1 bg-stone-200 border border-black text-stone-900 shadow-[1.5px_1.5px_0px_0px_#000]">
              UNRECOGNIZED: {result.unmatchedTerms.join(', ')}
            </span>
          )}
        </div>
      )}

      {/* Controls / Summary Header Bar */}
      <div className="p-4 sm:p-5 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] space-y-4">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="space-y-0.5 font-mono">
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 bg-[#FF5500] text-black text-[10px] font-black uppercase border border-black shadow-[1px_1px_0px_0px_#000]">
                {result.exhaustive ? 'EXHAUSTIVE' : 'TOP-K'}
              </span>
              <span className="text-xs font-black uppercase text-black dark:text-white">
                FOUND {result.totalVideos} MATCHING VIDEOS
                {query && <span className="text-[#FF5500] ml-1">"{query}"</span>}
              </span>
            </div>
            <p className="text-[11px] text-stone-500 font-bold">
              {result.totalKeyframes} KEYFRAMES • 1 PER VIDEO • LATENCY: {Math.round(result.tookMs)}ms
            </p>
          </div>

          <div className="flex items-center gap-3 flex-wrap font-mono">
            {isEngineer && scenes.length > 0 && (
              <button
                type="button"
                onClick={handleAddAll}
                disabled={unselectedCount === 0}
                className="px-4 py-2 bg-black hover:bg-[#FF5500] text-white hover:text-black text-xs font-black uppercase tracking-wider border-2 border-black shadow-[2px_2px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-40"
              >
                <Plus className="w-3.5 h-3.5" />
                ADD ALL{unselectedCount > 0 ? ` (${unselectedCount})` : ''}
              </button>
            )}

            <div className="flex items-center gap-2">
              <span className="text-xs font-black uppercase text-stone-500">SORT:</span>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
                className="bg-[#F7F4EE] dark:bg-stone-800 border-2 border-black text-black dark:text-white text-xs font-mono font-black uppercase px-3 py-1.5 outline-none shadow-[2px_2px_0px_0px_#000]"
              >
                <option value="relevance">RELEVANCE</option>
                <option value="moments">MATCHING MOMENTS</option>
                <option value="timestamp">TIMESTAMP</option>
              </select>
            </div>
          </div>
        </div>

        {/* Concept Constraints Filters */}
        {hasConstraints && (
          <div className="flex items-center gap-2 flex-wrap pt-3 border-t-2 border-black/20 font-mono">
            <span className="text-[10px] font-black uppercase tracking-wider text-stone-500 shrink-0">
              INFERRED CONSTRAINTS:
            </span>
            {result.requiredConcepts.map((concept) => (
              <ConceptChip
                key={`require-${concept}`}
                concept={concept}
                kind="require"
                onRemove={onRemoveConcept}
              />
            ))}
            {result.excludedConcepts.map((concept) => (
              <ConceptChip
                key={`exclude-${concept}`}
                concept={concept}
                kind="exclude"
                onRemove={onRemoveConcept}
              />
            ))}
          </div>
        )}
      </div>

      {/* Grid Layout */}
      <motion.div layout className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <AnimatePresence>
          {sortedScenes.map((scene) => (
            <SceneCard key={scene.id} scene={scene} searchMeta={searchMeta} />
          ))}
        </AnimatePresence>
      </motion.div>

      {/* Load More Pagination */}
      {result.nextCursor && (
        <div className="flex flex-col items-center gap-2 pt-6 font-mono">
          <button
            type="button"
            onClick={onLoadMore}
            disabled={isLoadingMore}
            className="px-8 py-3 bg-black hover:bg-[#FF5500] text-white hover:text-black font-black text-xs uppercase tracking-widest border-2 border-black shadow-[4px_4px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all flex items-center gap-2 cursor-pointer disabled:opacity-50"
          >
            {isLoadingMore ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" /> LOADING...
              </>
            ) : (
              <>LOAD MORE MATCHING VIDEOS ↵</>
            )}
          </button>
          <span className="text-[11px] text-stone-500 font-bold">
            SHOWING {scenes.length} OF {result.totalVideos} MATCHING VIDEOS
          </span>
        </div>
      )}
    </div>
  )
}
