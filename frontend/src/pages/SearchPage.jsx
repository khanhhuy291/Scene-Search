import React, { useCallback, useEffect, useRef, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { SearchBar } from "../components/search/SearchBar"
import { SceneGrid } from "../components/search/SceneGrid"
import { SelectionTray } from "../components/search/SelectionTray"
import { DraftRail } from "../components/search/DraftRail"
import { useToast } from "../context/ToastContext"
import { useDataset } from "../context/DatasetContext"
import { useLanguage } from "../context/LanguageContext"
import { searchScenes } from "../lib/searchApi"
import { Terminal, Database, Layers, Sparkles, ChevronDown, ChevronUp } from "lucide-react"

const EMPTY_RESULT = {
  scenes: [],
  totalVideos: 0,
  totalKeyframes: 0,
  interpretedQuery: "",
  requiredConcepts: [],
  excludedConcepts: [],
  unmatchedTerms: [],
  exhaustive: false,
  signalsUsed: [],
  belowThreshold: false,
  unconfirmedConcepts: [],
  nextCursor: null,
  tookMs: 0,
  modelVersion: "",
  degraded: false,
  source: "api"
}

export const SearchPage = () => {
  const { addToast } = useToast()
  const { activeDraft, removeItem, downloadManifest } = useDataset()
  const { t } = useLanguage()
  const [searchParams, setSearchParams] = useSearchParams()
  const urlQuery = searchParams.get("q") || ""
  const [currentQuery, setCurrentQuery] = useState(urlQuery)
  const [result, setResult] = useState(EMPTY_RESULT)
  const [isSearching, setIsSearching] = useState(false)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [error, setError] = useState(null)
  const [hasSearched, setHasSearched] = useState(false)
  const [heroExpanded, setHeroExpanded] = useState(false)
  const [searchOptions, setSearchOptions] = useState({ mode: "hybrid", limit: 24 })
  const [overrides, setOverrides] = useState({ require: null, exclude: null })

  const activeRequest = useRef(null)

  useEffect(() => () => activeRequest.current?.abort(), [])

  const runSearch = useCallback(
    async (queryText, options = {}) => {
      const trimmed = queryText.trim()
      if (!trimmed) return

      activeRequest.current?.abort()
      const controller = new AbortController()
      activeRequest.current = controller

      const mode = options.mode ?? searchOptions.mode
      const limit = options.limit ?? searchOptions.limit
      setSearchOptions({ mode, limit })

      setIsSearching(true)
      setError(null)
      setCurrentQuery(trimmed)
      setHasSearched(true)
      setHeroExpanded(false)

      try {
        const next = await searchScenes({
          query: trimmed,
          mode,
          limit,
          require: options.require ?? null,
          exclude: options.exclude ?? null,
          signal: controller.signal
        })
        setResult(next)
        setHasSearched(true)

        if (next.totalVideos === 0) {
          addToast(
            next.belowThreshold
              ? `Nothing in this corpus resembles "${trimmed}"`
              : `No scenes matched "${trimmed}"`,
            "info"
          )
        } else {
          const scope = next.exhaustive
            ? `all ${next.totalVideos} matching videos`
            : `${next.totalVideos} matching videos`
          addToast(`Found ${scope} (${next.totalKeyframes} keyframes)`, "success")
        }
        if (next.unmatchedTerms.length > 0) {
          addToast(
            `Could not enforce: ${next.unmatchedTerms.join(", ")}. Handled by similarity only.`,
            "info"
          )
        }
      } catch (caught) {
        if (caught.name === "AbortError") return
        setError(caught.message)
        setResult(EMPTY_RESULT)
        setHasSearched(true)
        addToast(caught.message, "error")
      } finally {
        if (activeRequest.current === controller) {
          activeRequest.current = null
          setIsSearching(false)
        }
      }
    },
    [addToast, searchOptions.limit, searchOptions.mode]
  )

  useEffect(() => {
    if (urlQuery && urlQuery !== currentQuery) {
      setCurrentQuery(urlQuery)
      runSearch(urlQuery)
    } else if (urlQuery && !hasSearched) {
      runSearch(urlQuery)
    }
  }, [urlQuery, currentQuery, hasSearched, runSearch])

  const handleSearch = (queryText, options = {}) => {
    const trimmed = queryText.trim()
    setOverrides({ require: null, exclude: null })
    if (trimmed) {
      setSearchParams({ q: trimmed })
    }
    runSearch(trimmed, options)
  }

  const handleOptionsChange = (options) => {
    setSearchOptions((prev) => ({ ...prev, ...options }))
    if (!hasSearched || !currentQuery) return
    runSearch(currentQuery, {
      ...options,
      require: overrides.require,
      exclude: overrides.exclude
    })
  }

  const handleLoadMore = async () => {
    if (!result.nextCursor || isLoadingMore) return
    setIsLoadingMore(true)
    try {
      const next = await searchScenes({
        query: currentQuery,
        cursor: result.nextCursor,
        mode: searchOptions.mode,
        limit: searchOptions.limit,
        require: overrides.require ?? undefined,
        exclude: overrides.exclude ?? undefined
      })
      setResult((previous) => ({
        ...next,
        scenes: [...previous.scenes, ...next.scenes]
      }))
    } catch (caught) {
      addToast(caught.message, "error")
    } finally {
      setIsLoadingMore(false)
    }
  }

  const handleRemoveConcept = (kind, concept) => {
    const nextRequire = (overrides.require ?? result.requiredConcepts).filter(
      (item) => kind !== "require" || item !== concept
    )
    const nextExclude = (overrides.exclude ?? result.excludedConcepts).filter(
      (item) => kind !== "exclude" || item !== concept
    )
    setOverrides({ require: nextRequire, exclude: nextExclude })
    runSearch(currentQuery, {
      require: nextRequire,
      exclude: nextExclude,
      mode: searchOptions.mode,
      limit: searchOptions.limit
    })
  }

  const handleExportDraft = () => {
    const items = activeDraft?.items || []
    if (!items.length) {
      addToast("Draft is empty", "info")
      return
    }
    try {
      if (activeDraft?.id) {
        downloadManifest(activeDraft.id)
        addToast(`Exported ${items.length} moments as JSONL`, "success")
      } else {
        const lines = items.map((item) =>
          JSON.stringify({
            video_id: item.videoId,
            keyframe_id: item.id,
            frame_no: item.frameNo,
            ts_start_s: item.startSeconds,
            ts_end_s: item.endSeconds,
            caption: item.description,
            weather: item.weather,
            time_of_day: item.timeOfDay,
            scene_type: item.sceneType,
            source_query: currentQuery,
            corpus: "bdd100k-20gb-subset"
          })
        )
        const blob = new Blob([lines.join("\n") + "\n"], { type: "application/x-ndjson" })
        const url = URL.createObjectURL(blob)
        const a = document.createElement("a")
        a.href = url
        a.download = `scenesearch-slice-${items.length}.jsonl`
        document.body.appendChild(a)
        a.click()
        a.remove()
        URL.revokeObjectURL(url)
        addToast(`Exported ${items.length} moments`, "success")
      }
    } catch (err) {
      addToast(err.message, "error")
    }
  }

  // Keyboard shortcut listener (/ to focus search)
  useEffect(() => {
    const handleKey = (e) => {
      const isInput = /^(INPUT|TEXTAREA)$/.test(document.activeElement?.tagName)
      if (e.key === "/" && !isInput) {
        e.preventDefault()
        const input = document.getElementById("search-input")
        if (input) {
          input.focus()
          input.select()
        }
      }
    }
    window.addEventListener("keydown", handleKey)
    return () => window.removeEventListener("keydown", handleKey)
  }, [])

  const searchMeta = {
    query: currentQuery,
    requiredConcepts: result.requiredConcepts,
    excludedConcepts: result.excludedConcepts,
    modelVersion: result.modelVersion
  }

  const draftItems = activeDraft?.items || []

  return (
    <div className="max-w-[1700px] mx-auto px-4 sm:px-8 py-6 space-y-6 font-sans pb-36">
      {/* State 1: Initial Landing View before any search (100% Centered Single-Column Layout) */}
      {!hasSearched && !isSearching && draftItems.length === 0 ? (
        <div className="space-y-8 max-w-4xl mx-auto pt-4 animate-fadeIn">
          {/* Top Banner / Hero Area */}
          <div className="text-center space-y-4">
            <div className="inline-flex items-center gap-2 px-3.5 py-1 bg-white dark:bg-[#1A1815] border-2 border-black dark:border-[#2E2A25] font-mono text-[11px] font-black uppercase tracking-wider shadow-[2px_2px_0px_0px_#000]">
              <Terminal className="w-3.5 h-3.5 text-[#FF5500]" />
              <span>MULTIMODAL NEURAL SEARCH // QDRANT HNSW + QWEN3-VL & SIGLIP</span>
            </div>

            <h1 className="text-3xl sm:text-5xl font-black tracking-tight text-black dark:text-white uppercase leading-none">
              SEMANTIC SCENE <span className="text-[#FF5500]">SEARCH</span>
            </h1>

            <p className="text-stone-600 dark:text-stone-400 text-sm max-w-xl mx-auto font-medium">
              Natural-language retrieval across driving footage. Query visual conditions, actions, and strict negations to curate balanced training slices.
            </p>

            <div className="flex flex-wrap items-center justify-center gap-3 pt-1 font-mono text-[11px] font-bold">
              <span className="px-2.5 py-1 bg-[#F7F4EE] dark:bg-stone-800 border border-black text-black dark:text-white flex items-center gap-1.5">
                <Database className="w-3 h-3 text-[#FF5500]" /> ~30,000 VECTORS
              </span>
              <span className="px-2.5 py-1 bg-[#F7F4EE] dark:bg-stone-800 border border-black text-black dark:text-white flex items-center gap-1.5">
                <Layers className="w-3 h-3 text-[#00D084]" /> ZERO-SHOT MULTIMODAL
              </span>
              <span className="px-2.5 py-1 bg-[#F7F4EE] dark:bg-stone-800 border border-black text-black dark:text-white flex items-center gap-1.5">
                <Sparkles className="w-3 h-3 text-[#FFD700]" /> TEMPORAL KEYFRAMES
              </span>
            </div>
          </div>

          {/* Centered Search Bar with quick chips */}
          <SearchBar
            initialQuery={currentQuery}
            onSearch={handleSearch}
            onOptionsChange={handleOptionsChange}
            isSearching={isSearching}
            compact={false}
          />

          {/* Initial State Box */}
          <div className="text-center space-y-3 max-w-xl mx-auto p-8 bg-white dark:bg-[#1A1815] border-2 border-black dark:border-[#2E2A25] shadow-[4px_4px_0px_0px_#000] font-mono">
            <p className="text-sm font-bold text-black dark:text-white uppercase">
              {t("search.system_ready", {}, "[SYSTEM READY // AWAITING QUERY]")}
            </p>
            <p className="text-xs text-stone-600 dark:text-stone-400 font-sans leading-relaxed">
              {t("search.system_ready_desc", {}, "Enter a scene description above or click one of the suggested query chips to start neural search across ~30,000 keyframes.")}
            </p>
          </div>
        </div>
      ) : (
        /* State 2: Active Workspace (2-Column Grid with Left Search Stream & Right Draft Rail) */
        <div className="space-y-4 animate-fadeIn">
          {/* Collapsible Overview Header */}
          {heroExpanded ? (
            <div className="text-center space-y-4 max-w-4xl mx-auto pt-2 pb-4 border-b border-black/10 dark:border-white/10">
              <h1 className="text-2xl sm:text-4xl font-black tracking-tight text-black dark:text-white uppercase leading-none">
                SEMANTIC SCENE <span className="text-[#FF5500]">SEARCH</span>
              </h1>
              <p className="text-stone-600 dark:text-stone-400 text-xs max-w-xl mx-auto font-medium">
                Natural-language retrieval across driving footage. Query visual conditions, actions, and strict negations to curate balanced training slices.
              </p>
              <button
                type="button"
                onClick={() => setHeroExpanded(false)}
                className="font-mono text-[11px] text-stone-500 hover:text-black dark:hover:text-white underline cursor-pointer inline-flex items-center gap-1"
              >
                <ChevronUp className="w-3.5 h-3.5" /> {t("search.collapse_header", {}, "Collapse header")}
              </button>
            </div>
          ) : (
            <div className="flex items-center justify-between pb-2 border-b border-black/10 dark:border-white/10 font-mono text-xs">
              <div className="flex items-center gap-2">
                <span className="font-black uppercase text-black dark:text-white">
                  {t("search.workspace", {}, "WORKSPACE")}
                </span>
                <span className="text-stone-400">•</span>
                <span className="text-stone-500 truncate max-w-md">
                  “{currentQuery}”
                </span>
              </div>
              <button
                type="button"
                onClick={() => setHeroExpanded(true)}
                className="text-[11px] text-stone-500 hover:text-black dark:hover:text-white flex items-center gap-1 cursor-pointer"
              >
                <ChevronDown className="w-3 h-3" /> {t("search.show_overview", {}, "Show overview")}
              </button>
            </div>
          )}

          {/* Main 2-Column Grid: Search Stream (Left) + Draft Rail (Right) */}
          <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_340px] gap-8 items-start">
            {/* Left Column: Sticky Compact SearchBar + Error + Results Grid */}
            <main className="min-w-0 space-y-4">
              <div className="sticky top-16 z-30 pt-1 pb-2 bg-[#F7F4EE]/95 dark:bg-[#12110F]/95 backdrop-blur-md">
                <SearchBar
                  initialQuery={currentQuery}
                  onSearch={handleSearch}
                  onOptionsChange={handleOptionsChange}
                  isSearching={isSearching}
                  compact={true}
                />
              </div>

              {error && (
                <div className="p-5 bg-red-100 dark:bg-red-950/50 border-2 border-red-600 text-center space-y-1 font-mono shadow-[4px_4px_0px_0px_#000]">
                  <p className="text-sm font-black uppercase text-red-900 dark:text-red-300">
                    SEARCH UNAVAILABLE // API ERROR
                  </p>
                  <p className="text-xs text-red-700 dark:text-red-400">{error}</p>
                </div>
              )}

              {!error && (
                <SceneGrid
                  scenes={result.scenes}
                  query={currentQuery}
                  result={result}
                  searchMeta={searchMeta}
                  isSearching={isSearching}
                  isLoadingMore={isLoadingMore}
                  onLoadMore={handleLoadMore}
                  onRemoveConcept={handleRemoveConcept}
                  onRunQuery={(q) => handleSearch(q)}
                />
              )}
            </main>

            {/* Permanent Draft Rail (Right Column) */}
            <DraftRail
              items={draftItems}
              onRemoveItem={(id) => removeItem(id)}
              onExportJsonl={handleExportDraft}
              className="hidden xl:block sticky top-20"
            />
          </div>
        </div>
      )}

      {/* Floating Tray for Mobile / Tablet screens (< xl) */}
      <div className="xl:hidden">
        <SelectionTray />
      </div>
    </div>
  )
}
