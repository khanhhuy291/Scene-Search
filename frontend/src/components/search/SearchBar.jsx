import React, { useState } from 'react'
import { motion } from 'framer-motion'
import { Search, Sliders } from 'lucide-react'

export const SearchBar = ({ onSearch, isSearching }) => {
  const [query, setQuery] = useState('')
  const [similarityThreshold, setSimilarityThreshold] = useState(0.75)
  const [searchModal, setSearchModal] = useState('multimodal')
  const [showFilters, setShowFilters] = useState(false)

  const sampleQueries = [
    '🏎️ Red sports car speeding through a rainy neon city at night',
    '💻 Developer typing python code on glowing keyboard',
    '🌅 Cinematic drone shot of golden hour ocean waves',
    '🚀 Rocket launching into deep dark starry space'
  ]

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!query.trim()) return
    onSearch(query, { similarityThreshold, searchModal })
  }

  const handleSampleClick = (promptText) => {
    const cleanPrompt = promptText.replace(/^[^\w]+/, '').trim()
    setQuery(cleanPrompt)
    onSearch(cleanPrompt, { similarityThreshold, searchModal })
  }

  return (
    <div className="w-full max-w-4xl mx-auto space-y-4">
      {/* Search Container Box */}
      <form
        onSubmit={handleSubmit}
        className="bg-white dark:bg-[#25211e]/95 p-3.5 rounded-full border border-stone-300 dark:border-[#403933] shadow-sm dark:shadow-black/20 relative group focus-within:border-stone-950 dark:focus-within:border-[#789b86] focus-within:ring-1 focus-within:ring-stone-950 dark:focus-within:ring-[#315c49]/20 transition-all"
      >
        <div className="flex items-center gap-3 px-3">
          <img
            src="/brand/logo-primary.jpg"
            alt="SceneSearch assistant"
            className="w-10 h-10 rounded-full object-cover shrink-0 drop-shadow-sm"
          />

          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Describe any scene, object, action, or spoken phrase..."
            className="w-full bg-transparent text-stone-950 dark:text-[#f3ece4] placeholder-stone-400 dark:placeholder-[#786e66] text-sm sm:text-base font-sans outline-none border-none focus:ring-0 font-medium"
          />

          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={() => setShowFilters(!showFilters)}
              className={`p-2.5 rounded-full border text-xs font-semibold transition-all cursor-pointer ${
                showFilters
                  ? 'bg-stone-950 text-white border-stone-950 dark:bg-[#315c49]/18 dark:text-[#a8c0b0] dark:border-[#315c49]/45'
                  : 'bg-stone-100 dark:bg-[#332e2a] border-stone-200 dark:border-[#514841] text-stone-600 dark:text-[#a99d92] hover:text-stone-950 dark:hover:text-stone-200'
              }`}
              title="Toggle Vector Similarity Filters"
            >
              <Sliders className="w-4 h-4" />
            </button>

            <button
              type="submit"
              disabled={isSearching || !query.trim()}
              className="px-6 py-2.5 rounded-full bg-stone-950 text-white dark:bg-[#294c3e] dark:text-[#f3ece4] font-bold text-xs tracking-widest uppercase hover:bg-orange-700 dark:hover:opacity-95 shadow-sm transition-all duration-300 flex items-center gap-2 cursor-pointer disabled:opacity-50"
            >
              {isSearching ? (
                <div className="w-4 h-4 border-2 border-white dark:border-stone-950 border-t-transparent rounded-full animate-spin" />
              ) : (
                <>
                  <Search className="w-3.5 h-3.5" /> SEARCH
                </>
              )}
            </button>
          </div>
        </div>

        {/* Expandable Advanced Similarity Filters */}
        {showFilters && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="pt-4 mt-3 border-t border-stone-100 dark:border-[#403933] px-4 pb-2 space-y-4 text-left"
          >
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Slider */}
              <div className="space-y-1">
                <div className="flex justify-between items-center text-xs font-mono">
                  <span className="text-stone-600 dark:text-[#a99d92]">Similarity Cutoff:</span>
                  <span className="text-orange-700 dark:text-[#789b86] font-bold">{(similarityThreshold * 100).toFixed(0)}%</span>
                </div>
                <input
                  type="range"
                  min="0.50"
                  max="0.95"
                  step="0.01"
                  value={similarityThreshold}
                  onChange={(e) => setSimilarityThreshold(parseFloat(e.target.value))}
                  className="w-full accent-orange-700 dark:accent-[#789b86] bg-stone-200 dark:bg-[#332e2a] h-1.5 rounded-lg cursor-pointer"
                />
              </div>

              {/* Multimodal Model selector */}
              <div className="space-y-1">
                <span className="block text-xs font-mono text-stone-600 dark:text-[#a99d92] mb-1">
                  Embedding Model:
                </span>
                <div className="grid grid-cols-3 gap-2">
                  {['multimodal', 'vision_clip', 'audio_whisper'].map((m) => (
                    <button
                      key={m}
                      type="button"
                      onClick={() => setSearchModal(m)}
                      className={`px-2 py-1 rounded-full text-[10px] font-mono font-bold uppercase transition-all ${
                        searchModal === m
                          ? 'bg-stone-950 text-white dark:bg-[#315c49]/18 dark:text-[#a8c0b0] dark:border dark:border-[#315c49]/45'
                          : 'bg-stone-100 dark:bg-[#332e2a] text-stone-600 dark:text-[#a99d92] border border-stone-200 dark:border-[#514841] hover:text-stone-950 dark:hover:text-stone-200'
                      }`}
                    >
                      {m.replace('_', ' ')}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </form>

      {/* Instant Prompt Chips */}
      <div className="flex items-center gap-2 flex-wrap text-xs justify-center">
        <span className="text-stone-500 dark:text-[#a99d92] font-sans text-[10px] font-bold uppercase tracking-widest shrink-0">
          PROMPTS:
        </span>
        {sampleQueries.map((prompt) => (
          <button
            key={prompt}
            type="button"
            onClick={() => handleSampleClick(prompt)}
            className="px-3.5 py-1.5 rounded-full bg-white dark:bg-[#25211e] border border-stone-200 dark:border-[#403933] hover:border-orange-700 dark:hover:border-[#315c49] hover:text-orange-700 dark:hover:text-[#a8c0b0] text-stone-700 dark:text-[#c8bbb0] text-xs transition-all cursor-pointer truncate max-w-xs shadow-2xs font-medium"
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  )
}
