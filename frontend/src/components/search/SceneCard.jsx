import React, { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { motion } from "framer-motion"
import {
  Play,
  Clock,
  Layers,
  ImageOff,
  Check,
  Plus,
  Maximize,
  Sparkles,
  AlertTriangle
} from "lucide-react"
import { humanizeConcept, withTimeFragment } from "../../lib/searchApi"
import { useAuth } from "../../context/AuthContext"
import { useDataset } from "../../context/DatasetContext"
import { useToast } from "../../context/ToastContext"

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
              relevance: "best match"
            }
          ],
    [scene]
  )

  const [showPlayerModal, setShowPlayerModal] = useState(false)
  const [activeMomentId, setActiveMomentId] = useState(moments[0]?.id)
  const [thumbFailed, setThumbFailed] = useState(false)
  const [videoFailed, setVideoFailed] = useState(false)
  const [videoLoading, setVideoLoading] = useState(true)
  const videoRef = useRef(null)
  const { isEngineer, token } = useAuth()
  const { addItem, removeItem, isSelected, activeDraft } = useDataset()
  const { addToast } = useToast()

  const activeMoment = moments.find((m) => m.id === activeMomentId) || moments[0]
  const videoDraftIds = (activeDraft?.items || [])
    .filter((item) => item.videoId === scene.videoId)
    .map((item) => item.id)
  const selected = videoDraftIds.length > 0 || isSelected(scene.id)
  const activeSelected = activeMoment ? isSelected(activeMoment.id) : false

  const matchedKf = scene.keyframesMatched || moments.length || 1
  const totalKf = scene.totalKeyframes || Math.max(matchedKf, 8)
  const coveragePct = Math.min(100, Math.round((matchedKf / totalKf) * 100))

  useEffect(() => {
    setThumbFailed(false)
    setVideoFailed(false)
  }, [scene.id, scene.thumbnail])

  useEffect(() => {
    if (showPlayerModal) {
      setActiveMomentId(moments.find((m) => m.isPrimary)?.id || moments[0]?.id)
      setVideoFailed(false)
      setVideoLoading(true)
    }
  }, [showPlayerModal, moments])

  const seekToMoment = useCallback((moment) => {
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
    else video.addEventListener("loadedmetadata", apply, { once: true })
  }, [])

  const selectMoment = useCallback((moment) => {
    setActiveMomentId(moment.id)
    setVideoLoading(true)
    seekToMoment(moment)
  }, [seekToMoment])

  const handleToggleKeepMoment = useCallback((e, moment = null) => {
    e?.stopPropagation?.()
    if (!isEngineer) {
      addToast("Sign in with an engineer account to save to dataset draft", "info")
      return
    }
    try {
      const target = moment ? sceneFromMoment(scene, moment) : scene
      if (isSelected(target.id)) {
        removeItem(target.id)
        addToast("Removed from draft", "info")
      } else {
        addItem(target, searchMeta || {})
        addToast("Kept moment in draft", "success")
      }
    } catch (err) {
      addToast(err.message, "error")
    }
  }, [addItem, addToast, isEngineer, isSelected, removeItem, scene, searchMeta])

  // Keyboard navigation inside modal (arrow keys step moments, A keeps moment)
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === "Escape") {
        setShowPlayerModal(false)
        return
      }
      if (showPlayerModal) {
        const currentIdx = moments.findIndex((m) => m.id === activeMomentId)
        if (e.key === "ArrowRight" && moments.length > 1) {
          e.preventDefault()
          const nextIdx = (currentIdx + 1) % moments.length
          selectMoment(moments[nextIdx])
        } else if (e.key === "ArrowLeft" && moments.length > 1) {
          e.preventDefault()
          const prevIdx = (currentIdx - 1 + moments.length) % moments.length
          selectMoment(moments[prevIdx])
        } else if (e.key.toLowerCase() === "a") {
          e.preventDefault()
          handleToggleKeepMoment(e, activeMoment)
        }
      }
    }
    if (showPlayerModal) {
      window.addEventListener("keydown", handleKeyDown)
    }
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [showPlayerModal, moments, activeMomentId, activeMoment, selectMoment, handleToggleKeepMoment])

  const handleLoadedMetadata = () => {
    if (activeMoment) seekToMoment(activeMoment)
  }

  const handleToggleFullscreen = (e) => {
    e.stopPropagation()
    const video = videoRef.current
    if (video) {
      if (document.fullscreenElement) {
        document.exitFullscreen().catch(() => {})
      } else if (video.requestFullscreen) {
        video.requestFullscreen().catch(() => {})
      } else if (video.webkitRequestFullscreen) {
        video.webkitRequestFullscreen()
      }
    }
  }

  const openModal = () => setShowPlayerModal(true)

  const handleCardKeyDown = (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault()
      openModal()
    }
  }



  const attachToken = (url) => {
    if (!url || !token) return url
    return url.includes("?") ? `${url}&token=${encodeURIComponent(token)}` : `${url}?token=${encodeURIComponent(token)}`
  }

  const rawPlayerSrc =
    scene.previewBaseUrl ||
    (scene.previewUrl ? scene.previewUrl.split("#")[0] : null) ||
    (scene.id ? `/api/v1/media/clip/${scene.id}` : null) ||
    (scene.videoId ? `/api/v1/media/video/${scene.videoId}` : null)
  const playerSrc = attachToken(rawPlayerSrc)

  return (
    <>
      <motion.article
        layout
        initial={{ opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        transition={{ duration: 0.2 }}
        tabIndex={0}
        onClick={openModal}
        onKeyDown={handleCardKeyDown}
        aria-label={`Result ${scene.rank}: ${scene.description.slice(0, 80)}`}
        className={`bg-white dark:bg-[#1A1815] border-2 border-black dark:border-[#2E2A25] shadow-[4px_4px_0px_0px_#000] dark:shadow-[4px_4px_0px_0px_#FF5500] hover:shadow-[6px_6px_0px_0px_#FF5500] hover:-translate-x-0.5 hover:-translate-y-0.5 cursor-pointer flex flex-col group relative outline-none transition-all duration-150 font-mono select-none ${
          selected ? "ring-2 ring-[#00D084]" : ""
        }`}
      >
        {/* Video Thumbnail Area */}
        <div className="relative aspect-video w-full overflow-hidden bg-black border-b-2 border-black dark:border-[#2E2A25]">
          {scene.thumbnail && !thumbFailed ? (
            <img
              src={attachToken(scene.thumbnail)}
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
            <div className="w-12 h-12 bg-black text-white border-2 border-white flex items-center justify-center shadow-[2px_2px_0px_0px_#FF5500] scale-90 group-hover:scale-100 transition-transform">
              <Play className="w-5 h-5 fill-current ml-0.5 text-[#FF5500]" />
            </div>
          </div>

          {/* Top Rank Badge */}
          <div className="absolute top-2.5 left-2.5 px-2 py-0.5 bg-black/90 text-white border border-white/40 font-mono text-[11px] font-bold">
            #{scene.rank}
          </div>

          {/* Timestamp Badge */}
          <div className="absolute bottom-2.5 left-2.5 px-2 py-0.5 bg-black/90 text-white border border-white/40 font-mono text-[10px] font-bold flex items-center gap-1">
            <Clock className="w-2.5 h-2.5 text-[#FF5500]" />
            <span>{scene.timestamp}</span>
          </div>

          {/* Kept indicator */}
          {selected && (
            <div className="absolute top-2.5 right-2.5 px-2.5 py-0.5 bg-[#00D084] text-black font-mono text-[10px] font-black uppercase border border-black shadow-[1.5px_1.5px_0px_0px_#000]">
              KEPT
            </div>
          )}
        </div>

        {/* Content Body */}
        <div className="p-4 flex-1 flex flex-col justify-between space-y-3">
          <div className="space-y-2">
            {/* Matching Keyframe Coverage Meter */}
            <div className="flex items-center gap-2 font-mono text-[10px] text-stone-500 dark:text-stone-400">
              <span className="shrink-0">{matchedKf}/{totalKf} frames</span>
              <div className="flex-1 h-1.5 bg-stone-200 dark:bg-stone-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-[#FF5500]"
                  style={{ width: `${coveragePct}%` }}
                />
              </div>
              <span className="shrink-0 font-bold text-stone-700 dark:text-stone-300">{coveragePct}%</span>
            </div>

            {/* Caption */}
            <p className="text-xs font-sans text-stone-800 dark:text-stone-200 line-clamp-2 leading-relaxed">
              {activeMoment.caption || scene.description}
            </p>

            {/* Chips: Confirmed & Metadata */}
            <div className="flex flex-wrap items-center gap-1.5 pt-1">
              {(scene.confirmed || []).slice(0, 2).map((concept) => (
                <span
                  key={`c-${concept}`}
                  className="px-2 py-0.5 bg-[#00D084]/15 border border-[#00D084] text-stone-900 dark:text-emerald-300 text-[10px] font-mono font-bold uppercase"
                >
                  ✓ {humanizeConcept(concept)}
                </span>
              ))}
              {scene.denied?.length > 0 && (
                <span className="px-2 py-0.5 bg-amber-500/15 border border-amber-500 text-amber-900 dark:text-amber-300 text-[10px] font-mono font-bold uppercase flex items-center gap-1">
                  <AlertTriangle className="w-2.5 h-2.5 text-amber-500" />
                  <span>{scene.denied.length} contradicting</span>
                </span>
              )}
              {(scene.timeOfDay || scene.weather) && (
                <span className="px-2 py-0.5 bg-stone-100 dark:bg-stone-800/80 border border-stone-300 dark:border-stone-700 text-stone-600 dark:text-stone-300 text-[10px] font-mono uppercase">
                  {scene.timeOfDay || "—"} · {scene.weather || "—"}
                </span>
              )}
            </div>
          </div>

          {/* Action Row */}
          <div className="pt-2 border-t border-stone-200 dark:border-stone-800 flex items-center justify-between">
            <span className="text-[10px] font-mono text-stone-400 group-hover:text-black dark:group-hover:text-white transition-colors">
              INSPECT MOMENT ▶
            </span>
            {isEngineer && (
              <button
                type="button"
                onClick={(e) => handleToggleKeepMoment(e, activeMoment)}
                className={`px-2.5 py-1 text-[10px] font-mono font-bold uppercase border transition-all flex items-center gap-1.5 cursor-pointer ${
                  activeSelected
                    ? "bg-[#00D084] text-black border-black shadow-[1px_1px_0px_0px_#000]"
                    : "bg-white dark:bg-stone-800 text-stone-700 dark:text-stone-300 border-stone-300 dark:border-stone-700 hover:border-black"
                }`}
              >
                {activeSelected ? <Check className="w-3 h-3 stroke-[3]" /> : <Plus className="w-3 h-3" />}
                <span>{activeSelected ? "KEPT" : "+ KEEP"}</span>
              </button>
            )}
          </div>
        </div>
      </motion.article>

      {/* Redesigned Video Modal Inspector */}
      {showPlayerModal && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={`Video player for ${scene.videoId}`}
          onClick={() => setShowPlayerModal(false)}
          className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 bg-black/85 backdrop-blur-sm animate-in fade-in duration-150"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="relative w-[94vw] max-w-4xl bg-[#FDFCF7] dark:bg-[#141210] border-3 border-black dark:border-[#2E2A25] shadow-[8px_8px_0px_0px_#000] dark:shadow-[8px_8px_0px_0px_#FF5500] flex flex-col max-h-[92vh] overflow-hidden font-mono"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 bg-black text-white border-b-2 border-black dark:border-[#2E2A25] shrink-0">
              <div className="flex items-center gap-2.5 min-w-0">
                <span className="font-mono font-black text-xs uppercase text-[#FF5500] truncate">
                  {scene.videoId}
                </span>
                <span className="text-stone-400 text-xs">•</span>
                <span className="text-stone-300 text-[11px] font-mono truncate">
                  frame {activeMoment.frameNo ?? "—"} · {activeMoment.timestamp} · {matchedKf}/{totalKf} frames matched
                </span>
              </div>

              <div className="flex items-center gap-2 shrink-0 ml-3">
                <button
                  type="button"
                  onClick={handleToggleFullscreen}
                  className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 bg-stone-800 hover:bg-stone-700 text-white font-mono text-xs font-bold uppercase border border-stone-600 transition-all cursor-pointer"
                  title="Fullscreen"
                >
                  <Maximize className="w-3 h-3 text-[#FF5500]" />
                  <span>FULLSCREEN</span>
                </button>
                <button
                  type="button"
                  onClick={() => setShowPlayerModal(false)}
                  className="px-3 py-1 bg-[#FF5500] hover:bg-white text-black font-mono text-xs font-black uppercase border border-black shadow-[2px_2px_0px_0px_#FFF] transition-all cursor-pointer"
                >
                  ESC · CLOSE
                </button>
              </div>
            </div>

            {/* Scrollable Modal Body */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {/* VIDEO STAGE */}
              <div className="w-full h-[260px] sm:h-[340px] md:h-[400px] bg-black border-2 border-black overflow-hidden relative flex items-center justify-center shrink-0">
                {playerSrc && !videoFailed ? (
                  <>
                    {videoLoading && (
                      <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/60 backdrop-blur-sm z-20 pointer-events-none gap-2">
                        <div className="flex items-center gap-2 px-3.5 py-1.5 bg-black border-2 border-[#FF5500] text-[#FF5500] font-mono text-xs font-black shadow-[2px_2px_0px_0px_#000] animate-pulse">
                          <div className="w-3.5 h-3.5 border-2 border-[#FF5500] border-t-transparent rounded-full animate-spin" />
                          <span>STREAMING VIDEO FEED...</span>
                        </div>
                      </div>
                    )}
                    <video
                      key={`${scene.videoId}_${activeMoment.id}`}
                      ref={videoRef}
                      src={playerSrc}
                      poster={attachToken(activeMoment.thumbnail || scene.thumbnail) || undefined}
                      controls
                      autoPlay
                      preload="metadata"
                      playsInline
                      onLoadedMetadata={handleLoadedMetadata}
                      onCanPlay={() => setVideoLoading(false)}
                      onPlaying={() => setVideoLoading(false)}
                      onWaiting={() => setVideoLoading(true)}
                      onError={() => {
                        setVideoLoading(false)
                        setVideoFailed(true)
                      }}
                      className="w-full h-full object-contain bg-black"
                    />
                  </>
                ) : activeMoment.thumbnail || scene.thumbnail ? (
                  <div className="w-full h-full relative flex items-center justify-center bg-stone-950">
                    <img
                      src={attachToken(activeMoment.thumbnail || scene.thumbnail)}
                      alt=""
                      className="w-full h-full object-contain"
                    />
                    <div className="absolute bottom-2.5 left-2.5 right-2.5 flex items-center justify-between gap-2">
                      <div className="px-2.5 py-1 bg-black/90 border border-[#FF5500] text-white font-mono text-[11px] uppercase font-black tracking-wider">
                        [KEYFRAME PREVIEW // VIDEO STREAM FALLBACK]
                      </div>
                      {playerSrc && (
                        <button
                          type="button"
                          onClick={() => {
                            setVideoFailed(false)
                            setVideoLoading(true)
                          }}
                          className="px-2.5 py-1 bg-[#FF5500] hover:bg-white text-black font-mono text-[11px] font-black uppercase border border-black cursor-pointer"
                        >
                          RETRY VIDEO ↻
                        </button>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="w-full h-full flex items-center justify-center">
                    <MissingThumbnail caption={activeMoment.caption} />
                  </div>
                )}
              </div>

              {/* FILMSTRIP OF MATCHED MOMENTS */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-[11px] font-mono font-black uppercase text-stone-600 dark:text-stone-400">
                  <span className="flex items-center gap-1.5">
                    <Layers className="w-3.5 h-3.5 text-[#FF5500]" />
                    MATCHED MOMENTS INSIDE THIS CLIP ({moments.length})
                  </span>
                  <span className="text-stone-400 font-normal">← → keys to step</span>
                </div>

                <div className="flex gap-2 overflow-x-auto pb-2 pt-1">
                  {moments.map((moment, idx) => {
                    const isActive = moment.id === activeMoment.id
                    const inDraft = isSelected(moment.id)
                    return (
                      <button
                        key={moment.id || idx}
                        type="button"
                        onClick={() => selectMoment(moment)}
                        className={`flex-shrink-0 w-28 aspect-video relative border-2 bg-stone-900 rounded-[2px] overflow-hidden transition-all cursor-pointer ${
                          isActive
                            ? "border-[#FF5500] ring-2 ring-[#FF5500] shadow-[2px_2px_0px_0px_#FF5500]"
                            : "border-black/50 dark:border-white/20 hover:border-black dark:hover:border-white opacity-70 hover:opacity-100"
                        }`}
                        title={`Moment at ${moment.timestamp}: ${moment.caption?.slice(0, 60)}`}
                      >
                        {moment.thumbnail ? (
                          <img
                            src={attachToken(moment.thumbnail)}
                            alt=""
                            className="w-full h-full object-cover"
                            loading="lazy"
                          />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center text-[10px] text-white">
                            {moment.timestamp}
                          </div>
                        )}
                        <span className="absolute bottom-0 left-0 px-1.5 py-0.5 bg-black/85 text-white font-mono text-[9px] font-bold">
                          {moment.timestamp}
                        </span>
                        {moment.isPrimary && (
                          <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-[#FF5500]" title="Primary match" />
                        )}
                        {inDraft && (
                          <span className="absolute top-1 left-1 px-1 bg-[#00D084] text-black text-[8px] font-bold">
                            KEPT
                          </span>
                        )}
                      </button>
                    )
                  })}
                </div>
              </div>

              {/* CAPTION & DESCRIPTION */}
              <div className="p-4 bg-white dark:bg-stone-900 border-2 border-black dark:border-[#2E2A25] shadow-[3px_3px_0px_0px_#000] space-y-1.5">
                <div className="flex items-center gap-1.5 text-xs font-black uppercase text-[#FF5500]">
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>KEYFRAME CAPTION & PERCEPTION</span>
                </div>
                <p className="text-sm font-sans font-medium text-stone-900 dark:text-stone-100 leading-relaxed">
                  {activeMoment.caption || scene.description}
                </p>
              </div>

              {/* ATTRIBUTE TAGS */}
              <div className="flex flex-wrap gap-2 text-xs font-mono">
                {(scene.timeOfDay || scene.weather || scene.sceneType) && (
                  <span className="px-2.5 py-1 bg-[#F7F4EE] dark:bg-stone-800 border border-black dark:border-stone-700 uppercase">
                    {scene.timeOfDay || "—"} · {scene.weather || "—"} · {scene.sceneType || "—"}
                  </span>
                )}
                {(scene.retrievalTags || []).map((tag) => (
                  <span
                    key={tag}
                    className="px-2 py-0.5 bg-white dark:bg-stone-800 border border-black/30 dark:border-stone-700 text-stone-600 dark:text-stone-300 text-[11px]"
                  >
                    #{tag}
                  </span>
                ))}
              </div>
            </div>

            {/* Footer */}
            <div className="px-4 py-3 bg-[#F7F4EE] dark:bg-[#1A1815] border-t-2 border-black dark:border-[#2E2A25] flex items-center justify-between gap-3 shrink-0">
              <span className="text-[11px] text-stone-500 font-sans hidden sm:inline">
                Press <kbd className="px-1 py-0.5 bg-white dark:bg-stone-800 border border-black text-[10px] font-mono font-bold">A</kbd> to keep moment · <kbd className="px-1 py-0.5 bg-white dark:bg-stone-800 border border-black text-[10px] font-mono font-bold">←</kbd> <kbd className="px-1 py-0.5 bg-white dark:bg-stone-800 border border-black text-[10px] font-mono font-bold">→</kbd> to step
              </span>

              <div className="flex items-center gap-2 ml-auto">
                {isEngineer && (
                  <button
                    type="button"
                    onClick={(e) => handleToggleKeepMoment(e, activeMoment)}
                    className={`px-5 py-2 font-mono text-xs font-black uppercase border-2 border-black transition-all flex items-center gap-1.5 cursor-pointer ${
                      activeSelected
                        ? "bg-[#00D084] text-black shadow-[2px_2px_0px_0px_#000]"
                        : "bg-[#FF5500] text-black shadow-[2px_2px_0px_0px_#000] hover:bg-black hover:text-white"
                    }`}
                  >
                    {activeSelected ? <Check className="w-3.5 h-3.5 stroke-[3]" /> : <Plus className="w-3.5 h-3.5" />}
                    <span>{activeSelected ? "KEPT IN DRAFT ✓" : "KEEP THIS MOMENT"}</span>
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setShowPlayerModal(false)}
                  className="px-4 py-2 bg-black hover:bg-stone-800 text-white font-mono text-xs font-bold uppercase border-2 border-black cursor-pointer"
                >
                  CLOSE
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
