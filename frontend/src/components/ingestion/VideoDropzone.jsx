import React, { useRef, useState } from 'react'
import { AlertCircle, Check, FileVideo, UploadCloud, X } from 'lucide-react'

const MAX_BYTES = 500 * 1024 * 1024
const ALLOWED = ['mp4', 'mov', 'mkv', 'webm']

const formatBytes = (bytes) => `${(bytes / 1024 / 1024).toFixed(1)} MB`

export const VideoDropzone = ({ onUpload, uploading, uploadProgress, disabled = false }) => {
  const input = useRef(null)
  const [file, setFile] = useState(null)
  const [error, setError] = useState('')
  const [dragging, setDragging] = useState(false)

  const select = (candidate) => {
    setError('')
    if (!candidate) return
    const extension = candidate.name.split('.').pop()?.toLowerCase()
    if (!ALLOWED.includes(extension)) return setError('USE MP4, MOV, MKV, OR WEBM FORMAT.')
    if (candidate.size > MAX_BYTES) return setError('MAXIMUM UPLOAD SIZE IS 500 MB.')
    if (candidate.size === 0) return setError('THE SELECTED FILE IS EMPTY.')
    setFile(candidate)
  }

  return (
    <section className="bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] p-6 lg:p-8 space-y-6 font-mono">
      <div className="flex items-start justify-between gap-4 border-b-2 border-black pb-4">
        <div>
          <div className="inline-flex items-center gap-1 px-2 py-0.5 bg-[#FF5500] text-black text-[10px] font-black uppercase border border-black shadow-[1px_1px_0px_0px_#000]">
            NEW INGESTION TASK
          </div>
          <h2 className="text-xl font-black uppercase text-black dark:text-white mt-1">
            INGEST RAW VIDEO TO NEURAL VECTOR SPACE
          </h2>
          <p className="text-xs text-stone-600 dark:text-stone-400 font-sans mt-0.5">
            Raw files are securely staged in S3. Celery extracts keyframe neural vectors into Qdrant.
          </p>
        </div>
        <div className="hidden sm:flex items-center gap-1.5 px-3 py-1 bg-[#F7F4EE] dark:bg-stone-800 border-2 border-black text-xs font-black text-black dark:text-white">
          <Check className="w-3.5 h-3.5 text-[#00D084]" /> MAX 500 MB
        </div>
      </div>

      <div
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragging(false)
          select(event.dataTransfer.files[0])
        }}
        onClick={() => !uploading && !disabled && input.current?.click()}
        className={`border-3 border-dashed p-8 text-center transition-all cursor-pointer ${
          dragging
            ? 'border-[#FF5500] bg-orange-50 dark:bg-stone-800'
            : 'border-black bg-[#F7F4EE] dark:bg-stone-900 hover:border-[#FF5500]'
        }`}
      >
        <input
          ref={input}
          type="file"
          accept="video/mp4,video/quicktime,video/x-matroska,video/webm"
          className="hidden"
          onChange={(event) => select(event.target.files[0])}
        />
        {file ? (
          <div className="flex items-center justify-between gap-4 p-3 bg-white dark:bg-stone-800 border-2 border-black shadow-[3px_3px_0px_0px_#000]">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-10 h-10 bg-black text-white flex items-center justify-center shrink-0">
                <FileVideo className="w-5 h-5 text-[#FF5500]" />
              </div>
              <div className="min-w-0 text-left">
                <p className="font-black text-xs text-black dark:text-white truncate">{file.name}</p>
                <p className="text-[10px] text-stone-500">{formatBytes(file.size)} · {file.type || 'video/mp4'}</p>
              </div>
            </div>
            {!uploading && (
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation()
                  setFile(null)
                }}
                className="p-1.5 bg-red-100 hover:bg-red-600 text-red-900 hover:text-white border border-black cursor-pointer"
                aria-label="Remove file"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        ) : (
          <div className="space-y-2">
            <UploadCloud className="w-10 h-10 mx-auto text-[#FF5500]" />
            <p className="text-sm font-black uppercase text-black dark:text-white">
              DROP RAW VIDEO HERE OR CLICK TO BROWSE
            </p>
            <p className="text-xs text-stone-500">SUPPORTED FORMATS: MP4, MOV, MKV, WEBM</p>
          </div>
        )}
      </div>

      {error && (
        <div className="p-3 bg-red-100 dark:bg-red-950/50 border-2 border-red-600 text-xs font-bold text-red-900 dark:text-red-300 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {uploading && (
        <div className="space-y-1.5">
          <div className="flex justify-between text-xs font-black">
            <span>UPLOADING TO S3 MINIO STORAGE...</span>
            <span>{uploadProgress}%</span>
          </div>
          <div className="h-3 bg-[#F7F4EE] dark:bg-stone-800 border-2 border-black overflow-hidden">
            <div
              className="h-full bg-[#FF5500] transition-all"
              style={{ width: `${uploadProgress}%` }}
            />
          </div>
        </div>
      )}

      <div className="flex justify-end pt-2">
        <button
          type="button"
          disabled={!file || uploading || disabled}
          onClick={() => onUpload(file)}
          className="px-6 py-3 bg-black hover:bg-[#FF5500] text-white hover:text-black text-xs font-black uppercase tracking-wider border-2 border-black shadow-[4px_4px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
        >
          {uploading
            ? 'PROCESSING UPLOAD…'
            : disabled
              ? 'LOAD QWEN MODEL BEFORE INGESTING'
              : 'UPLOAD & TRIGGER CELERY PIPELINE ↵'}
        </button>
      </div>
    </section>
  )
}
