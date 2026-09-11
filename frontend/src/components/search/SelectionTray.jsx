import React, { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { FolderKanban, Save, X, Download, ArrowUpRight } from 'lucide-react'
import { useAuth } from '../../context/AuthContext'
import { useDataset } from '../../context/DatasetContext'
import { useToast } from '../../context/ToastContext'

const BalanceSpark = ({ items }) => {
  const counts = useMemo(() => {
    const map = {}
    for (const item of items) {
      const key = item.weather || 'unknown'
      map[key] = (map[key] || 0) + 1
    }
    return Object.entries(map).sort((a, b) => b[1] - a[1]).slice(0, 5)
  }, [items])

  const max = Math.max(1, ...counts.map(([, n]) => n))
  if (counts.length === 0) return null

  return (
    <div className="flex items-end gap-1 h-7 font-mono" title="Class balance by weather tag">
      {counts.map(([label, n]) => (
        <div key={label} className="flex flex-col items-center gap-0.5">
          <div
            className="w-2.5 bg-[#FF5500] border border-black"
            style={{ height: `${Math.max(4, (n / max) * 22)}px` }}
          />
          <span className="text-[7px] font-black uppercase text-stone-500 max-w-[2rem] truncate">
            {label.slice(0, 3)}
          </span>
        </div>
      ))}
    </div>
  )
}

export const SelectionTray = () => {
  const { isEngineer } = useAuth()
  const { activeDraft, removeItem, saveDataset, downloadBundle } = useDataset()
  const { addToast } = useToast()

  if (!isEngineer || !activeDraft || activeDraft.items.length === 0) return null

  const videoCount = new Set(activeDraft.items.map((i) => i.videoId)).size

  const handleSave = () => {
    try {
      saveDataset()
      addToast('Dataset saved — download anytime from My datasets', 'success')
    } catch (err) {
      addToast(err.message, 'error')
    }
  }

  const handleDownloadNow = async () => {
    try {
      await downloadBundle(activeDraft.id)
      addToast('Downloaded keyframe manifest + videos', 'success')
    } catch (err) {
      addToast(err.message, 'error')
    }
  }

  return (
    <div className="fixed bottom-0 inset-x-0 z-40 border-t-3 border-black bg-[#F7F4EE] dark:bg-[#1C1A17] shadow-[0_-6px_0px_0px_rgba(0,0,0,0.2)] font-mono">
      <div className="max-w-[1700px] mx-auto px-4 sm:px-8 py-3 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4">
        {/* Left Status & Stats */}
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-8 h-8 bg-black text-white flex items-center justify-center border border-black shadow-[2px_2px_0px_0px_#FF5500] shrink-0">
            <FolderKanban className="w-4 h-4 text-[#FF5500]" />
          </div>
          <div className="min-w-0">
            <p className="text-xs font-black uppercase text-black dark:text-white truncate">
              [BẢN NHÁP ĐANG MỞ] // {activeDraft.items.length} KHUNG HÌNH · {videoCount} VIDEOS
            </p>
            <p className="text-[10px] text-stone-500 truncate">
              {activeDraft.queryHistory.slice(-1)[0] ? `TRUY VẤN GẦN NHẤT: "${activeDraft.queryHistory.slice(-1)[0]}"` : 'ĐÁNH DẤU PHÂN CẢNH ĐỂ GOM VÀO DATASET'}
            </p>
          </div>
          <BalanceSpark items={activeDraft.items} />
        </div>

        {/* Center Chips */}
        <div className="flex items-center gap-1.5 min-w-0 overflow-x-auto py-1">
          {activeDraft.items.slice(-5).map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => removeItem(item.id)}
              title={`Xóa ${item.timestamp || item.videoId || 'moment'} khỏi bản nháp`}
              className="inline-flex items-center gap-1 shrink-0 px-2 py-1 bg-white dark:bg-stone-800 text-black dark:text-white border border-black hover:border-red-600 hover:bg-red-100 hover:text-red-900 text-[10px] font-bold uppercase transition-colors cursor-pointer shadow-[1px_1px_0px_0px_#000]"
            >
              <span>{item.timestamp || item.videoId}</span>
              <X className="w-2.5 h-2.5" />
            </button>
          ))}
          {activeDraft.items.length > 5 && (
            <span className="text-[10px] font-black text-stone-500 shrink-0">
              +{activeDraft.items.length - 5} KHÁC
            </span>
          )}
          {activeDraft.items.length > 1 && (
            <button
              type="button"
              onClick={() => activeDraft.items.forEach((item) => removeItem(item.id))}
              className="shrink-0 px-2 py-1 text-[10px] font-black uppercase text-red-600 hover:underline cursor-pointer"
            >
              XÓA HẾT
            </button>
          )}
        </div>

        {/* Right Actions */}
        <div className="flex items-center gap-2 shrink-0">
          <Link
            to="/datasets/draft"
            className="px-3.5 py-1.5 bg-white dark:bg-stone-800 hover:bg-black hover:text-white text-black dark:text-white text-[11px] font-black uppercase border-2 border-black shadow-[2px_2px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all flex items-center gap-1"
          >
            <span>MỞ BẢN NHÁP</span>
            <ArrowUpRight className="w-3 h-3" />
          </Link>

          <button
            type="button"
            onClick={handleDownloadNow}
            className="px-3.5 py-1.5 bg-[#00D084] hover:bg-black text-black hover:text-white text-[11px] font-black uppercase border-2 border-black shadow-[2px_2px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all flex items-center gap-1 cursor-pointer"
          >
            <Download className="w-3 h-3" />
            <span>XUẤT ZIP</span>
          </button>

          <button
            type="button"
            onClick={handleSave}
            className="px-4 py-1.5 bg-black hover:bg-[#FF5500] text-white hover:text-black text-[11px] font-black uppercase border-2 border-black shadow-[2px_2px_0px_0px_#FF5500] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all flex items-center gap-1 cursor-pointer"
          >
            <Save className="w-3 h-3" />
            <span>LƯU LẠI</span>
          </button>
        </div>
      </div>
    </div>
  )
}
