import React, { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Save, Trash2, Plus, Download, FolderKanban, Film } from 'lucide-react'
import { useDataset } from '../context/DatasetContext'
import { useToast } from '../context/ToastContext'

const BalanceChart = ({ items }) => {
  const rows = React.useMemo(() => {
    const map = {}
    for (const item of items) {
      const key = item.weather || 'unknown'
      map[key] = (map[key] || 0) + 1
    }
    return Object.entries(map).sort((a, b) => b[1] - a[1])
  }, [items])
  const max = Math.max(1, ...rows.map(([, n]) => n))

  if (rows.length === 0) {
    return (
      <p className="text-xs font-mono text-stone-500">
        [NO MOMENTS YET] // Mark relevant results from Search to populate balance breakdown.
      </p>
    )
  }

  return (
    <div className="space-y-2.5 font-mono">
      {rows.map(([label, count]) => (
        <div key={label} className="grid grid-cols-[6rem_1fr_2.5rem] gap-2 items-center text-xs">
          <span className="text-black dark:text-white font-bold truncate uppercase">{label}</span>
          <div className="h-3 bg-white dark:bg-stone-800 border border-black overflow-hidden">
            <div
              className="h-full bg-[#FF5500]"
              style={{ width: `${(count / max) * 100}%` }}
            />
          </div>
          <span className="tabular-nums font-black text-black dark:text-white text-right">{count}</span>
        </div>
      ))}
    </div>
  )
}

