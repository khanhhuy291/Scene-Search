const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

const parseResponse = async (response) => {
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || `Request failed (${response.status})`)
  return payload
}

const authHeaders = (token) => (token ? { Authorization: `Bearer ${token}` } : {})

export const listIngestionJobs = async ({ status, signal, token } = {}) => {
  const query = new URLSearchParams({ limit: '50' })
  if (status && status !== 'all') query.set('status', status)
  const response = await fetch(`${API_BASE}/tasks?${query}`, {
    signal,
    headers: authHeaders(token)
  })
  return parseResponse(response)
}

export const getIngestionJob = async (taskId, { signal, token } = {}) => {
  const response = await fetch(`${API_BASE}/tasks/${taskId}`, {
    signal,
    headers: authHeaders(token)
  })
  return parseResponse(response)
}

export const deleteVideo = async (videoId, token) => {
  const response = await fetch(`${API_BASE}/videos/${videoId}`, {
    method: 'DELETE',
    headers: authHeaders(token)
  })
  return parseResponse(response)
}

export const uploadVideo = async (file, onProgress, token) => {
  try {
    // Step 1: Request Presigned URL from Backend (bypasses Cloud Run 32MB GFE limit)
    const presignedRes = await fetch(`${API_BASE}/ingest/presigned-url`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders(token)
      },
      body: JSON.stringify({
        filename: file.name,
        content_type: file.type || 'video/mp4'
      })
    })

    if (presignedRes.ok) {
      const { upload_url, video_id, raw_key } = await presignedRes.json()

      // Step 2: Upload file directly to Cloud Storage (MinIO / GCS) via PUT with progress
      await new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest()
        xhr.open('PUT', upload_url)
        if (file.type) xhr.setRequestHeader('Content-Type', file.type)
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100))
        }
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) resolve()
          else reject(new Error(`Storage direct upload failed (${xhr.status})`))
        }
        xhr.onerror = () => reject(new Error('Network error during storage direct upload'))
        xhr.send(file)
      })

      // Step 3: Trigger background AI ingestion task on Backend
      const processRes = await fetch(`${API_BASE}/ingest/process`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders(token)
        },
        body: JSON.stringify({
          video_id,
          raw_key,
          filename: file.name
        })
      })

      return parseResponse(processRes)
    }
  } catch (err) {
    console.warn('Presigned direct upload encountered error, attempting fallback:', err)
  }

  // Fallback to multipart upload for small files or local mode
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest()
    const form = new FormData()
    form.append('file', file)
    request.open('POST', `${API_BASE}/ingest/upload`)
    request.responseType = 'json'
    if (token) request.setRequestHeader('Authorization', `Bearer ${token}`)
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100))
    }
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) resolve(request.response)
      else reject(new Error(request.response?.detail || `Upload failed (${request.status})`))
    }
    request.onerror = () => reject(new Error('Cannot reach the ingestion API'))
    request.send(form)
  })
}
