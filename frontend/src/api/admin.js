const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

const parseResponse = async (response) => {
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = payload.detail
    throw new Error(typeof detail === 'string' ? detail : `Request failed (${response.status})`)
  }
  return payload
}

const authHeaders = (token) => ({
  Authorization: `Bearer ${token}`
})

export const getAdminTelemetry = async (token) => {
  const response = await fetch(`${API_BASE}/admin/telemetry`, {
    headers: authHeaders(token)
  })
  return parseResponse(response)
}

export const getEvalReport = async (token) => {
  const response = await fetch(`${API_BASE}/admin/eval`, {
    headers: authHeaders(token)
  })
  return parseResponse(response)
}

export const getEmbeddingModelStatus = async (token) => {
  const response = await fetch(`${API_BASE}/admin/embedding-model`, {
    headers: authHeaders(token)
  })
  return parseResponse(response)
}

const changeEmbeddingModelState = async (action, token) => {
  const response = await fetch(`${API_BASE}/admin/embedding-model/${action}`, {
    method: 'POST',
    headers: authHeaders(token)
  })
  return parseResponse(response)
}

export const loadEmbeddingModel = (token) => changeEmbeddingModelState('load', token)
export const unloadEmbeddingModel = (token) => changeEmbeddingModelState('unload', token)

export const getSystemTraces = async (token, { limit = 50, traceType } = {}) => {
  const params = new URLSearchParams()
  if (limit) params.set('limit', String(limit))
  if (traceType) params.set('trace_type', traceType)
  const query = params.toString() ? `?${params.toString()}` : ''
  const response = await fetch(`${API_BASE}/admin/traces${query}`, {
    headers: authHeaders(token)
  })
  return parseResponse(response)
}

export const getSystemTraceDetail = async (token, traceId) => {
  const response = await fetch(`${API_BASE}/admin/traces/${traceId}`, {
    headers: authHeaders(token)
  })
  return parseResponse(response)
}

export const clearSystemTraces = async (token) => {
  const response = await fetch(`${API_BASE}/admin/traces`, {
    method: 'DELETE',
    headers: authHeaders(token)
  })
  return parseResponse(response)
}