export const DatasetDraftPage = () => {
  const {
    activeDraft,
    removeItem,
    saveDataset,
    startNewDraft,
    ensureDraft,
    downloadBundle
  } = useDataset()
  const { addToast } = useToast()

  useEffect(() => {
    if (!activeDraft) {
      try {
        ensureDraft()
      } catch {
        // ProtectedRoute prevents non-engineers.
      }
    }
  }, [activeDraft, ensureDraft])

  const draft = activeDraft || {
    items: [],
    queryHistory: [],
    status: 'draft',
    id: 'pending'
  }

  const videoIds = draft.items.map((i) => i.videoId)
  const uniqueVideos = new Set(videoIds).size
  const hasDupVideos = videoIds.length > 0 && videoIds.length !== uniqueVideos

  const handleSave = () => {
    try {
      saveDataset()
      addToast('Dataset saved — available in Download', 'success')
    } catch (err) {
      addToast(err.message, 'error')
    }
  }

  const handleDownload = async () => {
    try {
      if (!activeDraft?.id) throw new Error('No draft to download')
      await downloadBundle(activeDraft.id)
      addToast('Downloaded keyframe manifest + videos', 'success')
    } catch (err) {
      addToast(err.message, 'error')
    }
  }

  const handleNew = () => {
    try {
      startNewDraft()
      addToast('Started a new empty draft', 'info')
    } catch (err) {
      addToast(err.message, 'error')
    }
  }

  return (
    <div className="max-w-[1700px] mx-auto px-4 sm:px-8 py-10 space-y-8 animate-fadeIn pb-32 font-sans">
      {/* Page Header */}
      <div className="border-b-2 border-black pb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="inline-flex items-center gap-2 px-2.5 py-0.5 bg-white dark:bg-stone-900 border border-black font-mono text-[10px] font-black uppercase text-black dark:text-white shadow-[1.5px_1.5px_0px_0px_#000]">
            <FolderKanban className="w-3 h-3 text-[#FF5500]" />
            <span>ENGINEER WORKSPACE // DATASET CURATOR</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-black text-black dark:text-white uppercase tracking-tight">
            DATASET DRAFT & KEYFRAME ANNOTATION
          </h1>
          <p className="text-xs font-mono text-stone-600 dark:text-stone-400">
            Collect moments across multiple semantic searches. Exports produce a JSONL manifest and zip bundle.
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center gap-2.5">
          <button
            type="button"
            onClick={handleNew}
            className="px-4 py-2 bg-white dark:bg-stone-900 hover:bg-black hover:text-white text-black dark:text-white font-mono text-xs font-black uppercase border-2 border-black shadow-[2px_2px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all flex items-center gap-1.5 cursor-pointer"
          >
            <Plus className="w-3.5 h-3.5" /> NEW DRAFT
          </button>

          <button
            type="button"
            onClick={handleSave}
            disabled={draft.items.length === 0}
            className="px-5 py-2 bg-black hover:bg-[#FF5500] text-white hover:text-black font-mono text-xs font-black uppercase border-2 border-black shadow-[3px_3px_0px_0px_#FF5500] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-40"
          >
            <Save className="w-3.5 h-3.5" /> SAVE DATASET
          </button>

          <button
            type="button"
            onClick={handleDownload}
            disabled={draft.items.length === 0}
            className="px-5 py-2 bg-[#00D084] hover:bg-black text-black hover:text-white font-mono text-xs font-black uppercase border-2 border-black shadow-[3px_3px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-40"
          >
            <Download className="w-3.5 h-3.5" /> DOWNLOAD BUNDLE
          </button>
        </div>
      </div>

      {/* Main Grid: Left Items + Right Telemetry */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Left: Draft Items List (cols 1-8) */}
        <div className="lg:col-span-8 space-y-6">
          <div className="flex items-center justify-between font-mono text-xs pb-2 border-b-2 border-black">
            <span className="font-black uppercase text-black dark:text-white">
              [CURATED KEYFRAMES ({draft.items.length})]
            </span>
            <span className="text-stone-500 font-bold uppercase">
              {uniqueVideos} UNIQUE VIDEO FILES
            </span>
          </div>

          {draft.items.length === 0 ? (
            <div className="p-10 bg-white dark:bg-[#1C1A17] border-2 border-black shadow-[4px_4px_0px_0px_#000] text-center space-y-3 font-mono">
              <Film className="w-8 h-8 text-[#FF5500] mx-auto" />
              <h3 className="text-sm font-black uppercase text-black dark:text-white">
                NO MOMENTS IN THIS DRAFT YET
              </h3>
              <p className="text-xs text-stone-600 dark:text-stone-400 font-sans max-w-md mx-auto">
                Search for scenes, then click "Add to Draft" or "Add All" on any result card to stage keyframe segments here.
              </p>
              <Link
                to="/search"
                className="inline-flex items-center gap-1.5 px-4 py-2 bg-black text-white hover:bg-[#FF5500] hover:text-black font-mono text-xs font-black uppercase border border-black transition-all shadow-[2px_2px_0px_0px_#000]"
              >
                GO TO SEARCH
              </Link>
            </div>
          ) : (
            <div className="space-y-3">
              {draft.items.map((item, index) => (
                <div
                  key={`${item.id || item.videoId}-${index}`}
                  className="bg-white dark:bg-[#1C1A17] border-2 border-black shadow-[3px_3px_0px_0px_#000] hover:shadow-[4px_4px_0px_0px_#FF5500] p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 transition-all"
                >
                  <div className="flex items-center gap-4 min-w-0">
                    <div className="w-16 h-12 bg-black border border-black shrink-0 overflow-hidden relative">
                      {item.thumbnailUrl ? (
                        <img
                          src={item.thumbnailUrl}
                          alt=""
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center font-mono text-[9px] text-white font-bold">
                          RAW
                        </div>
                      )}
                    </div>

                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-black text-black dark:text-white truncate">
                          {item.videoName || item.videoId}
                        </span>
                        <span className="px-1.5 py-0.2 bg-[#FFD700] text-black font-mono text-[9px] font-black uppercase border border-black">
                          {item.timestamp || `${Math.round(item.startSeconds || 0)}s`}
                        </span>
                      </div>
                      <p className="font-mono text-[11px] text-stone-500 truncate mt-0.5">
                        TAGS: {item.weather || 'GENERAL'} • Q: "{item.sourceQuery || 'DIRECT'}"
                      </p>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => removeItem(item.id || item.videoId)}
                    className="p-2 bg-red-100 hover:bg-red-600 text-red-900 hover:text-white border border-black font-mono text-xs transition-colors cursor-pointer shrink-0"
                    title="Remove from draft"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right: Balance Breakdown & Query Provenance (cols 9-12) */}
        <div className="lg:col-span-4 space-y-6">
          {/* Balance Breakdown Card */}
          <div className="bg-[#F7F4EE] dark:bg-[#1C1A17] border-2 border-black shadow-[4px_4px_0px_0px_#000] p-5 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b-2 border-black">
              <span className="font-mono text-xs font-black uppercase text-black dark:text-white">
                WEATHER & SCENE BALANCE
              </span>
              <span className="font-mono text-[10px] font-bold text-[#FF5500] uppercase">
                DISTRIBUTION
              </span>
            </div>

            <BalanceChart items={draft.items} />

            {hasDupVideos && (
              <div className="p-3 bg-amber-100 border border-black font-mono text-[11px] font-bold text-amber-950 flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-[#FF5500] shrink-0 mt-0.5" />
                <span>
                  Multiple keyframes from the same video file exist. Duplicate videos are deduplicated during zip export.
                </span>
              </div>
            )}
          </div>

          {/* Search Query Provenance */}
          <div className="bg-white dark:bg-[#1C1A17] border-2 border-black shadow-[4px_4px_0px_0px_#000] p-5 space-y-3 font-mono">
            <span className="block text-xs font-black uppercase text-black dark:text-white pb-2 border-b border-black">
              QUERY PROVENANCE HISTORY
            </span>

            {draft.queryHistory && draft.queryHistory.length > 0 ? (
              <div className="space-y-1.5">
                {draft.queryHistory.map((q, idx) => (
                  <div key={idx} className="p-2 bg-[#F7F4EE] dark:bg-stone-800 border border-black text-xs font-bold text-black dark:text-white truncate">
                    #{idx + 1}: "{q}"
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-stone-500">
                Queries contributing to this draft will appear here.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
