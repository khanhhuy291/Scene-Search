import React, { useEffect, useMemo, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import {
  Play,
  Clock,
  X,
  ArrowLeft,
  Layers,
  ImageOff,
  Check,
  Ban,
  Plus,
  CheckCircle2
} from 'lucide-react'
import { humanizeConcept, withTimeFragment } from '../../lib/searchApi'
import { useAuth } from '../../context/AuthContext'
import { useDataset } from '../../context/DatasetContext'
import { useToast } from '../../context/ToastContext'

const MissingThumbnail = ({ caption }) => (
  <div className="w-full h-full flex flex-col items-center justify-center gap-2 bg-stone-900 px-6 text-center text-white font-mono">
    <ImageOff className="w-6 h-6 text-stone-500" />
    <span className="text-[10px] font-black uppercase tracking-widest text-stone-400">
      [NO THUMBNAIL RENDERED]
    </span>
    <span className="text-[11px] text-stone-300 line-clamp-3">
      {caption}
    </span>
  </div>
)

const sceneFromMoment = (scene, moment) => ({
  ...scene,
  id: moment.id,
  description: moment.caption || scene.description,
  timestamp: moment.timestamp,
  startSeconds: moment.startSeconds,
  endSeconds: moment.endSeconds,
  thumbnail: moment.thumbnail || scene.thumbnail,
  frameNo: moment.frameNo,
  previewUrl: withTimeFragment(
    scene.previewBaseUrl || scene.previewUrl,
    moment.startSeconds
  )
})

export const SceneCard = ({ scene, searchMeta = null }) => {
  const moments = useMemo(
    () =>
      scene.matchingMoments?.length
        ? scene.matchingMoments
        : [
            {
              id: scene.id,
              startSeconds: scene.startSeconds,
              endSeconds: scene.endSeconds,
              timestamp: scene.timestamp,
              caption: scene.description,
              thumbnail: scene.thumbnail,
              frameNo: scene.frameNo,
              isPrimary: true,
              relevance: 'best match'
            }
          ],
    [scene]
  )

  const [showPlayerModal, setShowPlayerModal] = useState(false)
  const [activeMomentId, setActiveMomentId] = useState(moments[0]?.id)
  const [thumbFailed, setThumbFailed] = useState(false)
  const videoRef = useRef(null)
  const { isEngineer } = useAuth()
  const { addItem, removeItem, isSelected, activeDraft } = useDataset()
  const { addToast } = useToast()

  const activeMoment = moments.find((m) => m.id === activeMomentId) || moments[0]
  const videoDraftIds = (activeDraft?.items || [])
    .filter((item) => item.videoId === scene.videoId)
    .map((item) => item.id)
  const selected = videoDraftIds.length > 0 || isSelected(scene.id)
  const activeSelected = activeMoment ? isSelected(activeMoment.id) : false

  useEffect(() => {
    setThumbFailed(false)
  }, [scene.id, scene.thumbnail])

  useEffect(() => {
    if (showPlayerModal) {
      setActiveMomentId(moments.find((m) => m.isPrimary)?.id || moments[0]?.id)
    }
  }, [showPlayerModal, moments])

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') setShowPlayerModal(false)
    }
    if (showPlayerModal) {
      window.addEventListener('keydown', handleKeyDown)
    }
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [showPlayerModal])

  const seekToMoment = (moment) => {
    const video = videoRef.current
    if (!video || !moment) return
    const time = Math.max(0, Number(moment.startSeconds) || 0)
    const apply = () => {
      if (Number.isFinite(video.duration) && video.duration > 0) {
        video.currentTime = Math.min(time, Math.max(0, video.duration - 0.05))
      } else {
        video.currentTime = time
      }
      video.play?.().catch(() => {})
    }
    if (video.readyState >= 1) apply()
    else video.addEventListener('loadedmetadata', apply, { once: true })
  }

  const handleLoadedMetadata = () => {
    if (activeMoment) seekToMoment(activeMoment)
  }

  const selectMoment = (moment) => {
    setActiveMomentId(moment.id)
    seekToMoment(moment)
  }

  const openModal = () => setShowPlayerModal(true)

  const handleCardKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      openModal()
    }
  }

  const handleMarkRelevant = (e, moment = null) => {
    e.stopPropagation()
    if (!isEngineer) return
    try {
      const target = moment ? sceneFromMoment(scene, moment) : scene
      if (isSelected(target.id)) {
        removeItem(target.id)
        addToast('Removed from dataset draft', 'info')
        return
      }
      addItem(target, searchMeta || {})
      addToast(
        moment && !moment.isPrimary
          ? 'Added this matching moment to draft'
          : 'Added to dataset draft',
        'success'
      )
    } catch (err) {
      addToast(err.message, 'error')
    }
  }

  const handleRemoveVideo = (e) => {
    e.stopPropagation()
    if (!isEngineer) return
    const ids = new Set([
      scene.id,
      ...moments.map((moment) => moment.id),
      ...videoDraftIds
    ])
    ids.forEach((id) => removeItem(id))
    addToast('Removed this video from draft', 'info')
  }

  const handleMarkAllMoments = (e) => {
    e.stopPropagation()
    if (!isEngineer) return
    try {
      let added = 0
      for (const moment of moments) {
        const result = addItem(sceneFromMoment(scene, moment), searchMeta || {})
        added += result?.added ?? 1
      }
      addToast(
        added > 0
          ? `Added ${added} matching moment${added === 1 ? '' : 's'} from this video`
          : 'Those moments are already in your draft',
        added > 0 ? 'success' : 'info'
      )
    } catch (err) {
      addToast(err.message, 'error')
    }
  }

  const evidence = [
    ...scene.confirmed.map((concept) => ({ concept, kind: 'confirmed' })),
    ...scene.denied.map((concept) => ({ concept, kind: 'denied' }))
  ]

  const playerSrc = scene.previewBaseUrl || (scene.previewUrl ? scene.previewUrl.split('#')[0] : null)

  return (
    <>
      <motion.div
        layout
        initial={{ opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        transition={{ duration: 0.2 }}
        role="button"
        tabIndex={0}
        onClick={openModal}
        onKeyDown={handleCardKeyDown}
        aria-label={`Open moment at ${scene.timestamp}`}
        className="bg-white dark:bg-[#1C1A17] border-2 border-black shadow-[4px_4px_0px_0px_#000] hover:shadow-[6px_6px_0px_0px_#FF5500] hover:-translate-x-0.5 hover:-translate-y-0.5 cursor-pointer flex flex-col group relative outline-none transition-all duration-150 font-mono select-none"
      >
        {/* Video Thumbnail Area */}
        <div className="relative aspect-video w-full overflow-hidden bg-black border-b-2 border-black">
          {scene.thumbnail && !thumbFailed ? (
            <img
              src={scene.thumbnail}
              alt={scene.description.slice(0, 120)}
              className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
              loading="lazy"
              onError={() => setThumbFailed(true)}
            />
          ) : (
            <MissingThumbnail caption={scene.description} />
          )}

          <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-80" />

          {/* Hover Play Indicator */}
          <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-black/40 backdrop-blur-[2px]">
            {scene.previewUrl ? (
              <div className="w-12 h-12 bg-black text-white border-2 border-white flex items-center justify-center shadow-[2px_2px_0px_0px_#FF5500] scale-90 group-hover:scale-100 transition-transform">
                <Play className="w-5 h-5 fill-current ml-0.5 text-[#FF5500]" />
              </div>
            ) : (
              <span className="px-3 py-1 bg-black text-white font-mono text-[10px] font-black uppercase border border-white">
                NO CLIP · DETAILS
              </span>
            )}
          </div>

          {/* Top Badges */}
          <div className="absolute top-2.5 left-2.5 px-2 py-0.5 bg-black/90 text-white border border-white/40 font-mono text-[10px] font-bold flex items-center gap-1">
            <Clock className="w-2.5 h-2.5 text-[#FF5500]" />
            <span>{scene.timestamp}</span>
          </div>

          <div className="absolute top-2.5 right-2.5 px-2 py-0.5 bg-[#FF5500] text-black font-mono text-[10px] font-black uppercase border border-black flex items-center gap-1 shadow-[1.5px_1.5px_0px_0px_#000]">
            <Layers className="w-3 h-3" />
            <span>{moments.length} {moments.length === 1 ? 'MOMENT' : 'MOMENTS'}</span>
          </div>
        </div>

        {/* Content Body */}
        <div className="p-4 flex-1 flex flex-col justify-between space-y-3">
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-[10px] font-mono font-bold uppercase">
              <span className="text-[#FF5500]">RANK #{scene.rank}</span>
              {scene.score != null && (
                <span className={`px-1.5 py-0.5 border text-[9px] font-mono font-bold ${
                  scene.isReranked
                    ? 'bg-[#FFD700] text-black border-black shadow-[1px_1px_0px_0px_#000]'
                    : 'bg-stone-100 dark:bg-stone-800 text-stone-800 dark:text-stone-200 border-black'
                }`}>
                  {scene.isReranked ? '⚡ RERANK ' : '🎯 SCORE '}
                  {scene.score.toFixed(3)}
                </span>
              )}
              <span className="truncate max-w-[120px] text-stone-500">{scene.videoId}</span>
            </div>

            <p className="text-xs font-sans font-bold text-black dark:text-white leading-snug line-clamp-3">
              {scene.description}
            </p>

            {scene.contradictionNote && (
              <p className="p-1.5 bg-amber-50 dark:bg-amber-950/40 border border-amber-400 text-[10px] font-mono text-amber-900 dark:text-amber-300">
                ⚠️ {scene.contradictionNote}
              </p>
            )}
          </div>

          {/* Evidence & Concept Badges */}
          {evidence.length > 0 && (
            <div className="flex items-center gap-1.5 flex-wrap pt-2 border-t border-black/20">
              {evidence.map(({ concept, kind }) => (
                <span
                  key={`${kind}-${concept}`}
                  className={`inline-flex items-center gap-1 px-1.5 py-0.5 text-[9px] font-mono font-black uppercase border ${
                    kind === 'confirmed'
                      ? 'bg-[#00D084] text-black border-black shadow-[1px_1px_0px_0px_#000]'
                      : 'bg-red-100 text-red-900 border-red-600'
                  }`}
                >
                  {kind === 'confirmed' ? <Check className="w-2.5 h-2.5 stroke-[3]" /> : <Ban className="w-2.5 h-2.5 stroke-[3]" />}
                  {kind === 'denied' ? 'NO ' : ''}
                  {humanizeConcept(concept)}
                </span>
              ))}
            </div>
          )}

          {/* Action Buttons for Engineers */}
          {isEngineer && (
            <div className="pt-2 border-t border-black/20">
              <button
                type="button"
                onClick={selected ? handleRemoveVideo : handleMarkRelevant}
                className={`w-full py-2 font-mono text-[10px] font-black tracking-wider uppercase flex items-center justify-center gap-1.5 border-2 transition-all cursor-pointer ${
                  selected
                    ? 'bg-red-100 hover:bg-red-600 text-red-900 hover:text-white border-red-600 shadow-[2px_2px_0px_0px_#000]'
                    : 'bg-black hover:bg-[#FF5500] text-white hover:text-black border-black shadow-[2px_2px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5'
                }`}
              >
                {selected ? (
                  <>
                    <X className="w-3.5 h-3.5" /> REMOVE FROM DRAFT
                  </>
                ) : (
                  <>
                    <Plus className="w-3.5 h-3.5" /> ADD TO DRAFT
                  </>
                )}
              </button>
            </div>
          )}
        </div>
      </motion.div>

      {/* Player Modal */}
      {showPlayerModal && activeMoment && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Keyframe detail"
          onClick={() => setShowPlayerModal(false)}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fadeIn"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-4xl bg-[#F7F4EE] dark:bg-[#1C1A17] p-6 sm:p-8 border-3 border-black shadow-[10px_10px_0px_0px_#000] relative space-y-5 max-h-[90vh] overflow-y-auto font-mono text-black dark:text-white"
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b-2 border-black pb-4">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="px-2.5 py-0.5 bg-[#FF5500] text-black font-black text-xs uppercase border border-black shadow-[1.5px_1.5px_0px_0px_#000]">
                  SCENE INSPECTOR
                </span>
                <span className="text-xs font-bold text-stone-600 dark:text-stone-400">
                  {scene.videoId} // {activeMoment.timestamp}
                </span>
              </div>

              <button
                type="button"
                onClick={() => setShowPlayerModal(false)}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-black hover:bg-[#FF5500] text-white hover:text-black font-mono text-xs font-bold uppercase border-2 border-black shadow-[2px_2px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all cursor-pointer"
              >
                <X className="w-3.5 h-3.5" />
                <span>ESC</span>
              </button>
            </div>

            {/* Video Player */}
            <div className="aspect-video w-full bg-black border-2 border-black shadow-[4px_4px_0px_0px_#000] overflow-hidden relative">
              {playerSrc ? (
                <video
                  key={scene.videoId}
                  ref={videoRef}
                  src={playerSrc}
                  poster={activeMoment.thumbnail || scene.thumbnail || undefined}
                  controls
                  autoPlay
                  preload="auto"
                  onLoadedMetadata={handleLoadedMetadata}
                  className="w-full h-full object-contain bg-black"
                />
              ) : activeMoment.thumbnail || scene.thumbnail ? (
                <img
                  src={activeMoment.thumbnail || scene.thumbnail}
                  alt=""
                  className="w-full h-full object-cover"
                />
              ) : (
                <MissingThumbnail caption={activeMoment.caption} />
              )}
            </div>

            {/* Caption & Metadata */}
            <div className="p-4 bg-white dark:bg-stone-900 border-2 border-black shadow-[3px_3px_0px_0px_#000] space-y-2">
              <div className="flex items-center justify-between text-xs font-black text-[#FF5500]">
                <span>TIMECODE: {activeMoment.timestamp}</span>
                {activeMoment.frameNo != null && <span>FRAME #{activeMoment.frameNo}</span>}
              </div>
              <p className="text-sm font-sans font-bold text-black dark:text-white leading-relaxed">
                {activeMoment.caption}
              </p>
            </div>

            {/* Structured Metadata & Video Timing Inspector */}
            {(scene.metadata || scene.sceneType || scene.timeOfDay || scene.weather) && (
              <div className="p-4 rounded-2xl bg-stone-50 dark:bg-[#181512] border border-stone-200 dark:border-[#403933] space-y-3">
                <div className="flex items-center justify-between border-b border-stone-200/60 dark:border-[#332e2a] pb-2">
                  <span className="text-[10px] font-bold uppercase tracking-widest text-stone-500 dark:text-[#a99d92]">
                    Scene Properties & Video Timing
                  </span>
                  <span className="text-[10px] font-mono text-orange-700 dark:text-[#789b86] font-bold">
                    video_second: {activeMoment.startSeconds}s
                  </span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs font-mono">
                  {scene.score != null && (
                    <div className="p-2 rounded-xl bg-amber-50/70 dark:bg-amber-950/30 border border-amber-200/80 dark:border-amber-700/40">
                      <span className="text-[9px] text-amber-800 dark:text-amber-300 block uppercase font-sans font-bold">
                        {scene.isReranked ? '⚡ Rerank Score' : '🎯 Score'}
                      </span>
                      <span className="text-amber-950 dark:text-amber-200 font-bold font-mono">
                        {scene.score.toFixed(4)}
                      </span>
                    </div>
                  )}
                  {(scene.sceneType || scene.metadata?.scene?.scene_type) && (
                    <div className="p-2 rounded-xl bg-white dark:bg-[#25211e] border border-stone-100 dark:border-[#332e2a]">
                      <span className="text-[9px] text-stone-400 block uppercase">Scene Type</span>
                      <span className="text-stone-800 dark:text-[#ded3c8] font-bold">
                        {scene.sceneType || scene.metadata?.scene?.scene_type}
                      </span>
                    </div>
                  )}
                  {(scene.timeOfDay || scene.metadata?.scene?.time_of_day) && (
                    <div className="p-2 rounded-xl bg-white dark:bg-[#25211e] border border-stone-100 dark:border-[#332e2a]">
                      <span className="text-[9px] text-stone-400 block uppercase">Time of Day</span>
                      <span className="text-stone-800 dark:text-[#ded3c8] font-bold">
                        {scene.timeOfDay || scene.metadata?.scene?.time_of_day}
                      </span>
                    </div>
                  )}
                  {scene.metadata?.scene?.lighting && scene.metadata.scene.lighting !== 'unknown' && (
                    <div className="p-2 rounded-xl bg-white dark:bg-[#25211e] border border-stone-100 dark:border-[#332e2a]">
                      <span className="text-[9px] text-stone-400 block uppercase">Lighting</span>
                      <span className="text-stone-800 dark:text-[#ded3c8] font-bold">
                        {scene.metadata.scene.lighting}
                      </span>
                    </div>
                  )}
                  {scene.metadata?.scene?.visibility && scene.metadata.scene.visibility !== 'unknown' && (
                    <div className="p-2 rounded-xl bg-white dark:bg-[#25211e] border border-stone-100 dark:border-[#332e2a]">
                      <span className="text-[9px] text-stone-400 block uppercase">Visibility</span>
                      <span className="text-stone-800 dark:text-[#ded3c8] font-bold">
                        {scene.metadata.scene.visibility}
                      </span>
                    </div>
                  )}
                  {scene.metadata?.scene?.traffic_density && scene.metadata.scene.traffic_density !== 'unknown' && (
                    <div className="p-2 rounded-xl bg-white dark:bg-[#25211e] border border-stone-100 dark:border-[#332e2a]">
                      <span className="text-[9px] text-stone-400 block uppercase">Traffic Density</span>
                      <span className="text-stone-800 dark:text-[#ded3c8] font-bold">
                        {scene.metadata.scene.traffic_density}
                      </span>
                    </div>
                  )}
                  {scene.weather && scene.weather !== 'unknown' && (
                    <div className="p-2 rounded-xl bg-white dark:bg-[#25211e] border border-stone-100 dark:border-[#332e2a]">
                      <span className="text-[9px] text-stone-400 block uppercase">Weather</span>
                      <span className="text-stone-800 dark:text-[#ded3c8] font-bold">
                        {scene.weather}
                      </span>
                    </div>
                  )}
                  {scene.metadata?.road?.intersection !== undefined && (
                    <div className="p-2 rounded-xl bg-white dark:bg-[#25211e] border border-stone-100 dark:border-[#332e2a]">
                      <span className="text-[9px] text-stone-400 block uppercase">Intersection</span>
                      <span className="text-stone-800 dark:text-[#ded3c8] font-bold">
                        {scene.metadata.road.intersection ? 'Yes' : 'No'}
                      </span>
                    </div>
                  )}
                </div>
                {(scene.retrievalTags?.length > 0 || scene.metadata?.retrieval_tags?.length > 0) && (
                  <div className="flex items-center gap-1.5 flex-wrap pt-1">
                    <span className="text-[10px] text-stone-400 uppercase font-mono mr-1">Tags:</span>
                    {(scene.retrievalTags?.length ? scene.retrievalTags : scene.metadata?.retrieval_tags || []).map((tag) => (
                      <span key={tag} className="px-2 py-0.5 rounded-md bg-stone-200/70 dark:bg-[#315c49]/20 text-stone-700 dark:text-[#a8c0b0] text-[10px] font-mono">
                        #{tag}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Matching Moments Grid */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-black uppercase text-black dark:text-white">
                  MATCHING KEYFRAMES IN THIS CLIP ({moments.length})
                </h3>
                {isEngineer && moments.length > 1 && (
                  <button
                    type="button"
                    onClick={handleMarkAllMoments}
                    className="text-xs font-black uppercase text-[#FF5500] hover:underline cursor-pointer"
                  >
                    + ADD ALL {moments.length} MOMENTS
                  </button>
                )}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {moments.map((moment) => {
                  const isActive = moment.id === activeMoment.id
                  const inDraft = isSelected(moment.id)
                  return (
                    <button
                      key={moment.id}
                      type="button"
                      onClick={() => selectMoment(moment)}
                      className={`flex items-start gap-3 p-3 border-2 text-left transition-all cursor-pointer ${
                        isActive
                          ? 'border-black bg-black text-white shadow-[3px_3px_0px_0px_#FF5500]'
                          : 'border-black bg-white dark:bg-stone-900 text-black dark:text-white shadow-[2px_2px_0px_0px_#000] hover:shadow-[3px_3px_0px_0px_#FF5500]'
                      }`}
                    >
                      <div className="w-16 h-12 bg-stone-900 border border-current shrink-0 overflow-hidden relative">
                        {moment.thumbnail ? (
                          <img src={moment.thumbnail} alt="" className="w-full h-full object-cover" />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center">
                            <Play className="w-3.5 h-3.5" />
                          </div>
                        )}
                      </div>

                      <div className="min-w-0 flex-1 space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-black">{moment.timestamp}</span>
                          {inDraft && <CheckCircle2 className="w-3.5 h-3.5 text-[#00D084]" />}
                        </div>
                        <p className="text-[11px] font-sans line-clamp-2 opacity-90">
                          {moment.caption}
                        </p>
                      </div>
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Modal Bottom Actions */}
            <div className="pt-4 border-t-2 border-black flex flex-wrap justify-between gap-3">
              {isEngineer && (
                <button
                  type="button"
                  onClick={(e) => handleMarkRelevant(e, activeMoment)}
                  className={`px-5 py-2.5 font-mono text-xs font-black uppercase border-2 border-black shadow-[3px_3px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all flex items-center gap-2 cursor-pointer ${
                    activeSelected
                      ? 'bg-red-600 text-white'
                      : 'bg-[#00D084] text-black'
                  }`}
                >
                  {activeSelected ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
                  {activeSelected ? 'REMOVE THIS MOMENT' : 'MARK THIS MOMENT'}
                </button>
              )}

              <button
                type="button"
                onClick={() => setShowPlayerModal(false)}
                className="ml-auto px-6 py-2.5 bg-black hover:bg-[#FF5500] text-white hover:text-black font-mono text-xs font-black uppercase border-2 border-black shadow-[3px_3px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all flex items-center gap-2 cursor-pointer"
              >
                <ArrowLeft className="w-4 h-4" /> EXIT VIEWER
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
