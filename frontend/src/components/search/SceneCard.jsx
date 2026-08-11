import React, { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { Play, Clock, Sparkles, Film, Tag, X, ArrowLeft } from 'lucide-react'
import { getVideoStreamUrl } from '../../services/api'

export const SceneCard = ({ scene }) => {
  const [showPlayerModal, setShowPlayerModal] = useState(false)
  const videoRef = useRef(null)

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        setShowPlayerModal(false)
      }
    }
    if (showPlayerModal) {
      window.addEventListener('keydown', handleKeyDown)
    }
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [showPlayerModal])

  const getScoreBadgeClass = (score) => {
    if (score >= 90) return { bg: 'bg-emerald-50 dark:bg-[#1d352b]/65 text-emerald-800 dark:text-[#a8c0b0] border-emerald-200 dark:border-[#456f5b]/55' }
    if (score >= 80) return { bg: 'bg-orange-50 dark:bg-[#1d352b]/45 text-orange-800 dark:text-[#a8c0b0] border-orange-200 dark:border-[#315c49]/45' }
    return { bg: 'bg-amber-50 dark:bg-[#3a3020]/65 text-amber-800 dark:text-[#c6ad78] border-amber-200 dark:border-[#6d5b35]/55' }
  }

  const scoreStyle = getScoreBadgeClass(scene.score)
  const videoStreamUrl = scene.video_url || getVideoStreamUrl(scene.video_id, scene.timestamp_sec)

  // Curated fallback gradient thumbnail based on scene id hash if no image
  const defaultThumbnails = [
    'https://images.unsplash.com/photo-1508974239320-0a029497e820?auto=format&fit=crop&w=800&q=80',
    'https://images.unsplash.com/photo-1555066931-4365d14bab8c?auto=format&fit=crop&w=800&q=80',
    'https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=800&q=80',
    'https://images.unsplash.com/photo-1503899036084-c55cdd92da26?auto=format&fit=crop&w=800&q=80',
  ]
  const thumbIndex = Math.abs((scene.id || '').split('').reduce((acc, c) => acc + c.charCodeAt(0), 0)) % defaultThumbnails.length
  const thumbSrc = scene.thumbnail || defaultThumbnails[thumbIndex]

  return (
    <>
      <motion.div
        layout
        initial={{ opacity: 0, scale: 0.97 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        transition={{ duration: 0.25 }}
        onClick={() => setShowPlayerModal(true)}
        className="classic-card classic-card-hover rounded-3xl overflow-hidden cursor-pointer flex flex-col group relative"
      >
        {/* Thumbnail preview container */}
        <div className="relative aspect-video w-full overflow-hidden bg-stone-900">
          <img
            src={thumbSrc}
            alt={scene.title || scene.videoName}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500 opacity-90"
            loading="lazy"
          />

          <div className="absolute inset-0 bg-gradient-to-t from-stone-950/80 dark:from-stone-950/90 via-transparent to-transparent opacity-80" />

          {/* Hover Play Button */}
          <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-stone-950/30 dark:bg-[#181512]/55 backdrop-blur-[2px]">
            <div className="w-12 h-12 rounded-full bg-white dark:bg-[#789b86] text-stone-950 dark:text-[#f3ece4] flex items-center justify-center shadow-lg scale-90 group-hover:scale-100 transition-transform">
              <Play className="w-5 h-5 fill-current ml-0.5" />
            </div>
          </div>

          {/* Timestamp badge */}
          <div className="absolute top-3 left-3 px-3 py-1 rounded-full bg-white/90 dark:bg-[#181512]/85 backdrop-blur-md border border-stone-200 dark:border-white/10 text-[11px] font-mono font-bold text-stone-900 dark:text-[#ded3c8] flex items-center gap-1.5 shadow-sm">
            <Clock className="w-3 h-3 text-orange-700 dark:text-[#789b86]" />
            {scene.timestamp || `${scene.timestamp_sec}s`}
          </div>

          {/* Relevance Score Gauge */}
          <div
            className={`absolute top-3 right-3 px-3 py-1 rounded-full backdrop-blur-md border font-mono text-xs font-bold flex items-center gap-1.5 shadow-sm ${scoreStyle.bg}`}
          >
            <Sparkles className="w-3.5 h-3.5 text-orange-700 dark:text-[#789b86]" />
            {scene.score}% Match
          </div>
        </div>

        {/* Card Body */}
        <div className="p-6 flex-1 flex flex-col justify-between space-y-4">
          <div className="pl-3 orange-accent-line">
            <div className="flex items-center gap-2 text-[10px] font-sans font-bold tracking-widest uppercase text-orange-700 dark:text-[#789b86] mb-1">
              <Film className="w-3 h-3" />
              <span className="truncate">{scene.videoName || scene.video_id}</span>
            </div>
            <h3 className="text-base font-serif font-normal text-stone-950 dark:text-[#f3ece4] leading-snug group-hover:text-orange-700 dark:group-hover:text-[#a8c0b0] transition-colors line-clamp-3">
              {scene.description || scene.title}
            </h3>
          </div>

          {/* Tags */}
          <div className="flex items-center gap-1.5 flex-wrap pt-3 border-t border-stone-100 dark:border-[#403933]">
            {scene.tags?.map((tag) => (
              <span
                key={tag}
                className="px-2.5 py-0.5 rounded-full bg-stone-100 dark:bg-[#25211e] text-stone-600 dark:text-[#a99d92] text-[10px] font-mono border border-stone-200 dark:border-[#403933]"
              >
                #{tag}
              </span>
            ))}
          </div>
        </div>
      </motion.div>

      {/* Video Preview Modal */}
      {showPlayerModal && (
        <div
          onClick={() => setShowPlayerModal(false)}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-stone-950/60 dark:bg-[#181512]/85 backdrop-blur-md animate-fadeIn"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-3xl bg-white dark:bg-[#25211e] p-6 sm:p-8 rounded-3xl border border-stone-200 dark:border-[#315c49]/45 shadow-2xl relative space-y-6 max-h-[90vh] overflow-y-auto"
          >
            {/* Top Close / Exit Button */}
            <div className="flex items-center justify-between border-b border-stone-100 dark:border-[#403933] pb-4">
              <div className="flex items-center gap-2">
                <span className="px-3 py-0.5 rounded-full bg-stone-100 dark:bg-[#315c49]/12 text-orange-700 dark:text-[#a8c0b0] border border-stone-200 dark:border-[#315c49]/35 text-[10px] font-sans font-bold uppercase tracking-widest">
                  QDRANT SCENE VECTOR DETAIL
                </span>
                <span className="text-stone-500 dark:text-[#a99d92] text-xs font-mono truncate max-w-[200px]">
                  ID: {scene.id}
                </span>
              </div>

              <button
                type="button"
                onClick={() => setShowPlayerModal(false)}
                className="flex items-center gap-2 px-4 py-1.5 rounded-full bg-stone-950 dark:bg-[#332e2a] hover:bg-orange-700 dark:hover:bg-[#433b35] text-white text-xs font-bold tracking-widest transition-all cursor-pointer uppercase shadow-sm border border-transparent dark:border-[#514841]"
              >
                <X className="w-3.5 h-3.5 text-stone-300 dark:text-[#789b86]" />
                <span>CLOSE (ESC)</span>
              </button>
            </div>

            {/* Video Player Canvas */}
            <div className="aspect-video w-full rounded-2xl overflow-hidden bg-black relative border border-stone-200 dark:border-[#403933] shadow-lg">
              <video
                ref={videoRef}
                controls
                autoPlay
                className="w-full h-full object-contain"
                src={videoStreamUrl}
                onLoadedMetadata={() => {
                  if (videoRef.current && scene.timestamp_sec) {
                    videoRef.current.currentTime = scene.timestamp_sec
                  }
                }}
                onError={(e) => {
                  console.warn('Video stream load error:', e)
                }}
              >
                Your browser does not support HTML5 video streaming.
              </video>
            </div>

            {/* Title & Cosine Score Header */}
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pl-3 orange-accent-line">
              <div>
                <span className="text-xs font-mono text-orange-700 dark:text-[#789b86] font-bold tracking-wider">
                  {scene.videoName || scene.video_id} • Timestamp {scene.timestamp || `${scene.timestamp_sec}s`}
                </span>
                <h2 className="text-xl sm:text-2xl font-serif font-normal text-stone-950 dark:text-[#f3ece4] mt-1">
                  {scene.description || scene.title}
                </h2>
              </div>

              <div className={`px-4 py-2 rounded-full border font-mono text-xs font-bold shrink-0 ${scoreStyle.bg}`}>
                <Sparkles className="w-3.5 h-3.5 inline mr-1 text-orange-700 dark:text-[#789b86]" />
                {scene.score}% Vector Relevance
              </div>
            </div>

            {/* Vector Telemetry Details */}
            <div className="p-4 rounded-2xl bg-stone-50 dark:bg-[#181512] border border-stone-200 dark:border-[#403933] space-y-2 text-xs font-mono text-stone-600 dark:text-[#a99d92]">
              <div className="flex justify-between">
                <span>Vector Point ID:</span>
                <span className="text-stone-950 dark:text-[#ded3c8] font-bold truncate max-w-[280px]">{scene.id}</span>
              </div>
              <div className="flex justify-between">
                <span>Visual Vector (SigLIP ViT-B/16):</span>
                <span className="text-stone-950 dark:text-[#ded3c8] font-bold">768 dimensions ({scene.visual_score || '0.92'})</span>
              </div>
              <div className="flex justify-between">
                <span>Text Vector (BGE-M3 Multilingual):</span>
                <span className="text-stone-950 dark:text-[#ded3c8] font-bold">1024 dimensions ({scene.text_score || '0.88'})</span>
              </div>
              <div className="flex justify-between">
                <span>Fusion Strategy:</span>
                <span className="text-orange-700 dark:text-[#789b86] font-bold">Qdrant RRF (Reciprocal Rank Fusion)</span>
              </div>
            </div>

            {/* Bottom Exit Action */}
            <div className="pt-4 border-t border-stone-100 dark:border-[#403933] flex justify-end">
              <button
                type="button"
                onClick={() => setShowPlayerModal(false)}
                className="px-6 py-2.5 rounded-full bg-stone-950 dark:bg-[#315c49] hover:bg-orange-700 dark:hover:bg-[#789b86] text-white dark:text-[#f3ece4] font-bold text-xs tracking-widest transition-all flex items-center gap-2 cursor-pointer uppercase shadow-sm"
              >
                <ArrowLeft className="w-4 h-4 text-orange-300 dark:text-[#f3ece4]" /> EXIT DETAILS
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
