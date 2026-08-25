import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { exportDatasetZip } from '../api/datasets'
import { useAuth } from './AuthContext'

/** v2 drops reviewer approval — engineers download freely. */
const STORAGE_KEY = 'scenesearch_datasets_v2'

const emptyDraft = (user) => ({
  id: `ds_${Date.now().toString(36)}`,
  title: 'Untitled dataset',
  status: 'draft',
  queryHistory: [],
  items: [],
  createdBy: user?.id || null,
  createdByEmail: user?.email || null,
  createdByName: user?.name || null,
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
  modelVersion: ''
})

const migrateStatus = (status) => {
  if (status === 'submitted' || status === 'approved') return 'ready'
  if (status === 'exported') return 'exported'
  return 'draft'
}

const loadStore = () => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      return {
        datasets: (parsed.datasets || []).map((d) => ({
          ...d,
          status: migrateStatus(d.status)
        })),
        activeDraftId: parsed.activeDraftId || null
      }
    }
    // One-time lift from v1 if present
    const legacy = localStorage.getItem('scenesearch_datasets_v1')
    if (legacy) {
      const parsed = JSON.parse(legacy)
      return {
        datasets: (parsed.datasets || []).map((d) => ({
          ...d,
          status: migrateStatus(d.status),
          approvedBy: undefined,
          approvedByEmail: undefined,
          approvedAt: undefined,
          submittedAt: undefined
        })),
        activeDraftId: parsed.activeDraftId || null
      }
    }
    return { datasets: [], activeDraftId: null }
  } catch {
    return { datasets: [], activeDraftId: null }
  }
}

