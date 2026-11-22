const BASE = import.meta.env.VITE_API_BASE ?? ''

async function req(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: options.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body)
    } catch { /* body was not JSON */ }
    throw new Error(`${res.status}: ${detail}`)
  }
  return res.json()
}

const q = (explainer) => (explainer ? `?explainer=${encodeURIComponent(explainer)}` : '')

export const api = {
  benchmarkDetection: () => req('/api/benchmark/detection'),
  benchmarkExplainers: () => req('/api/benchmark/explainers'),
  benchmarkCompare: (set, a, b) =>
    req(`/api/benchmark/explainers/${set}/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`),
  benchmarkPacketsUrl: (set) => `${BASE}/api/benchmark/explainers/${set}/packets`,
  benchmarkSubmit: (set, name, file) => {
    const form = new FormData()
    form.append('name', name)
    form.append('file', file)
    return req(`/api/benchmark/explainers/${set}/submit`, { method: 'POST', body: form })
  },
  health: () => req('/api/health'),
  explainers: () => req('/api/explainers'),
  benchmark: () => req('/api/benchmark'),
  detectionBenchmark: () => req('/api/benchmark/detectors'),
  analyzeRealExample: () => req('/api/analyze/real-example', { method: 'POST' }),
  analyzeSynthetic: (body) =>
    req('/api/analyze/synthetic', { method: 'POST', body: JSON.stringify(body) }),
  uploadLog: (file, params, { baselineFile, metadataFile, baselineSeconds } = {}) => {
    const form = new FormData()
    form.append('file', file)
    if (baselineFile) form.append('baseline_file', baselineFile)
    if (metadataFile) form.append('metadata_file', metadataFile)
    const query = new URLSearchParams(Object.fromEntries(
      ['detector', 'window_s', 'stride_s', 'threshold'].map((key) => [key, params[key]])))
    if (baselineSeconds && !baselineFile) query.set('baseline_s', baselineSeconds)
    return req(`/api/analyze/upload?${query}`, { method: 'POST', body: form })
  },
  summary: (id) => req(`/api/analysis/${id}/summary`),
  timeline: (id) => req(`/api/analysis/${id}/timeline`),
  ids: (id) => req(`/api/analysis/${id}/ids`),
  idSeries: (id, canId, signal) => req(`/api/analysis/${id}/ids/${canId}/series`, { signal }),
  alerts: (id, explainer, signal) => req(`/api/analysis/${id}/alerts${q(explainer)}`, { signal }),
  alert: (id, alertId, explainer, signal) => req(`/api/analysis/${id}/alerts/${alertId}${q(explainer)}`, { signal }),
  explain: (id, alertId, body = {}) =>
    req(`/api/analysis/${id}/alerts/${alertId}/explain`, {
      method: 'POST', body: JSON.stringify(body),
    }),
  metrics: (id, explainer) => req(`/api/analysis/${id}/metrics${q(explainer)}`),
  ask: (id, question, explainer, signal) =>
    req(`/api/analysis/${id}/ask`, { method: 'POST', body: JSON.stringify({ question, explainer }), signal }),
}

export const fmt = {
  sec: (v) => `${Number(v).toFixed(2)}s`,
  pct: (v) => (v === null || v === undefined ? 'n/a' : `${(v * 100).toFixed(1)}%`),
  num: (v, d = 2) => (v === null || v === undefined ? 'n/a' : Number(v).toFixed(d)),
}
