/**
 * RLHF Feedback API Client
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

const parseResponse = async (response) => {
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload.detail || `Request failed (${response.status})`)
  }
  return payload
}

const getHeaders = (extra = {}) => {
  const token = localStorage.getItem('scenesearch_token')
  const headers = { 'Content-Type': 'application/json', ...extra }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  return headers
}

export async function submitRerankFeedback(payload) {
  const res = await fetch(`${API_BASE}/feedback/rerank`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(payload)
  })
  return parseResponse(res)
}

export async function fetchRLHFFeedback({ limit = 25, offset = 0, q = '' } = {}) {
  const params = new URLSearchParams({ limit, offset })
  if (q) params.set('q', q)

  const res = await fetch(`${API_BASE}/feedback/rerank?${params}`, {
    headers: getHeaders()
  })
  return parseResponse(res)
}

export async function fetchRLHFStats() {
  const res = await fetch(`${API_BASE}/feedback/stats`, {
    headers: getHeaders()
  })
  return parseResponse(res)
}

export async function downloadRLHFDataset(format = 'pairwise') {
  const token = localStorage.getItem('scenesearch_token')
  const headers = {}
  if (token) headers['Authorization'] = `Bearer ${token}`

  const response = await fetch(`${API_BASE}/feedback/export?format=${format}`, {
    headers
  })
  if (!response.ok) {
    throw new Error('Failed to export dataset')
  }

  const blob = await response.blob()
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.style.display = 'none'
  a.href = url
  a.download = `rlhf_reranker_${format}.jsonl`
  document.body.appendChild(a)
  a.click()
  window.URL.revokeObjectURL(url)
}
