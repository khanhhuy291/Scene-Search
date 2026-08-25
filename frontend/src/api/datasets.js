const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export const exportDatasetZip = async (payload, token) => {
  const response = await fetch(`${API_BASE}/datasets/export`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`
    },
    body: JSON.stringify(payload)
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    const detail = error.detail
    throw new Error(typeof detail === 'string' ? detail : `Export failed (${response.status})`)
  }
  return response.blob()
}
