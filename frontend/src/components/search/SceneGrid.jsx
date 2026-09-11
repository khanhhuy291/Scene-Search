import React, { useMemo, useState, useEffect } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { Loader2, Plus, ChevronUp, ChevronDown, Send, Sparkles, RotateCcw, GripVertical } from "lucide-react"
import { SceneCard } from "./SceneCard"
import { QueryInterpretationStrip } from "./QueryInterpretationStrip"
import { explainEmptyResult } from "../../lib/searchApi"
import { useAuth } from "../../context/AuthContext"
import { useDataset } from "../../context/DatasetContext"
import { useToast } from "../../context/ToastContext"
import { useLanguage } from "../../context/LanguageContext"
import { submitRerankFeedback } from "../../api/feedback"

export const SceneGrid = ({
  scenes = [],
  query = "",
  result,
  searchMeta = null,
  isSearching = false,
  isLoadingMore = false,
  onLoadMore,
  onRemoveConcept,
  onRunQuery
}) => {
  const [sortBy, setSortBy] = useState("relevance")
  const { isEngineer } = useAuth()
  const { addItems, isSelected } = useDataset()
  const { addToast } = useToast()
  const { t } = useLanguage()

  // RLHF State
  const [isRlhfMode, setIsRlhfMode] = useState(false)
  const [reorderedScenes, setReorderedScenes] = useState([])
  const [rlhfNotes, setRlhfNotes] = useState("")
  const [isSubmittingRlhf, setIsSubmittingRlhf] = useState(false)

  // Drag & Drop State
  const [draggedIndex, setDraggedIndex] = useState(null)
  const [dragOverIndex, setDragOverIndex] = useState(null)

  // Initialize reorderedScenes whenever scenes change
  useEffect(() => {
    setReorderedScenes(scenes)
  }, [scenes])

  const handleDragStart = (e, index) => {
    setDraggedIndex(index)
    e.dataTransfer.effectAllowed = "move"
    e.dataTransfer.setData("text/plain", index.toString())
  }

  const handleDragOver = (e, index) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = "move"
    if (dragOverIndex !== index) {
      setDragOverIndex(index)
    }
  }

  const handleDragLeave = (e) => {
    e.preventDefault()
  }

  const handleDrop = (e, targetIndex) => {
    e.preventDefault()
    if (draggedIndex === null || draggedIndex === targetIndex) {
      setDraggedIndex(null)
      setDragOverIndex(null)
      return
    }
    const updated = [...reorderedScenes]
    const [draggedItem] = updated.splice(draggedIndex, 1)
    updated.splice(targetIndex, 0, draggedItem)
    setReorderedScenes(updated)
    setDraggedIndex(null)
    setDragOverIndex(null)
  }

  const handleDragEnd = () => {
    setDraggedIndex(null)
    setDragOverIndex(null)
  }

  const moveScene = (index, direction) => {
    const targetIndex = index + direction
    if (targetIndex < 0 || targetIndex >= reorderedScenes.length) return
    const updated = [...reorderedScenes]
    const [moved] = updated.splice(index, 1)
    updated.splice(targetIndex, 0, moved)
    setReorderedScenes(updated)
  }

  const handleResetRlhf = () => {
    setReorderedScenes(scenes)
    setRlhfNotes("")
    setDraggedIndex(null)
    setDragOverIndex(null)
  }

  const handleSubmitRlhf = async () => {
    if (!query.trim()) {
      addToast("Query is required for RLHF feedback", "error")
      return
    }
    setIsSubmittingRlhf(true)
    try {
      const originalRanking = scenes.map((s, idx) => ({
        scene_id: s.id,
        video_id: s.videoId || s.video_id,
        timestamp_s: s.startSeconds,
        score: s.similarity,
        rank: idx + 1,
        caption: s.caption
      }))

      const newRanking = reorderedScenes.map((s, idx) => ({
        scene_id: s.id,
        video_id: s.videoId || s.video_id,
        timestamp_s: s.startSeconds,
        rank: idx + 1,
        caption: s.caption
      }))

      await submitRerankFeedback({
        query: query.trim(),
        mode: searchMeta?.mode || "qwen",
        original_ranking: originalRanking,
        reordered_ranking: newRanking,
        notes: rlhfNotes.trim() || null
      })

      addToast("RLHF ranking feedback submitted successfully! Dataset updated for model fine-tuning.", "success")
      setIsRlhfMode(false)
    } catch (err) {
      addToast(err.message || "Failed to submit RLHF feedback", "error")
    } finally {
      setIsSubmittingRlhf(false)
    }
  }

  const sortedScenes = useMemo(() => {
    if (isRlhfMode) return reorderedScenes
    if (sortBy === "relevance") return scenes
    const copy = [...scenes]
    if (sortBy === "moments") copy.sort((a, b) => b.keyframesMatched - a.keyframesMatched)
    if (sortBy === "timestamp") copy.sort((a, b) => a.startSeconds - b.startSeconds)
    return copy
  }, [scenes, reorderedScenes, sortBy, isRlhfMode])

  const unselectedCount = useMemo(
    () => scenes.filter((scene) => !isSelected(scene.id)).length,
    [scenes, isSelected]
  )

  const handleAddAll = () => {
    try {
      const { added, skipped } = addItems(scenes, searchMeta || {})
      if (added === 0) {
        addToast(
          skipped > 0 ? "All visible results are already in your draft" : "Nothing to add",
          "info"
        )
      } else {
        addToast(
          `Added ${added} moment${added === 1 ? "" : "s"} to draft${skipped ? ` (${skipped} already in draft)` : ""}`,
          "success"
        )
      }
    } catch (err) {
      addToast(err.message, "error")
    }
  }

  if (isSearching && scenes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-20 font-mono text-black dark:text-white">
        <div className="w-10 h-10 border-3 border-black border-t-[#FF5500] rounded-full animate-spin" />
        <span className="text-xs font-black uppercase tracking-widest">
          {t("search.scanning", {}, "SCANNING QDRANT VECTOR SPACE...")}
        </span>
      </div>
    )
  }

  if (scenes.length === 0) {
    return (
      <div className="space-y-6">
        <QueryInterpretationStrip
          query={query}
          result={result}
          onRemoveConcept={onRemoveConcept}
          onRunQuery={onRunQuery}
        />
        <div className="text-center py-16 space-y-4 p-8 bg-white dark:bg-[#1A1815] border-2 border-black dark:border-[#2E2A25] shadow-[6px_6px_0px_0px_#000] font-mono">
          <p className="text-base font-black text-black dark:text-white uppercase">
            {result?.belowThreshold ? "[NO FOOTAGE MATCHING THRESHOLD IN CORPUS]" : "[ZERO RESULTS MATCHED]"}
          </p>
          <p className="text-xs font-sans text-stone-600 dark:text-stone-400 max-w-lg mx-auto leading-relaxed">
            {explainEmptyResult({
              query,
              belowThreshold: result?.belowThreshold,
              unconfirmedConcepts: result?.unconfirmedConcepts,
              excludedConcepts: result?.excludedConcepts
            })}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6 font-sans pb-16">
      {/* Rich Interpretation Strip */}
      <QueryInterpretationStrip
        query={query}
        result={result}
        onRemoveConcept={onRemoveConcept}
        onRunQuery={onRunQuery}
      />

      {/* Controls & Summary Header */}
      <div className="p-3.5 sm:p-4 bg-white dark:bg-[#1A1815] border-2 border-black dark:border-[#2E2A25] shadow-[4px_4px_0px_0px_#000] dark:shadow-[4px_4px_0px_0px_#FF5500]">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="font-mono text-xs">
            <span className="font-black uppercase text-black dark:text-white">
              RESULTS ({scenes.length} VIDEOS DISPLAYED)
            </span>
          </div>

          <div className="flex items-center gap-3 flex-wrap font-mono">
            {/* RLHF Re-rank Toggle */}
            <button
              type="button"
              onClick={() => {
                setIsRlhfMode(!isRlhfMode)
                if (!isRlhfMode) setReorderedScenes(scenes)
              }}
              className={`px-3 py-1.5 text-xs font-mono font-black uppercase tracking-wider border-2 border-black transition-all flex items-center gap-1.5 cursor-pointer ${
                isRlhfMode
                  ? "bg-[#FF5500] text-black shadow-none translate-x-0.5 translate-y-0.5"
                  : "bg-white dark:bg-stone-900 text-black dark:text-white hover:bg-stone-100 shadow-[2px_2px_0px_0px_#000]"
              }`}
            >
              <Sparkles className="w-3.5 h-3.5" />
              {isRlhfMode ? "EXIT RLHF MODE" : "RLHF RE-RANK"}
            </button>

            {isEngineer && scenes.length > 0 && !isRlhfMode && (
              <button
                type="button"
                onClick={handleAddAll}
                disabled={unselectedCount === 0}
                className="px-3 py-1.5 bg-black hover:bg-[#FF5500] text-white hover:text-black text-xs font-black uppercase tracking-wider border-2 border-black shadow-[2px_2px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-40"
              >
                <Plus className="w-3.5 h-3.5" />
                ADD ALL{unselectedCount > 0 ? ` (${unselectedCount})` : ""}
              </button>
            )}

            {!isRlhfMode && (
              <div className="flex items-center gap-2">
                <span className="text-xs font-black uppercase text-stone-500">SORT:</span>
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                  className="bg-[#F7F4EE] dark:bg-stone-800 border-2 border-black dark:border-stone-700 text-black dark:text-white text-xs font-mono font-black uppercase px-2.5 py-1 outline-none shadow-[1.5px_1.5px_0px_0px_#000]"
                >
                  <option value="relevance">RELEVANCE</option>
                  <option value="moments">MATCHING MOMENTS</option>
                  <option value="timestamp">TIMESTAMP</option>
                </select>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* RLHF Active Notice */}
      {isRlhfMode && (
        <div className="p-3.5 bg-amber-500/10 border-2 border-amber-500 text-amber-900 dark:text-amber-200 font-mono text-xs flex items-center justify-between gap-4 shadow-[3px_3px_0px_0px_#f59e0b]">
          <div className="flex items-center gap-2.5">
            <GripVertical className="w-5 h-5 text-amber-500 shrink-0" />
            <span>
              <strong>RLHF DRAG & DROP MODE:</strong> Drag and drop any result card to reposition and re-rank it based on visual inspection, or use ▲/▼ buttons.
            </span>
          </div>
        </div>
      )}

      {/* Grid Layout */}
      <motion.div layout className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
        <AnimatePresence>
          {sortedScenes.map((scene, idx) => {
            const origIndex = scenes.findIndex((s) => s.id === scene.id)
            const diff = origIndex >= 0 ? origIndex - idx : 0
            const isDragging = draggedIndex === idx
            const isDragOver = dragOverIndex === idx

            return (
              <div
                key={scene.id}
                draggable={isRlhfMode}
                onDragStart={(e) => handleDragStart(e, idx)}
                onDragOver={(e) => handleDragOver(e, idx)}
                onDragLeave={handleDragLeave}
                onDrop={(e) => handleDrop(e, idx)}
                onDragEnd={handleDragEnd}
                className={`relative transition-all duration-150 ${
                  isRlhfMode ? "cursor-grab active:cursor-grabbing select-none" : ""
                } ${
                  isDragging
                    ? "opacity-40 scale-95 border-2 border-dashed border-[#FF5500]"
                    : ""
                } ${
                  isDragOver && !isDragging
                    ? "ring-4 ring-[#FF5500] scale-[1.02] shadow-[8px_8px_0px_0px_#FF5500]"
                    : ""
                }`}
              >
                {isRlhfMode && (
                  <div className="mb-2 p-2 bg-black text-white border-2 border-black flex items-center justify-between font-mono text-xs shadow-[2px_2px_0px_0px_#FF5500]">
                    <div className="flex items-center gap-2">
                      <div className="flex items-center gap-1 bg-stone-900 px-1.5 py-0.5 border border-stone-700 text-[#FF5500]">
                        <GripVertical className="w-3.5 h-3.5" />
                        <span className="text-[10px] font-black tracking-wider">DRAG</span>
                      </div>
                      <span className="px-2 py-0.5 bg-[#FF5500] text-black font-black font-mono">
                        RANK #{idx + 1}
                      </span>
                      {diff !== 0 && (
                        <span className={`font-bold text-[10px] ${diff > 0 ? "text-[#00D084]" : "text-rose-400"}`}>
                          (Orig #{origIndex + 1} {diff > 0 ? `▲${diff}` : `▼${Math.abs(diff)}`})
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        disabled={idx === 0}
                        onClick={(e) => {
                          e.stopPropagation()
                          moveScene(idx, -1)
                        }}
                        className="p-1 bg-stone-800 hover:bg-[#FF5500] hover:text-black disabled:opacity-30 border border-stone-700 transition cursor-pointer"
                        title="Move Up"
                      >
                        <ChevronUp className="w-3.5 h-3.5 stroke-[3]" />
                      </button>
                      <button
                        type="button"
                        disabled={idx === reorderedScenes.length - 1}
                        onClick={(e) => {
                          e.stopPropagation()
                          moveScene(idx, 1)
                        }}
                        className="p-1 bg-stone-800 hover:bg-[#FF5500] hover:text-black disabled:opacity-30 border border-stone-700 transition cursor-pointer"
                        title="Move Down"
                      >
                        <ChevronDown className="w-3.5 h-3.5 stroke-[3]" />
                      </button>
                    </div>
                  </div>
                )}
                <SceneCard scene={scene} searchMeta={searchMeta} />
              </div>
            )
          })}
        </AnimatePresence>
      </motion.div>

      {/* Load More Pagination */}
      {!isRlhfMode && result.nextCursor && (
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

      {/* Floating Sticky RLHF Submission Bar */}
      {isRlhfMode && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 w-full max-w-2xl px-4 animate-slideUp">
          <div className="bg-black text-white border-3 border-black p-4 shadow-[6px_6px_0px_0px_#FF5500] flex flex-col sm:flex-row items-center justify-between gap-3 font-mono">
            <div className="flex-1 w-full">
              <input
                type="text"
                placeholder="RLHF annotation notes (optional)..."
                value={rlhfNotes}
                onChange={(e) => setRlhfNotes(e.target.value)}
                className="w-full px-3 py-1.5 bg-stone-900 border border-stone-700 text-xs text-white placeholder-stone-500 outline-none focus:border-[#FF5500]"
              />
            </div>

            <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
              <button
                type="button"
                onClick={handleResetRlhf}
                className="px-3 py-2 bg-stone-800 hover:bg-stone-700 text-white text-xs font-black uppercase flex items-center gap-1 cursor-pointer"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                RESET
              </button>

              <button
                type="button"
                disabled={isSubmittingRlhf}
                onClick={handleSubmitRlhf}
                className="px-4 py-2 bg-[#FF5500] hover:bg-[#ff6a20] text-black text-xs font-black uppercase flex items-center gap-1.5 shadow-[2px_2px_0px_0px_#fff] cursor-pointer disabled:opacity-50"
              >
                {isSubmittingRlhf ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Send className="w-3.5 h-3.5" />
                )}
                SUBMIT RLHF
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
