import React, { useState, useEffect } from 'react'
import { SearchBar } from '../components/search/SearchBar'
import { SceneGrid, MOCK_SCENES } from '../components/search/SceneGrid'
import { useToast } from '../context/ToastContext'
import { searchScenes } from '../services/api'

export const SearchPage = () => {
  const { addToast } = useToast()
  const [currentQuery, setCurrentQuery] = useState('')
  const [scenes, setScenes] = useState([])
  const [isSearching, setIsSearching] = useState(false)
  const [hasSearched, setHasSearched] = useState(false)

  // Perform initial default search on load
  useEffect(() => {
    handleSearch('city street driving', { initial: true })
  }, [])

  const handleSearch = async (queryText, options = {}) => {
    if (!queryText || !queryText.trim()) return

    setCurrentQuery(queryText)
    setIsSearching(true)

    try {
      const data = await searchScenes({
        query: queryText,
        limit: 12,
      })

      setIsSearching(false)
      setHasSearched(true)

      if (data.results && data.results.length > 0) {
        setScenes(data.results)
        if (!options.initial) {
          addToast(`Found ${data.results.length} Qdrant scene vectors for "${queryText}"`, 'success')
        }
      } else {
        setScenes([])
        if (!options.initial) {
          addToast(`No matching vector scenes found for "${queryText}"`, 'info')
        }
      }
    } catch (err) {
      console.error('Qdrant Search API Error:', err)
      setIsSearching(false)
      setHasSearched(true)

      // Fallback to local filter if backend error occurs
      const filtered = MOCK_SCENES.filter(
        (s) =>
          s.title.toLowerCase().includes(queryText.toLowerCase()) ||
          s.description.toLowerCase().includes(queryText.toLowerCase()) ||
          s.tags.some((t) => t.toLowerCase().includes(queryText.toLowerCase()))
      )
      setScenes(filtered.length > 0 ? filtered : MOCK_SCENES)
      addToast(`API error: ${err.message}. Showing local preview data.`, 'warning')
    }
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 space-y-16 animate-fadeIn pb-24">
      {/* Hero Banner Header */}
      <div className="text-center space-y-4 max-w-4xl mx-auto pt-6">
        <div className="inline-flex items-center gap-2 px-4 py-1 rounded-full bg-white dark:bg-[#25211e] border border-stone-200 dark:border-[#403933] text-stone-700 dark:text-[#a8c0b0] text-xs font-sans font-bold tracking-widest uppercase shadow-2xs">
          <img src="/brand/logo-primary.jpg" alt="" className="w-6 h-6 rounded-full object-cover" />
          <span>ELEGANT AI LAB • QDRANT VECTOR ENGINE (21,979 SCENES)</span>
        </div>

        {/* Main Title */}
        <img
          src="/brand/logo-primary.jpg"
          alt="SceneSearch"
          className="w-36 h-36 sm:w-44 sm:h-44 mx-auto rounded-full object-cover drop-shadow-xl"
        />
        <h1 className="text-4xl sm:text-6xl lg:text-7xl font-serif text-stone-950 dark:text-[#f3ece4] tracking-tighter uppercase font-normal leading-none">
          SCENESEARCH
        </h1>

        <p className="text-stone-600 dark:text-[#a99d92] text-sm font-sans tracking-widest uppercase max-w-xl mx-auto font-medium">
          Multimodal Video Intelligence & Hybrid Vector Scene Retrieval
        </p>
      </div>

      {/* Search Bar Component */}
      <SearchBar onSearch={handleSearch} isSearching={isSearching} />

      {/* Results Grid Component */}
      <SceneGrid scenes={scenes} query={currentQuery} isSearching={isSearching} hasSearched={hasSearched} />

      {/* Unique Scroll Element at bottom */}
      <div className="flex flex-col items-center justify-center pt-12 space-y-2 text-stone-400 dark:text-[#847970]">
        <span className="text-[10px] font-sans font-bold tracking-widest uppercase text-stone-500 dark:text-[#a99d92]">
          SCROLL
        </span>
        <div className="w-[1.5px] h-12 bg-stone-300 dark:bg-[#332e2a] relative overflow-hidden">
          <div className="w-full h-full bg-orange-700 dark:bg-[#789b86] animate-scroll-line" />
        </div>
      </div>
    </div>
  )
}
