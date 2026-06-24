const BASE = 'http://127.0.0.1:8000'

async function json(res) {
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status}: ${text}`)
  }
  return res.json()
}

export async function uploadDrawing(file) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/drawings`, { method: 'POST', body: form })
  return json(res)
}

export async function createView(drawingId, body) {
  const res = await fetch(`${BASE}/drawings/${drawingId}/views`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json(res)
}

export async function listViews(drawingId) {
  const res = await fetch(`${BASE}/drawings/${drawingId}/views`)
  return json(res)
}

export async function getView(viewId) {
  const res = await fetch(`${BASE}/views/${viewId}`)
  return json(res)
}

export function cropUrl(viewId) {
  return `${BASE}/views/${viewId}/crop`
}

export async function extractView(viewId) {
  const res = await fetch(`${BASE}/views/${viewId}/extract`, { method: 'POST' })
  return json(res)
}
