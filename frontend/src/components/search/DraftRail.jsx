import React, { useMemo } from 'react'
import { useLanguage } from '../../context/LanguageContext'
import { Download, Trash2, Layers, Clock, Cloud, Compass } from 'lucide-react'
import { formatTimestamp } from '../../lib/searchApi'

export const DraftRail = ({
  items = [],
  onRemoveItem,
  onExportJsonl,
  className = ''
}) => {
  const { t } = useLanguage()
  // Compute distribution for slice balance
  const distributions = useMemo(() => {
    if (!items.length) return null

    const calcDistribution = (key) => {
      const counts = {}
      items.forEach((item) => {
        const val = (item[key] || item.metadata?.scene?.[key] || 'unknown').toLowerCase()
        counts[val] = (counts[val] || 0) + 1
      })
      return Object.entries(counts)
        .sort((a, b) => b[1] - a[1])
        .map(([name, count]) => ({
          name,
          count,
          pct: Math.round((count / items.length) * 100)
        }))
    }

    return {
      tod: calcDistribution('timeOfDay'),
      weather: calcDistribution('weather'),
      scene: calcDistribution('sceneType')
    }
  }, [items])

  return (
    <aside className={`space-y-4 font-mono text-xs ${className}`}>
      {/* Draft Items Box */}
      <div className="bg-white dark:bg-[#1A1815] border-2 border-black dark:border-[#2E2A25] shadow-[4px_4px_0px_0px_#000] dark:shadow-[4px_4px_0px_0px_#FF5500]">
        <header className="px-4 py-3 border-b-2 border-black dark:border-[#2E2A25] flex items-center justify-between gap-2 bg-[#F7F4EE] dark:bg-[#221F1B]">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[#00D084]" />
            <b className="font-mono font-black uppercase text-black dark:text-white">
              DRAFT · {items.length}
            </b>
          </div>
          <button
            type="button"
            onClick={onExportJsonl}
            disabled={items.length === 0}
            className="px-3 py-1.5 bg-[#FF5500] hover:bg-black hover:text-white text-black font-mono text-[11px] font-black uppercase border border-black shadow-[1.5px_1.5px_0px_0px_#000] active:translate-x-0.5 active:translate-y-0.5 transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            title="Export kept moments as JSONL manifest"
          >
            <Download className="w-3 h-3" />
            <span>{t('rail.export')}</span>
          </button>
        </header>

        <div className="p-3 max-h-[300px] overflow-y-auto space-y-2">
          {items.length === 0 ? (
            <p className="text-stone-500 dark:text-stone-400 font-sans text-xs p-3 text-center leading-relaxed">
              No moments kept yet. Press <b className="font-mono font-bold text-black dark:text-white">A</b> on a result card or use the save button in the clip viewer to assemble a training slice.
            </p>
          ) : (
            items.map((item, idx) => (
              <div
                key={item.id || `${item.videoId}_${idx}`}
                className="flex items-center gap-2.5 p-2 bg-[#FAF8F5] dark:bg-[#14120F] border border-black/20 dark:border-white/10 rounded-sm group"
              >
                <div className="w-14 h-9 bg-black shrink-0 overflow-hidden rounded-[2px] border border-black/40">
                  {item.thumbnail ? (
                    <img
                      src={item.thumbnail}
                      alt=""
                      className="w-full h-full object-cover"
                      loading="lazy"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-[9px] text-stone-500">
                      FRAME
                    </div>
                  )}
                </div>

                <div className="min-w-0 flex-1">
                  <p className="text-[11px] font-sans text-stone-800 dark:text-stone-200 line-clamp-1 font-medium">
                    {item.description || item.caption || 'Driving keyframe'}
                  </p>
                  <div className="flex items-center gap-2 text-[10px] text-stone-500 dark:text-stone-400">
                    <span className="truncate max-w-[90px]">{item.videoId}</span>
                    <span>•</span>
                    <span className="text-[#FF5500] font-bold">
                      {item.timestamp || formatTimestamp(item.startSeconds, item.endSeconds)}
                    </span>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => onRemoveItem?.(item.id)}
                  className="p-1 text-stone-400 hover:text-red-500 transition-colors cursor-pointer"
                  title="Remove from draft"
                  aria-label="Remove item"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Slice Balance Box */}
      <div className="bg-white dark:bg-[#1A1815] border-2 border-black dark:border-[#2E2A25] shadow-[4px_4px_0px_0px_#000] dark:shadow-[4px_4px_0px_0px_#FF5500]">
        <header className="px-4 py-2.5 border-b-2 border-black dark:border-[#2E2A25] bg-[#F7F4EE] dark:bg-[#221F1B]">
          <b className="font-mono font-black uppercase text-black dark:text-white flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5 text-[#FF5500]" />
            SLICE BALANCE
          </b>
        </header>

        <div className="p-3.5 space-y-3.5">
          {!distributions ? (
            <p className="text-stone-500 dark:text-stone-400 font-sans text-xs text-center py-2">
              Distribution meters appear once the draft has moments in it.
            </p>
          ) : (
            <>
              {/* Time of Day */}
              <div className="space-y-1.5">
                <span className="text-[10px] font-bold text-stone-500 dark:text-stone-400 uppercase flex items-center gap-1">
                  <Clock className="w-3 h-3" /> TIME OF DAY
                </span>
                <div className="space-y-1">
                  {distributions.tod.slice(0, 3).map((d) => (
                    <div key={d.name} className="grid grid-cols-[70px_1fr_30px] items-center gap-2 text-[11px]">
                      <span className="truncate uppercase text-stone-700 dark:text-stone-300">{d.name}</span>
                      <div className="h-1.5 bg-stone-200 dark:bg-stone-800 rounded-full overflow-hidden">
                        <div className="h-full bg-[#FF5500]" style={{ width: `${d.pct}%` }} />
                      </div>
                      <b className="text-right text-stone-900 dark:text-stone-100">{d.count}</b>
                    </div>
                  ))}
                </div>
              </div>

              {/* Weather */}
              <div className="space-y-1.5 pt-2 border-t border-black/10 dark:border-white/10">
                <span className="text-[10px] font-bold text-stone-500 dark:text-stone-400 uppercase flex items-center gap-1">
                  <Cloud className="w-3 h-3" /> WEATHER
                </span>
                <div className="space-y-1">
                  {distributions.weather.slice(0, 3).map((d) => (
                    <div key={d.name} className="grid grid-cols-[70px_1fr_30px] items-center gap-2 text-[11px]">
                      <span className="truncate uppercase text-stone-700 dark:text-stone-300">{d.name}</span>
                      <div className="h-1.5 bg-stone-200 dark:bg-stone-800 rounded-full overflow-hidden">
                        <div className="h-full bg-[#00D084]" style={{ width: `${d.pct}%` }} />
                      </div>
                      <b className="text-right text-stone-900 dark:text-stone-100">{d.count}</b>
                    </div>
                  ))}
                </div>
              </div>

              {/* Scene Type */}
              <div className="space-y-1.5 pt-2 border-t border-black/10 dark:border-white/10">
                <span className="text-[10px] font-bold text-stone-500 dark:text-stone-400 uppercase flex items-center gap-1">
                  <Compass className="w-3 h-3" /> SCENE TYPE
                </span>
                <div className="space-y-1">
                  {distributions.scene.slice(0, 3).map((d) => (
                    <div key={d.name} className="grid grid-cols-[70px_1fr_30px] items-center gap-2 text-[11px]">
                      <span className="truncate uppercase text-stone-700 dark:text-stone-300">{d.name}</span>
                      <div className="h-1.5 bg-stone-200 dark:bg-stone-800 rounded-full overflow-hidden">
                        <div className="h-full bg-[#FFD700]" style={{ width: `${d.pct}%` }} />
                      </div>
                      <b className="text-right text-stone-900 dark:text-stone-100">{d.count}</b>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Keyboard Shortcuts Box */}
      <div className="bg-white dark:bg-[#1A1815] border-2 border-black dark:border-[#2E2A25] p-3.5 shadow-[4px_4px_0px_0px_#000] dark:shadow-[4px_4px_0px_0px_#FF5500] space-y-2">
        <span className="text-[10px] font-black uppercase tracking-wider text-stone-500 dark:text-stone-400 block">
          {t('rail.shortcuts')}
        </span>
        <div className="grid grid-cols-2 gap-y-1.5 gap-x-2 text-[11px]">
          <div className="flex items-center justify-between">
            <kbd className="px-1.5 py-0.5 bg-[#F7F4EE] dark:bg-stone-800 border border-black/40 text-[10px] font-bold">J / K</kbd>
            <span className="text-stone-500">navigate</span>
          </div>
          <div className="flex items-center justify-between">
            <kbd className="px-1.5 py-0.5 bg-[#F7F4EE] dark:bg-stone-800 border border-black/40 text-[10px] font-bold">Enter</kbd>
            <span className="text-stone-500">open clip</span>
          </div>
          <div className="flex items-center justify-between">
            <kbd className="px-1.5 py-0.5 bg-[#F7F4EE] dark:bg-stone-800 border border-black/40 text-[10px] font-bold">A</kbd>
            <span className="text-stone-500">keep moment</span>
          </div>
          <div className="flex items-center justify-between">
            <kbd className="px-1.5 py-0.5 bg-[#F7F4EE] dark:bg-stone-800 border border-black/40 text-[10px] font-bold">/</kbd>
            <span className="text-stone-500">focus search</span>
          </div>
          <div className="flex items-center justify-between col-span-2 pt-1 border-t border-black/10 dark:border-white/10">
            <kbd className="px-1.5 py-0.5 bg-[#F7F4EE] dark:bg-stone-800 border border-black/40 text-[10px] font-bold">← / →</kbd>
            <span className="text-stone-500">step moment in viewer</span>
          </div>
        </div>
      </div>
    </aside>
  )
}
