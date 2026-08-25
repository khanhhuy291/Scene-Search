import React, { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Search, Sliders, Sparkles } from 'lucide-react'

const MODES = [
  { id: 'hybrid', label: 'HYBRID', hint: 'Qwen and SigLIP together' },
  { id: 'qwen', label: 'QWEN', hint: 'Qwen embeddings only' },
  { id: 'siglip', label: 'SIGLIP', hint: 'SigLIP image embeddings only' },
  { id: 'visual', label: 'VISUAL', hint: 'Configured visual tower' },
  { id: 'caption', label: 'CAPTION', hint: 'Scene descriptions only' }
]

const PAGE_SIZES = [12, 24, 48, 96]

export const SearchBar = ({ initialQuery = '', onSearch, onOptionsChange, isSearching }) => {
  const [query, setQuery] = useState(initialQuery)
  const [mode, setMode] = useState('hybrid')
  const [limit, setLimit] = useState(24)
  const [showFilters, setShowFilters] = useState(false)

  React.useEffect(() => {
    if (initialQuery !== undefined) {
      setQuery(initialQuery)
    }
  }, [initialQuery])

  const sampleQueries = [
    'Rainy day without people',
    'Snowy intersection at night',
    'Foggy highway with no trucks',
    'trời mưa, không có người đi bộ'
  ]

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!query.trim()) return
    onSearch(query, { mode, limit })
  }

  const handleSampleClick = (promptText) => {
    setQuery(promptText)
    onSearch(promptText, { mode, limit })
  }

  return (
    <div className="w-full max-w-4xl mx-auto space-y-4">
      <form onSubmit={handleSubmit} className="space-y-3 font-mono">
        <div className="bg-white dark:bg-[#1C1A17] p-2 sm:p-3 border-3 border-black shadow-[6px_6px_0px_0px_#000] transition-all focus-within:shadow-[8px_8px_0px_0px_#FF5500]">
          <div className="flex items-center gap-3 px-2">
            <div className="w-8 h-8 bg-black text-white flex items-center justify-center font-mono font-black text-sm shrink-0">
              S
            </div>

            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Describe scene — weather, objects, actions, what is or is not present…"
              className="w-full min-w-0 bg-transparent text-black dark:text-white placeholder:text-stone-400 text-sm sm:text-base font-mono font-bold outline-none border-none focus:ring-0 uppercase"
            />

            <div className="flex items-center gap-2 shrink-0">
              <button
                type="button"
                onClick={() => setShowFilters((open) => !open)}
                aria-expanded={showFilters}
                aria-label="Retrieval options"
                className={`p-2.5 border-2 font-mono text-xs font-black uppercase transition-all cursor-pointer ${
                  showFilters
                    ? 'bg-black text-white border-black shadow-[2px_2px_0px_0px_#FF5500]'
                    : 'bg-[#F7F4EE] dark:bg-stone-800 border-black text-black dark:text-white hover:bg-black hover:text-white'
                }`}
                title="Retrieval options"
              >
                <Sliders className="w-4 h-4" />
              </button>

              <button
                type="submit"
                disabled={isSearching || !query.trim()}
                className="px-5 sm:px-6 py-2.5 bg-black hover:bg-[#FF5500] text-white hover:text-black font-mono font-black text-xs sm:text-sm uppercase tracking-wider border-2 border-black shadow-[3px_3px_0px_0px_rgba(0,0,0,0.5)] active:translate-x-0.5 active:translate-y-0.5 transition-all flex items-center gap-2 cursor-pointer disabled:opacity-40"
              >
                {isSearching ? (
                  <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                ) : (
                  <>
                    <Search className="w-4 h-4 stroke-[2.5]" />
                    <span>SEARCH</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        <AnimatePresence>
          {showFilters && (
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.18 }}
              className="bg-[#F7F4EE] dark:bg-[#1C1A17] border-2 border-black shadow-[4px_4px_0px_0px_#000] p-4 sm:p-5 space-y-4 text-left"
            >
              <div className="space-y-2">
                <span className="block text-[11px] font-mono font-black uppercase tracking-wider text-stone-600 dark:text-stone-400">
                  RETRIEVAL SIGNALS // ENCODER TOWERS
                </span>
                <div className="flex flex-wrap gap-2">
                  {MODES.map((option) => (
                    <button
                      key={option.id}
                      type="button"
                      onClick={() => {
                        setMode(option.id)
                        onOptionsChange?.({ mode: option.id, limit })
                      }}
                      title={option.hint}
                      className={`px-3 py-1.5 border-2 text-[11px] font-mono font-black uppercase transition-all cursor-pointer ${
                        mode === option.id
                          ? 'bg-black text-white border-black shadow-[2px_2px_0px_0px_#FF5500]'
                          : 'bg-white dark:bg-stone-800 text-black dark:text-stone-200 border-black/60 hover:border-black hover:bg-black hover:text-white'
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <span className="block text-[11px] font-mono font-black uppercase tracking-wider text-stone-600 dark:text-stone-400">
                  VIDEOS PER PAGE
                </span>
                <div className="flex flex-wrap gap-2">
                  {PAGE_SIZES.map((size) => (
                    <button
                      key={size}
                      type="button"
                      onClick={() => {
                        setLimit(size)
                        onOptionsChange?.({ mode, limit: size })
                      }}
                      className={`min-w-12 px-3 py-1.5 border-2 text-[11px] font-mono font-black transition-all cursor-pointer ${
                        limit === size
                          ? 'bg-black text-white border-black shadow-[2px_2px_0px_0px_#FF5500]'
                          : 'bg-white dark:bg-stone-800 text-black dark:text-stone-200 border-black/60 hover:border-black hover:bg-black hover:text-white'
                      }`}
                    >
                      {size}
                    </button>
                  ))}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </form>

      {/* Instant Prompt Chips */}
      <div className="flex items-center gap-2 flex-wrap text-xs justify-center font-mono">
        <span className="text-stone-500 text-[10px] font-black uppercase tracking-widest shrink-0 flex items-center gap-1">
          <Sparkles className="w-3 h-3 text-[#FF5500]" />
          PROMPTS:
        </span>
        {sampleQueries.map((prompt) => (
          <button
            key={prompt}
            type="button"
            onClick={() => handleSampleClick(prompt)}
            className="px-3 py-1 bg-white dark:bg-stone-800 border border-black hover:bg-black hover:text-white text-black dark:text-white text-xs font-bold transition-all cursor-pointer shadow-[2px_2px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5"
          >
            "{prompt}"
          </button>
        ))}
      </div>
    </div>
  )
}
