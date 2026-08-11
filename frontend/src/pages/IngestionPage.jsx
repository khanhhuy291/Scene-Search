import React, { useState } from 'react'
import { VideoDropzone } from '../components/ingestion/VideoDropzone'
import { TaskProgressTracker } from '../components/ingestion/TaskProgressTracker'
import { Video, CheckCircle2 } from 'lucide-react'

export const IngestionPage = () => {
  const [activeTask, setActiveTask] = useState(null)
  const [completedTasks, setCompletedTasks] = useState([
    {
      id: 'task_88201',
      filename: 'cyberpunk_neon_city_4k.mp4',
      size: '248.5 MB',
      scenes: 42,
      time: '10 mins ago'
    },
    {
      id: 'task_88200',
      filename: 'developer_workspace_vlog.mp4',
      size: '182.1 MB',
      scenes: 28,
      time: '45 mins ago'
    }
  ])

  const handleStartIngestion = (taskPayload) => {
    setActiveTask(taskPayload)
  }

  const handleTaskComplete = () => {
    if (activeTask) {
      setCompletedTasks((prev) => [
        {
          id: activeTask.id,
          filename: activeTask.filename,
          size: activeTask.size,
          scenes: 42,
          time: 'Just now'
        },
        ...prev
      ])
    }
  }

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-12 space-y-10 animate-fadeIn pb-24">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-stone-200 dark:border-[#403933] pb-6">
        <div className="pl-3 orange-accent-line">
          <div className="flex items-center gap-2 mb-1">
            <span className="px-3 py-0.5 rounded-full bg-stone-100 dark:bg-[#315c49]/12 text-orange-700 dark:text-[#a8c0b0] border border-stone-200 dark:border-[#315c49]/35 text-[10px] font-sans font-bold uppercase tracking-widest">
              ASYNC CELERY QUEUE ACTIVE
            </span>
          </div>
          <h1 className="text-4xl sm:text-5xl font-serif font-normal text-stone-950 dark:text-[#f3ece4] uppercase tracking-tighter ">
            VIDEO STREAM INGESTION
          </h1>
          <p className="text-stone-500 dark:text-[#a99d92] text-xs font-sans tracking-widest uppercase mt-1">
            Upload MP4 video files for keyframe extraction & Qdrant vector indexing.
          </p>
        </div>
      </div>

      <VideoDropzone onStartIngestion={handleStartIngestion} />

      {activeTask && (
        <TaskProgressTracker activeTask={activeTask} onComplete={handleTaskComplete} />
      )}

      {/* History List */}
      <div className="bg-white dark:bg-[#25211e]/95 p-8 rounded-3xl border border-stone-200 dark:border-[#403933] shadow-2xs space-y-4">
        <div className="flex items-center justify-between border-b border-stone-100 dark:border-[#403933] pb-4">
          <h3 className="text-xl font-serif font-normal text-stone-950 dark:text-[#f3ece4] uppercase tracking-tight flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-emerald-700 dark:text-[#789b86]" />
            RECENTLY INDEXED VIDEOS
          </h3>
          <span className="text-xs font-mono text-stone-500 dark:text-[#a99d92]">{completedTasks.length} Videos Ingested</span>
        </div>

        <div className="divide-y divide-stone-100 dark:divide-[#403933]">
          {completedTasks.map((item) => (
            <div key={item.id} className="py-3 flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-full bg-stone-100 dark:bg-[#332e2a] border border-stone-200 dark:border-[#514841] text-orange-700 dark:text-[#789b86]">
                  <Video className="w-4 h-4" />
                </div>
                <div>
                  <div className="text-sm font-bold text-stone-950 dark:text-[#ded3c8]">{item.filename}</div>
                  <div className="text-xs text-stone-500 dark:text-[#a99d92] font-mono">
                    {item.size} • {item.scenes} Scenes • {item.time}
                  </div>
                </div>
              </div>

              <span className="px-3 py-1 rounded-full bg-stone-100 dark:bg-[#315c49]/18 border border-stone-200 dark:border-[#456f5b]/45 text-orange-700 dark:text-[#789b86] text-xs font-mono font-bold uppercase">
                QDRANT INDEXED
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
