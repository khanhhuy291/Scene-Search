const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export const sendChatMessageApi = async ({ message, history = [], limit = 3 }) => {
  const response = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history, limit })
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload.detail || `Chat request failed (${response.status})`)
  }
  return payload
}
