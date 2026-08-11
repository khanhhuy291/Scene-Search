import React, { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { SceneCard } from './SceneCard'
import { Film, Search, Loader2 } from 'lucide-react'

export const MOCK_SCENES = [
  {
    id: 'sc_801',
    videoName: 'cyberpunk_neon_city_4k.mp4',
    title: 'Cyberpunk Red Sports Car in Rain',
    description: 'High speed chase with a sleek red sports car driving down a futuristic neon city street in heavy rain.',
    timestamp: '01:42 - 02:15',
    timestamp_sec: 102.0,
    score: 96.4,
    tags: ['cyberpunk', 'car', 'rain', 'neon', 'city'],
    thumbnail: 'https://images.unsplash.com/photo-1508974239320-0a029497e820?auto=format&fit=crop&w=800&q=80'
  },
  {
    id: 'sc_802',
    videoName: 'developer_workspace_vlog.mp4',
    title: 'Developer Typing Code on Mechanical Keyboard',
    description: 'Close-up camera angle of software engineer typing python AI code on a RGB backlit mechanical keyboard.',
    timestamp: '04:10 - 04:38',
    timestamp_sec: 250.0,
    score: 91.8,
    tags: ['coding', 'keyboard', 'developer', 'workspace'],
    thumbnail: 'https://images.unsplash.com/photo-1555066931-4365d14bab8c?auto=format&fit=crop&w=800&q=80'
  },
  {
    id: 'sc_803',
    videoName: 'drone_nature_scenery.mp4',
    title: 'Sunset Drone Aerial Over Ocean',
    description: 'Breathtaking 4K drone camera flight over golden hour ocean waves crashing against coastal cliffs.',
    timestamp: '00:15 - 00:52',
    timestamp_sec: 15.0,
    score: 88.5,
    tags: ['drone', 'ocean', 'sunset', 'nature', 'aerial'],
    thumbnail: 'https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=800&q=80'
  }
]

export const SceneGrid = ({ scenes = [], query = '', isSearching = false, hasSearched = false }) => {
  const [sortBy, setSortBy] = useState('score')

  const displayScenes = scenes.length > 0 ? scenes : (hasSearched ? [] : MOCK_SCENES)

  const sortedScenes = [...displayScenes].sort((a, b) => {
    if (sortBy === 'score') return (b.score || 0) - (a.score || 0)
    return (a.timestamp || '').localeCompare(b.timestamp || '')
  })

  return (
    <div className="space-y-6">
      {/* Controls Bar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-4 bg-white dark:bg-[#25211e]/95 rounded-2xl border border-stone-200 dark:border-[#403933] shadow-2xs">
        <div className="flex items-center gap-3 pl-2 orange-accent-line">
          <img src="/brand/logo-primary.jpg" alt="" className="w-8 h-8 rounded-full object-cover" />
          <span className="text-xs font-sans font-bold uppercase tracking-widest text-stone-950 dark:text-[#f3ece4]">
            QDRANT VECTOR RESULTS ({isSearching ? '...' : sortedScenes.length})
            {query && <span className="text-stone-500 dark:text-[#a99d92] font-serif lowercase ml-2 font-normal">for "{query}"</span>}
          </span>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-xs text-stone-500 dark:text-[#a99d92] font-mono">Sort:</span>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="bg-stone-100 dark:bg-[#332e2a] border border-stone-200 dark:border-[#514841] text-stone-900 dark:text-[#ded3c8] text-xs font-mono font-bold rounded-full px-3.5 py-1.5 focus:outline-none"
          >
            <option value="score">Cosine Relevance Score</option>
            <option value="timestamp">Timestamp Chronological</option>
          </select>
        </div>
      </div>

      {/* Loading Skeleton View */}
      {isSearching && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3, 4, 5, 6].map((idx) => (
            <div key={idx} className="bg-white dark:bg-[#25211e] rounded-3xl overflow-hidden border border-stone-200 dark:border-[#403933] p-6 space-y-4 animate-pulse">
              <div className="aspect-video w-full bg-stone-200 dark:bg-[#332e2a] rounded-2xl" />
              <div className="h-4 bg-stone-200 dark:bg-[#332e2a] rounded w-3/4" />
              <div className="h-3 bg-stone-200 dark:bg-[#332e2a] rounded w-full" />
              <div className="h-3 bg-stone-200 dark:bg-[#332e2a] rounded w-2/3" />
            </div>
          ))}
        </div>
      )}

      {/* Empty Search State */}
      {!isSearching && hasSearched && sortedScenes.length === 0 && (
        <div className="text-center py-16 px-4 bg-white dark:bg-[#25211e] rounded-3xl border border-stone-200 dark:border-[#403933] space-y-4 max-w-lg mx-auto">
          <Search className="w-12 h-12 text-stone-400 dark:text-[#789b86] mx-auto opacity-70" />
          <h3 className="text-lg font-serif text-stone-900 dark:text-[#f3ece4]">No matching scene vectors found</h3>
          <p className="text-stone-500 dark:text-[#a99d92] text-xs">
            Try adjusting your query string or describing actions, objects, lighting, or setting details.
          </p>
        </div>
      )}

      {/* Grid Layout */}
      {!isSearching && sortedScenes.length > 0 && (
        <motion.div layout className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <AnimatePresence>
            {sortedScenes.map((scene) => (
              <SceneCard key={scene.id} scene={scene} />
            ))}
          </AnimatePresence>
        </motion.div>
      )}
    </div>
  )
}