const triggerBrowserDownload = (blob, filename) => {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

const DatasetContext = createContext(null)

export const DatasetProvider = ({ children }) => {
  const { user, token } = useAuth()
  const [datasets, setDatasets] = useState([])
  const [activeDraftId, setActiveDraftId] = useState(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const stored = loadStore()
    setDatasets(stored.datasets || [])
    setActiveDraftId(stored.activeDraftId || null)
    setReady(true)
  }, [])

  useEffect(() => {
    if (!ready) return
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ datasets, activeDraftId }))
  }, [datasets, activeDraftId, ready])

  const activeDraft = useMemo(() => {
    if (!activeDraftId) return null
    return datasets.find((d) => d.id === activeDraftId && d.status === 'draft') || null
  }, [datasets, activeDraftId])

  const ensureDraft = useCallback(() => {
    if (!user || user.role !== 'engineer') {
      throw new Error('Sign in as an engineer to build a dataset.')
    }
    const existing = datasets.find((d) => d.status === 'draft' && d.createdBy === user.id)
    if (existing) {
      setActiveDraftId(existing.id)
      return existing
    }
    const draft = emptyDraft(user)
    setDatasets((prev) => [draft, ...prev])
    setActiveDraftId(draft.id)
    return draft
  }, [datasets, user])

  const sceneToItem = (scene, meta = {}) => ({
    id: scene.id,
    videoId: scene.videoId,
    description: scene.description,
    timestamp: scene.timestamp,
    startSeconds: scene.startSeconds,
    endSeconds: scene.endSeconds,
    thumbnail: scene.thumbnail,
    previewUrl: scene.previewUrl,
    videoUrl: scene.previewUrl || scene.videoUrl || null,
    keyframesMatched: scene.keyframesMatched,
    confirmed: scene.confirmed || [],
    denied: scene.denied || [],
    weather: scene.weather,
    timeOfDay: scene.timeOfDay,
    objects: scene.objects || [],
    query: meta.query || '',
    requiredConcepts: meta.requiredConcepts || [],
    excludedConcepts: meta.excludedConcepts || [],
    addedAt: new Date().toISOString()
  })

  const addItem = useCallback(
    (scene, meta = {}) => {
      if (!user || user.role !== 'engineer') {
        throw new Error('Only engineers can mark moments relevant.')
      }
      const draft = ensureDraft()
      if (draft.items.some((item) => item.id === scene.id)) return { draft, added: 0 }

      const item = sceneToItem(scene, meta)

      setDatasets((prev) =>
        prev.map((d) => {
          if (d.id !== draft.id) return d
          const queryHistory =
            meta.query && !d.queryHistory.includes(meta.query)
              ? [...d.queryHistory, meta.query]
              : d.queryHistory
          return {
            ...d,
            items: [...d.items, item],
            queryHistory,
            modelVersion: meta.modelVersion || d.modelVersion,
            updatedAt: new Date().toISOString()
          }
        })
      )
      return { draft, added: 1 }
    },
    [ensureDraft, user]
  )

  /** Add every scene not already in the active draft (one state update). */
  const addItems = useCallback(
    (scenes = [], meta = {}) => {
      if (!user || user.role !== 'engineer') {
        throw new Error('Only engineers can mark moments relevant.')
      }
      if (!scenes.length) return { added: 0, skipped: 0 }

      const draft = ensureDraft()
      const existingIds = new Set(draft.items.map((item) => item.id))
      const newcomers = scenes.filter((scene) => scene?.id && !existingIds.has(scene.id))
      const skipped = scenes.length - newcomers.length

      if (newcomers.length === 0) {
        return { draft, added: 0, skipped }
      }

      const newItems = newcomers.map((scene) => sceneToItem(scene, meta))

      setDatasets((prev) =>
        prev.map((d) => {
          if (d.id !== draft.id) return d
          const queryHistory =
            meta.query && !d.queryHistory.includes(meta.query)
              ? [...d.queryHistory, meta.query]
              : d.queryHistory
          return {
            ...d,
            items: [...d.items, ...newItems],
            queryHistory,
            modelVersion: meta.modelVersion || d.modelVersion,
            updatedAt: new Date().toISOString()
          }
        })
      )
      return { draft, added: newcomers.length, skipped }
    },
    [ensureDraft, user]
  )

  const removeItem = useCallback(
    (itemId, datasetId = null) => {
      const targetId = datasetId || activeDraftId
      setDatasets((prev) =>
        prev.map((d) => {
          if (d.id !== targetId) return d
          if (d.status !== 'draft' && d.status !== 'ready') return d
          return {
            ...d,
            items: d.items.filter((item) => item.id !== itemId),
            updatedAt: new Date().toISOString()
          }
        })
      )
    },
    [activeDraftId]
  )

  /** Finalize the open draft so it appears in the download picker. Still downloadable while draft. */
  const saveDataset = useCallback(() => {
    if (!user || user.role !== 'engineer') {
      throw new Error('Only engineers can save a dataset.')
    }
    const draft = datasets.find((d) => d.id === activeDraftId && d.status === 'draft')
    if (!draft) throw new Error('No active draft to save.')
    if (draft.items.length === 0) throw new Error('Mark at least one moment before saving.')

    setDatasets((prev) =>
      prev.map((d) =>
        d.id === draft.id
          ? {
              ...d,
              status: 'ready',
              updatedAt: new Date().toISOString(),
              title: d.queryHistory[0]
                ? `Dataset · ${d.queryHistory[0].slice(0, 48)}`
                : d.title
            }
          : d
      )
    )
    setActiveDraftId(null)
    return draft.id
  }, [activeDraftId, datasets, user])

  /** @deprecated alias */
  const submitDraft = saveDataset

  const getDataset = useCallback(
    (datasetId) => datasets.find((d) => d.id === datasetId) || null,
    [datasets]
  )

  const assertCanDownload = useCallback(
    (dataset) => {
      if (!dataset) throw new Error('Choose a dataset first.')
      if (!user) throw new Error('Sign in to download.')
      if (user.role === 'admin') return
      if (dataset.createdBy !== user.id) {
        throw new Error('You can only download datasets you built.')
      }
      if (!dataset.items?.length) {
        throw new Error('This dataset has no moments yet.')
      }
    },
    [user]
  )

  const buildManifest = useCallback((dataset) => {
    const videos = [
      ...new Map(
        dataset.items.map((item) => [
          item.videoId,
          {
            video_id: item.videoId,
            video_url: item.videoUrl || item.previewUrl || null,
            moment_count: dataset.items.filter((i) => i.videoId === item.videoId).length
          }
        ])
      ).values()
    ]

    const header = {
      type: 'provenance',
      dataset_id: dataset.id,
      title: dataset.title,
      queries: dataset.queryHistory,
      model_version: dataset.modelVersion,
      created_by: dataset.createdByEmail,
      item_count: dataset.items.length,
      video_count: videos.length,
      contents: ['keyframes', 'videos'],
      split_policy: 'by_video',
      exported_at: new Date().toISOString()
    }

    const lines = [JSON.stringify(header)]
    for (const video of videos) {
      lines.push(JSON.stringify({ type: 'video', ...video }))
    }
    for (const item of dataset.items) {
      lines.push(
        JSON.stringify({
          type: 'keyframe',
          scene_id: item.id,
          video_id: item.videoId,
          ts_start_s: item.startSeconds,
          ts_end_s: item.endSeconds,
          thumbnail_url: item.thumbnail,
          preview_url: item.previewUrl,
          video_url: item.videoUrl || item.previewUrl,
          caption: item.description,
          query: item.query,
          required_concepts: item.requiredConcepts,
          excluded_concepts: item.excludedConcepts,
          weather: item.weather,
          time_of_day: item.timeOfDay,
          objects: item.objects
        })
      )
    }
    return lines.join('\n') + '\n'
  }, [])

  const markExported = useCallback((datasetId) => {
    setDatasets((prev) =>
      prev.map((d) =>
        d.id === datasetId
          ? {
              ...d,
              status: d.status === 'draft' ? 'ready' : d.status === 'ready' ? 'exported' : d.status,
              updatedAt: new Date().toISOString(),
              ...(d.status === 'draft'
                ? {
                    title: d.queryHistory[0]
                      ? `Dataset · ${d.queryHistory[0].slice(0, 48)}`
                      : d.title
                  }
                : {})
            }
          : d
      )
    )
  }, [])

  /** Download the JSONL manifest (keyframe + video metadata / URLs). */
  const downloadManifest = useCallback(
    (datasetId) => {
      const dataset = getDataset(datasetId)
      assertCanDownload(dataset)
      const text = buildManifest(dataset)
      triggerBrowserDownload(
        new Blob([text], { type: 'application/x-ndjson' }),
        `${dataset.id}-manifest.jsonl`
      )
      markExported(datasetId)
      return text
    },
    [assertCanDownload, buildManifest, getDataset, markExported]
  )

  /**
   * Download unique source videos + thumbnails for the selection via the live media store.
   */
  const downloadVideos = useCallback(
    async (datasetId) => {
      const dataset = getDataset(datasetId)
      assertCanDownload(dataset)
      if (!token) throw new Error('Sign in to download.')

      const blob = await exportDatasetZip(
        {
          dataset_id: dataset.id,
          title: dataset.title,
          queries: dataset.queryHistory,
          model_version: dataset.modelVersion || null,
          items: dataset.items.map((item) => ({
            point_id: item.id,
            video_id: item.videoId,
            ts_start_s: item.startSeconds,
            ts_end_s: item.endSeconds,
            caption: item.description,
            query: item.query,
            required_concepts: item.requiredConcepts || [],
            excluded_concepts: item.excludedConcepts || [],
            weather: item.weather,
            time_of_day: item.timeOfDay,
            objects: item.objects || []
          }))
        },
        token
      )
      triggerBrowserDownload(blob, `${dataset.id}.zip`)
      markExported(datasetId)
      return {
        videoCount: new Set(dataset.items.map((item) => item.videoId)).size,
        downloaded: dataset.items.length
      }
    },
    [assertCanDownload, getDataset, markExported, token]
  )

  /** Manifest JSONL locally, then the zip of clips from the API. */
  const downloadBundle = useCallback(
    async (datasetId) => {
      downloadManifest(datasetId)
      return downloadVideos(datasetId)
    },
    [downloadManifest, downloadVideos]
  )

  /** Back-compat name used by older UI. */
  const exportJsonl = downloadManifest
  const buildJsonl = useCallback(
    (dataset) => {
      assertCanDownload(dataset)
      return buildManifest(dataset)
    },
    [assertCanDownload, buildManifest]
  )

  const startNewDraft = useCallback(() => {
    if (!user || user.role !== 'engineer') {
      throw new Error('Only engineers can start a dataset draft.')
    }
    const draft = emptyDraft(user)
    setDatasets((prev) => [draft, ...prev])
    setActiveDraftId(draft.id)
    return draft
  }, [user])

  const reopenAsDraft = useCallback(
    (datasetId) => {
      if (!user || user.role !== 'engineer') {
        throw new Error('Only engineers can edit a dataset.')
      }
      setDatasets((prev) =>
        prev.map((d) =>
          d.id === datasetId && d.createdBy === user.id
            ? { ...d, status: 'draft', updatedAt: new Date().toISOString() }
            : d
        )
      )
      setActiveDraftId(datasetId)
    },
    [user]
  )

  const isSelected = useCallback(
    (sceneId) => Boolean(activeDraft?.items.some((item) => item.id === sceneId)),
    [activeDraft]
  )

  const myDatasets = useMemo(() => {
    if (!user) return []
    if (user.role === 'admin') return datasets
    return datasets.filter((d) => d.createdBy === user.id)
  }, [datasets, user])

  /** Any of the engineer’s sets that have at least one moment. */
  const downloadableDatasets = useMemo(
    () => myDatasets.filter((d) => (d.items?.length || 0) > 0),
    [myDatasets]
  )

  return (
    <DatasetContext.Provider
      value={{
        ready,
        datasets,
        activeDraft,
        activeDraftId,
        myDatasets,
        downloadableDatasets,
        ensureDraft,
        startNewDraft,
        reopenAsDraft,
        addItem,
        addItems,
        removeItem,
        saveDataset,
        submitDraft,
        downloadManifest,
        downloadVideos,
        downloadBundle,
        exportJsonl,
        buildJsonl,
        isSelected
      }}
    >
      {children}
    </DatasetContext.Provider>
  )
}

export const useDataset = () => {
  const ctx = useContext(DatasetContext)
  if (!ctx) throw new Error('useDataset must be used within a DatasetProvider')
  return ctx
}
