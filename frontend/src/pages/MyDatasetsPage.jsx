import React, { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Download, FileStack, Film, FileJson, Package, FolderKanban } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useDataset } from '../context/DatasetContext'
import { useToast } from '../context/ToastContext'

const STATUS_TONE = {
  draft: 'bg-[#FFD700] text-black border-black',
  ready: 'bg-[#00D084] text-black border-black',
  exported: 'bg-[#7C3AED] text-white border-black'
}

export const MyDatasetsPage = () => {
  const { user, isEngineer } = useAuth()
  const {
    myDatasets,
    downloadableDatasets,
    downloadManifest,
    downloadVideos,
    downloadBundle,
    reopenAsDraft
  } = useDataset()
  const { addToast } = useToast()
  const navigate = useNavigate()
  const [selectedId, setSelectedId] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (downloadableDatasets.length === 0) {
      setSelectedId('')
      return
    }
    if (!downloadableDatasets.some((d) => d.id === selectedId)) {
      setSelectedId(downloadableDatasets[0].id)
    }
  }, [downloadableDatasets, selectedId])

  const selected = useMemo(
    () => downloadableDatasets.find((d) => d.id === selectedId) || null,
    [downloadableDatasets, selectedId]
  )

  const videoCount = selected
    ? new Set(selected.items.map((i) => i.videoId)).size
    : 0

  const runDownload = async (kind) => {
    if (!selectedId) {
      addToast('Choose a dataset to download', 'info')
      return
    }
    setBusy(true)
    try {
      if (kind === 'manifest') {
        downloadManifest(selectedId)
        addToast('Downloaded keyframe + video manifest (JSONL)', 'success')
      } else if (kind === 'videos') {
        const result = await downloadVideos(selectedId)
        addToast(`Downloaded zip of ${result.videoCount} selected video(s)`, 'success')
      } else {
        await downloadBundle(selectedId)
        addToast('Downloaded manifest + videos', 'success')
      }
    } catch (err) {
      addToast(err.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-[1700px] mx-auto px-4 sm:px-8 py-10 space-y-8 animate-fadeIn pb-32 font-sans">
      {/* Page Header */}
      <div className="border-b-2 border-black pb-6 space-y-1">
        <div className="inline-flex items-center gap-2 px-2.5 py-0.5 bg-white dark:bg-stone-900 border border-black font-mono text-[10px] font-black uppercase text-black dark:text-white shadow-[1.5px_1.5px_0px_0px_#000]">
          <FolderKanban className="w-3 h-3 text-[#FF5500]" />
          <span>KHO LƯU TRỮ DATASET // TRUNG TÂM XUẤT DỮ LIỆU</span>
        </div>
        <h1 className="text-3xl sm:text-4xl font-black text-black dark:text-white uppercase tracking-tight">
          TẢI VỀ & XUẤT DATASET
        </h1>
        <p className="text-xs font-mono text-stone-600 dark:text-stone-400">
          Chọn một dataset đã tạo trong không gian làm việc của bạn để tải các gói video chất lượng cao và file manifest trực tiếp.
        </p>
      </div>

      {/* Choose & Download Card */}
      <div className="bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] p-6 sm:p-8 space-y-6">
        <div className="flex items-center justify-between pb-4 border-b-2 border-black">
          <div className="flex items-center gap-2">
            <Package className="w-4 h-4 text-[#FF5500]" />
            <h2 className="font-mono text-xs font-black uppercase tracking-wider text-black dark:text-white">
              CHỌN DATASET // XUẤT NHANH
            </h2>
          </div>
          <span className="font-mono text-[10px] font-bold uppercase text-[#FF5500]">
            KHÔNG CẦN PHÊ DUYỆT
          </span>
        </div>

        {downloadableDatasets.length === 0 ? (
          <div className="p-6 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black font-mono text-xs text-stone-600 dark:text-stone-400 text-center space-y-2">
            <p className="font-bold text-black dark:text-white uppercase">
              [CHƯA CÓ DATASET NÀO ĐỂ TẢI]
            </p>
            <p className="font-sans">
              Thực hiện tìm kiếm, gắn nhãn các phân cảnh vào bản nháp, hoặc mở{' '}
              <Link to="/datasets/draft" className="font-bold underline text-[#FF5500]">
                Trang Bản Nháp Dataset
              </Link>
              .
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            <div className="space-y-2 font-mono">
              <label
                htmlFor="dataset-download-select"
                className="block text-xs font-black uppercase text-black dark:text-white"
              >
                DATASET ĐANG CHỌN:
              </label>
              <select
                id="dataset-download-select"
                value={selectedId}
                onChange={(e) => setSelectedId(e.target.value)}
                className="w-full bg-[#F7F4EE] dark:bg-stone-900 text-black dark:text-white font-mono text-sm font-bold p-3.5 border-2 border-black shadow-[3px_3px_0px_0px_#000] outline-none"
              >
                {downloadableDatasets.map((ds) => (
                  <option key={ds.id} value={ds.id}>
                    {ds.title} · {ds.items.length} KHUNG HÌNH ·{' '}
                    {new Set(ds.items.map((i) => i.videoId)).size} VIDEOS · [{ds.status.toUpperCase()}]
                  </option>
                ))}
              </select>

              {selected && (
                <div className="flex flex-wrap items-center gap-2 pt-1 text-[11px] font-mono text-stone-600 dark:text-stone-400">
                  <span className="px-2 py-0.5 bg-black text-white font-bold">
                    {selected.items.length} KHUNG HÌNH
                  </span>
                  <span className="px-2 py-0.5 bg-[#FF5500] text-black font-bold">
                    {videoCount} TẬP TIN VIDEO
                  </span>
                </div>
              )}
            </div>

            {/* Export Buttons */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <button
                type="button"
                disabled={busy || !selectedId}
                onClick={() => runDownload('manifest')}
                className="p-4 bg-[#F7F4EE] dark:bg-stone-900 hover:bg-black hover:text-white border-2 border-black shadow-[4px_4px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all text-left space-y-1.5 cursor-pointer disabled:opacity-40 font-mono"
              >
                <div className="flex items-center justify-between">
                  <FileJson className="w-5 h-5 text-[#FF5500]" />
                  <span className="text-[10px] font-black uppercase text-stone-500">.JSONL</span>
                </div>
                <div className="text-xs font-black uppercase">TẢI MANIFEST</div>
                <div className="text-[10px] text-stone-500 font-sans">
                  File chú thích, timestamps và metadata khung hình
                </div>
              </button>

              <button
                type="button"
                disabled={busy || !selectedId}
                onClick={() => runDownload('videos')}
                className="p-4 bg-[#F7F4EE] dark:bg-stone-900 hover:bg-black hover:text-white border-2 border-black shadow-[4px_4px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all text-left space-y-1.5 cursor-pointer disabled:opacity-40 font-mono"
              >
                <div className="flex items-center justify-between">
                  <Film className="w-5 h-5 text-[#00D084]" />
                  <span className="text-[10px] font-black uppercase text-stone-500">.ZIP</span>
                </div>
                <div className="text-xs font-black uppercase">TẢI VIDEO CLIPS</div>
                <div className="text-[10px] text-stone-500 font-sans">
                  Gói nén ZIP các video và ảnh khung hình trích xuất
                </div>
              </button>

              <button
                type="button"
                disabled={busy || !selectedId}
                onClick={() => runDownload('bundle')}
                className="p-4 bg-[#00D084] hover:bg-black text-black hover:text-white border-2 border-black shadow-[4px_4px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all text-left space-y-1.5 cursor-pointer disabled:opacity-40 font-mono"
              >
                <div className="flex items-center justify-between">
                  <Package className="w-5 h-5 text-black hover:text-white" />
                  <span className="text-[10px] font-black uppercase text-black/70">TRỌN GÓI</span>
                </div>
                <div className="text-xs font-black uppercase">TẢI TRỌN BỘ BUNDLE</div>
                <div className="text-[10px] font-sans opacity-80">
                  Manifest JSONL + Toàn bộ Video và Ảnh Keyframes
                </div>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Dataset History Cards */}
      <div className="space-y-4 font-mono">
        <div className="flex items-center justify-between pb-2 border-b-2 border-black">
          <h2 className="text-xs font-black uppercase text-black dark:text-white">
            SAVED DATASETS REPOSITORY ({myDatasets.length})
          </h2>
          <span className="text-[11px] text-stone-500 font-bold">
            USER: {user?.email}
          </span>
        </div>

        {myDatasets.length === 0 ? (
          <div className="p-8 bg-white dark:bg-[#1C1A17] border-2 border-black shadow-[4px_4px_0px_0px_#000] text-center space-y-3">
            <FileStack className="w-8 h-8 mx-auto text-stone-400" />
            <p className="text-xs font-bold uppercase text-stone-600 dark:text-stone-400">
              [NO SAVED DATASETS IN LOCAL STORAGE]
            </p>
            {isEngineer && (
              <Link
                to="/search"
                className="inline-flex px-5 py-2 bg-black text-white hover:bg-[#FF5500] hover:text-black text-xs font-black uppercase border border-black transition-all shadow-[2px_2px_0px_0px_#000]"
              >
                START SEARCHING NOW
              </Link>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {myDatasets.map((ds) => (
              <div
                key={ds.id}
                className="bg-white dark:bg-[#1C1A17] border-2 border-black shadow-[4px_4px_0px_0px_#000] hover:shadow-[6px_6px_0px_0px_#FF5500] p-5 space-y-4 transition-all flex flex-col justify-between"
              >
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs font-black text-black dark:text-white truncate">
                      {ds.title || ds.id}
                    </span>
                    <span
                      className={`px-2 py-0.5 font-mono text-[9px] font-black uppercase border ${
                        STATUS_TONE[ds.status] || 'bg-stone-100 text-black border-black'
                      }`}
                    >
                      {ds.status}
                    </span>
                  </div>

                  <p className="text-xs font-mono text-stone-500">
                    {ds.items.length} KEYFRAMES • {new Set(ds.items.map((i) => i.videoId)).size} VIDEOS
                  </p>
                </div>

                <div className="pt-3 border-t border-black flex items-center justify-between">
                  <button
                    type="button"
                    onClick={() => {
                      reopenAsDraft(ds.id)
                      navigate('/datasets/draft')
                      addToast(`Reopened ${ds.title} as active draft`, 'info')
                    }}
                    className="px-3 py-1.5 bg-[#F7F4EE] hover:bg-black hover:text-white text-black font-mono text-xs font-bold uppercase border border-black shadow-[2px_2px_0px_0px_#000] transition-all cursor-pointer"
                  >
                    EDIT DRAFT
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setSelectedId(ds.id)
                      runDownload('bundle')
                    }}
                    className="px-3 py-1.5 bg-black hover:bg-[#FF5500] text-white hover:text-black font-mono text-xs font-black uppercase border border-black shadow-[2px_2px_0px_0px_#FF5500] transition-all flex items-center gap-1 cursor-pointer"
                  >
                    <Download className="w-3 h-3" /> EXPORT
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
