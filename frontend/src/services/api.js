/**
 * API Service for SceneSearch Backend endpoints
 */

const API_BASE = import.meta.env.VITE_API_URL || '/api/v1'

export async function searchScenes({ query, limit = 12, alphaVisual = 0.5, alphaText = 0.5 }) {
  if (!query || !query.trim()) {
    return { query: '', results: [], total: 0 }
  }

  const params = new URLSearchParams({
    query: query.trim(),
    limit: limit.toString(),
    alpha_visual: alphaVisual.toString(),
    alpha_text: alphaText.toString(),
  })

  const response = await fetch(`${API_BASE}/search?${params.toString()}`, {
    method: 'GET',
    headers: {
      'Accept': 'application/json',
    },
  })

  if (!response.ok) {
    let errorMsg = `Server error ${response.status}`
    try {
      const errObj = await response.json()
      if (errObj.detail) errorMsg = errObj.detail
    } catch (_) {}
    throw new Error(errorMsg)
  }

  return await response.json()
}

export function getVideoStreamUrl(videoId, timestampSec = 0) {
  if (!videoId) return ''
  const t = Math.max(0, Math.floor(timestampSec))
  return `${API_BASE}/videos/stream?video_id=${encodeURIComponent(videoId)}#t=${t}`
}

export async function triggerIngestion(videoPath) {
  const response = await fetch(`${API_BASE}/ingest`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: JSON.stringify({ video_path: videoPath }),
  })

  if (!response.ok) {
    let errorMsg = `Ingestion trigger failed with status ${response.status}`
    try {
      const errObj = await response.json()
      if (errObj.detail) errorMsg = errObj.detail
    } catch (_) {}
    throw new Error(errorMsg)
  }

  return await response.json()
}

export async function getTaskStatus(taskId) {
  const response = await fetch(`${API_BASE}/tasks/${taskId}`, {
    method: 'GET',
    headers: {
      'Accept': 'application/json',
    },
  })

  if (!response.ok) {
    throw new Error(`Task status fetch failed with status ${response.status}`)
  }

  return await response.json()
}

export async function getAdminStats() {
  const response = await fetch(`${API_BASE}/admin/stats`, {
    method: 'GET',
    headers: {
      'Accept': 'application/json',
    },
  })

  if (!response.ok) {
    throw new Error(`Admin stats fetch failed with status ${response.status}`)
  }

  return await response.json()
}
