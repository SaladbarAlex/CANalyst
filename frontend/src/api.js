const BASE = import.meta.env.VITE_API_BASE ?? ''

async function req(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* body was not JSON */
    }
    throw new Error(`${res.status}: ${detail}`)
  }
  return res.json()
}

const q = (explainer) => (explainer ? `?explainer=${encodeURIComponent(explainer)}` : '')

export const api = {
  health: () => req('/api/health'),
  explainers: () => req('/api/explainers'),
  benchmark: () => req('/api/benchmark'),
  analyzeSynthetic: (body) =>
    req('/api/analyze/synthetic', { method: 'POST', body: JSON.stringify(body) }),
  uploadLog: async (file, detector = 'rule') => {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`${BASE}/api/analyze/upload?detector=${detector}`, {
      method: 'POST',
      body: form,
    })
    if (!res.ok) throw new Error(`${res.status}: upload failed`)
    return res.json()
  },
  summary: (id) => req(`/api/analysis/${id}/summary`),
  timeline: (id) => req(`/api/analysis/${id}/timeline`),
  ids: (id) => req(`/api/analysis/${id}/ids`),
  idSeries: (id, canId) => req(`/api/analysis/${id}/ids/${canId}/series`),
  alerts: (id, explainer) => req(`/api/analysis/${id}/alerts${q(explainer)}`),
  alert: (id, alertId, explainer) => req(`/api/analysis/${id}/alerts/${alertId}${q(explainer)}`),
  explain: (id, alertId, body = {}) =>
    req(`/api/analysis/${id}/alerts/${alertId}/explain`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  explainAll: (id, body = {}) =>
    req(`/api/analysis/${id}/explain-all`, { method: 'POST', body: JSON.stringify(body) }),
  metrics: (id, explainer) => req(`/api/analysis/${id}/metrics${q(explainer)}`),
  ask: (id, question, explainer) =>
    req(`/api/analysis/${id}/ask`, { method: 'POST', body: JSON.stringify({ question, explainer }) }),
}

export const fmt = {
  sec: (v) => `${Number(v).toFixed(2)}s`,
  pct: (v) => (v === null || v === undefined ? 'n/a' : `${(v * 100).toFixed(1)}%`),
  num: (v, d = 2) => (v === null || v === undefined ? 'n/a' : Number(v).toFixed(d)),
}
