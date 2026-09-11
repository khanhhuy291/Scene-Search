import React, { useState } from "react"
import { useLanguage } from "../../context/LanguageContext"
import { AnimatePresence, motion } from "framer-motion"
import { Search, Sliders, Sparkles } from "lucide-react"

const MODES = [
  { id: "hybrid", label: "HYBRID", hint: "Fuses Qwen 2048d semantic + SigLIP 768d visual vectors" },
  { id: "qwen", label: "QWEN-VL", hint: "Qwen3-VL 2048-dim multimodal embeddings" },
  { id: "siglip", label: "SIGLIP", hint: "SigLIP 768-dim vision-language embeddings" },
  { id: "visual", label: "VISUAL ONLY", hint: "Pure visual similarity retrieval" },
  { id: "caption", label: "CAPTION ONLY", hint: "Lexical & semantic text retrieval" }
]

const PAGE_SIZES = [12, 24, 48, 96]

export const SearchBar = ({ initialQuery = "", onSearch, onOptionsChange, isSearching, compact = false }) => {
  const { t, isVietnamese } = useLanguage()
  const [query, setQuery] = useState(initialQuery)
  const [mode, setMode] = useState("hybrid")
  const [limit, setLimit] = useState(24)
  const [showFilters, setShowFilters] = useState(false)

  React.useEffect(() => {
    if (initialQuery !== undefined) {
      setQuery(initialQuery)
    }
  }, [initialQuery])

  const sampleQueries = isVietnamese
    ? [
        "đường mưa không có người đi bộ",
        "lái xe qua hầm",
        "đường tuyết ban ngày",
        "xe màu vàng và đèn đỏ",
        "cao tốc sương mù lúc hoàng hôn"
      ]
    : [
        "rainy street without pedestrians",
        "driving through a tunnel",
        "snowy road in daylight",
        "yellow vehicle and red light",
        "foggy highway at dusk"
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
    <div className={`w-full mx-auto space-y-3 font-mono ${compact ? "max-w-5xl" : "max-w-4xl"}`}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="bg-white dark:bg-[#1A1815] p-2 sm:p-2.5 border-2 border-black dark:border-[#2E2A25] shadow-[4px_4px_0px_0px_#000] dark:shadow-[4px_4px_0px_0px_#FF5500] transition-all focus-within:shadow-[6px_6px_0px_0px_#FF5500]">
          <div className="flex items-center gap-2 sm:gap-3 px-1.5">
            <div className="w-7 h-7 bg-black text-white flex items-center justify-center font-mono font-black text-xs shrink-0">
              S
            </div>

            <input
              id="search-input"
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t("search.placeholder")}
              className="w-full min-w-0 bg-transparent text-black dark:text-white placeholder:text-stone-400 text-xs sm:text-sm font-mono font-bold outline-none border-none focus:ring-0"
            />

            <div className="flex items-center gap-1.5 shrink-0">
              <button
                type="button"
                onClick={() => setShowFilters((open) => !open)}
                aria-expanded={showFilters}
                aria-label="Search Options"
                className={`p-2 border-2 font-mono text-xs font-black uppercase transition-all cursor-pointer ${
                  showFilters
                    ? "bg-black text-white border-black shadow-[2px_2px_0px_0px_#FF5500]"
                    : "bg-[#F7F4EE] dark:bg-stone-800 border-black dark:border-stone-700 text-black dark:text-white hover:bg-black hover:text-white"
                }`}
                title="Search Options"
              >
                <Sliders className="w-3.5 h-3.5" />
              </button>

              <button
                type="submit"
                disabled={isSearching || !query.trim()}
                className="px-4 sm:px-5 py-2 bg-black hover:bg-[#FF5500] text-white hover:text-black font-mono font-black text-xs uppercase tracking-wider border-2 border-black shadow-[2px_2px_0px_0px_rgba(0,0,0,0.5)] active:translate-x-0.5 active:translate-y-0.5 transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-40"
              >
                {isSearching ? (
                  <div className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" />
                ) : (
                  <>
                    <Search className="w-3.5 h-3.5 stroke-[2.5]" />
                    <span>{t("search.btn")}</span>
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
              className="bg-[#F7F4EE] dark:bg-[#1C1A17] border-2 border-black dark:border-[#2E2A25] shadow-[4px_4px_0px_0px_#000] p-4 space-y-4 text-left"
            >
              <div className="space-y-2">
                <span className="block text-[10px] font-mono font-black uppercase tracking-wider text-stone-600 dark:text-stone-400">
                  {t("search.signals")}
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
                      className={`px-3 py-1 border-2 text-[10px] font-mono font-black uppercase transition-all cursor-pointer ${
                        mode === option.id
                          ? "bg-black text-white border-black shadow-[2px_2px_0px_0px_#FF5500]"
                          : "bg-white dark:bg-stone-800 text-black dark:text-stone-200 border-black/60 dark:border-stone-700 hover:border-black hover:bg-black hover:text-white"
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <span className="block text-[10px] font-mono font-black uppercase tracking-wider text-stone-600 dark:text-stone-400">
                  {t("search.results_per_page")}
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
                      className={`min-w-10 px-2.5 py-1 border-2 text-[10px] font-mono font-black transition-all cursor-pointer ${
                        limit === size
                          ? "bg-black text-white border-black shadow-[2px_2px_0px_0px_#FF5500]"
                          : "bg-white dark:bg-stone-800 text-black dark:text-stone-200 border-black/60 dark:border-stone-700 hover:border-black hover:bg-black hover:text-white"
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

      {/* Suggested Query Chips: only on initial full-size view */}
      {!compact && (
        <div className="flex items-center gap-2 flex-wrap text-xs justify-center font-mono">
          <span className="text-stone-500 text-[10px] font-black uppercase tracking-widest shrink-0 flex items-center gap-1">
            <Sparkles className="w-3 h-3 text-[#FF5500]" />
            {t("search.try")}
          </span>
          {sampleQueries.map((prompt) => (
            <button
              key={prompt}
              type="button"
              onClick={() => handleSampleClick(prompt)}
              className="px-2.5 py-1 bg-white dark:bg-stone-800 hover:bg-black hover:text-white text-black dark:text-white border-2 border-black font-mono text-[11px] font-bold shadow-[2px_2px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all cursor-pointer"
            >
              “{prompt}”
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
