import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { SearchBar } from '../components/search/SearchBar'
import { SceneGrid } from '../components/search/SceneGrid'
import { SelectionTray } from '../components/search/SelectionTray'
import { useToast } from '../context/ToastContext'
import { searchScenes } from '../lib/searchApi'
import { Terminal, Database, Layers, Sparkles } from 'lucide-react'

const EMPTY_RESULT = {
  scenes: [],
  totalVideos: 0,
  totalKeyframes: 0,
  interpretedQuery: '',
  requiredConcepts: [],
  excludedConcepts: [],
  unmatchedTerms: [],
  exhaustive: false,
  signalsUsed: [],
  belowThreshold: false,
  unconfirmedConcepts: [],
  nextCursor: null,
  tookMs: 0,
  modelVersion: '',
  degraded: false,
  source: 'api'
}

export const SearchPage = () => {
  const { addToast } = useToast()
  const [searchParams, setSearchParams] = useSearchParams()
  const urlQuery = searchParams.get('q') || ''
  const [currentQuery, setCurrentQuery] = useState(urlQuery)
  const [result, setResult] = useState(EMPTY_RESULT)
  const [isSearching, setIsSearching] = useState(false)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [error, setError] = useState(null)
  const [hasSearched, setHasSearched] = useState(false)
  const [searchOptions, setSearchOptions] = useState({ mode: 'hybrid', limit: 24 })

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
            'info'
          )
        } else {
          const scope = next.exhaustive
            ? `all ${next.totalVideos} matching videos`
            : `${next.totalVideos} matching videos`
          addToast(`Found ${scope} (${next.totalKeyframes} keyframes)`, 'success')
        }
        if (next.unmatchedTerms.length > 0) {
          addToast(
            `Could not enforce: ${next.unmatchedTerms.join(', ')}. Handled by similarity only.`,
            'info'
          )
        }
      } catch (caught) {
        if (caught.name === 'AbortError') return
        setError(caught.message)
        setResult(EMPTY_RESULT)
        setHasSearched(true)
        addToast(caught.message, 'error')
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
  }, [urlQuery, runSearch])

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
      addToast(caught.message, 'error')
    } finally {
      setIsLoadingMore(false)
    }
  }

  const handleRemoveConcept = (kind, concept) => {
    const nextRequire = (overrides.require ?? result.requiredConcepts).filter(
      (item) => kind !== 'require' || item !== concept
    )
    const nextExclude = (overrides.exclude ?? result.excludedConcepts).filter(
      (item) => kind !== 'exclude' || item !== concept
    )
    setOverrides({ require: nextRequire, exclude: nextExclude })
    runSearch(currentQuery, {
      require: nextRequire,
      exclude: nextExclude,
      mode: searchOptions.mode,
      limit: searchOptions.limit
    })
  }

  const searchMeta = {
    query: currentQuery,
    requiredConcepts: result.requiredConcepts,
    excludedConcepts: result.excludedConcepts,
    modelVersion: result.modelVersion
  }

  return (
    <div className="max-w-[1700px] mx-auto px-4 sm:px-8 py-10 space-y-12 animate-fadeIn pb-36 font-sans">
      {/* Top Banner / Hero Area */}
      <div className="text-center space-y-4 max-w-4xl mx-auto pt-4">
        <div className="inline-flex items-center gap-2 px-3.5 py-1 bg-white dark:bg-stone-900 border-2 border-black font-mono text-[11px] font-black uppercase tracking-wider shadow-[2px_2px_0px_0px_#000]">
          <Terminal className="w-3.5 h-3.5 text-[#FF5500]" />
          <span>NEURAL VECTOR SEARCH // QDRANT HNSW + ViT CLIP</span>
        </div>

        <h1 className="text-4xl sm:text-6xl font-black tracking-tight text-black dark:text-white uppercase leading-none">
          SEARCH <span className="text-[#FF5500]">MULTIMODAL</span> SCENES
        </h1>

        <p className="text-stone-700 dark:text-stone-300 text-sm font-sans max-w-xl mx-auto font-medium">
          Query cinematic moments, visual semantic layers, and temporal frame sequences instantly with sub-10ms neural embeddings.
        </p>

        {/* Feature Badges */}
        <div className="flex flex-wrap items-center justify-center gap-3 pt-2 font-mono text-[11px] font-bold">
          <span className="px-2.5 py-1 bg-[#EFECE3] dark:bg-stone-800 border border-black text-black dark:text-white flex items-center gap-1.5">
            <Database className="w-3 h-3 text-[#FF5500]" /> 1.48M+ VECTORS
          </span>
          <span className="px-2.5 py-1 bg-[#EFECE3] dark:bg-stone-800 border border-black text-black dark:text-white flex items-center gap-1.5">
            <Layers className="w-3 h-3 text-[#00D084]" /> ZERO-SHOT INFERENCE
          </span>
          <span className="px-2.5 py-1 bg-[#EFECE3] dark:bg-stone-800 border border-black text-black dark:text-white flex items-center gap-1.5">
            <Sparkles className="w-3 h-3 text-[#FFD700]" /> TEMPORAL KEYFRAMES
          </span>
        </div>
      </div>

      {/* Search Input Bar */}
      <SearchBar
        initialQuery={currentQuery}
        onSearch={handleSearch}
        onOptionsChange={handleOptionsChange}
        isSearching={isSearching}
      />

      {/* Error state */}
      {error && (
        <div className="max-w-4xl mx-auto p-5 bg-red-100 dark:bg-red-950/50 border-2 border-red-600 text-center space-y-1 font-mono shadow-[4px_4px_0px_0px_#000]">
          <p className="text-sm font-black uppercase text-red-900 dark:text-red-300">
            SEARCH UNAVAILABLE // API EXCEPTION
          </p>
          <p className="text-xs text-red-700 dark:text-red-400">{error}</p>
        </div>
      )}

      {/* Search Results Grid */}
      {hasSearched && !error && (
        <SceneGrid
          scenes={result.scenes}
          query={currentQuery}
          result={result}
          searchMeta={searchMeta}
          isSearching={isSearching}
          isLoadingMore={isLoadingMore}
          onLoadMore={handleLoadMore}
          onRemoveConcept={handleRemoveConcept}
        />
      )}

      {/* Empty / Initial State */}
      {!hasSearched && !error && (
        <div className="text-center space-y-3 max-w-xl mx-auto p-8 bg-white dark:bg-[#1C1A17] border-2 border-black shadow-[4px_4px_0px_0px_#000] font-mono">
          <p className="text-sm font-bold text-black dark:text-white uppercase">
            [READY // AWAITING QUERY INPUT]
          </p>
          <p className="text-xs text-stone-600 dark:text-stone-400 font-sans leading-relaxed">
            Enter a scene description above or click one of the suggested prompts to launch vector similarity search across all indexed video keyframes.
          </p>
        </div>
      )}

      <SelectionTray />
    </div>
  )
}
