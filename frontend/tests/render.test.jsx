import test from 'node:test'
import assert from 'node:assert/strict'
import { renderToStaticMarkup } from 'react-dom/server'
import { loadAnalysisViews } from '../src/analysisLoad'
import IdView from '../src/components/IdView'
import { runExplanationQueue } from '../src/explanationQueue'
import { api } from '../src/api'
import MetricsPanel from '../src/components/MetricsPanel'
import ExplanationPanel from '../src/components/ExplanationPanel'
import DetectionBenchmarkPanel from '../src/components/DetectionBenchmarkPanel'
import ValidationWarnings from '../src/components/ValidationWarnings'
import { AlertReasoning, Prediction, predictionType } from '../src/components/BenchmarkPanel'
import TimelineChart from '../src/components/TimelineChart'
import AlertList from '../src/components/AlertList'
import { DetectionSection, ExplainerSection, SubmitSection, runLabel } from '../src/components/EvaluationBenchmarkPanel'

const alert = { alert_id: 0, start: 1, end: 2, score: 0.8, true_type: 'dos',
  frame_count: 100, reasons: ['High rate'], components: { rate: 0.8 }, ids_involved: ['0x000'] }
const report = { detection: { labeled: false }, classification: { accuracy: null },
  grounding: { grounded_rate: null }, explained_alerts: 0, total_alerts: 2 }

test('frozen benchmark views handle missing intervals and explain held-out coverage', () => {
  const missing = { value: null, lo: null, hi: null }
  const html = renderToStaticMarkup(<DetectionSection data={{ datasets: [{ dataset: 'road',
    split: { evaluation: { windows: 12, attack_windows: 0 } }, references: { pooled: {
      reference_captures: ['normal'], reference_seconds: 30,
      detectors: { iforest: { precision: missing, recall: missing, f1: missing, fpr: missing, auroc: null } },
    } },
  }] }} />)
  assert.match(html, /Interval unavailable/)
  assert.match(html, /IsolationForest/)
  assert.doesNotMatch(html, /NaN/)
  const explanation = renderToStaticMarkup(<ExplainerSection data={{ heldout: {
    alerts: 77, datasets: ['hcrl', 'road'], runs: {}, pairs: {},
  } }} />)
  assert.match(explanation, /70 Car-Hacking attack alerts and seven ROAD false alarms/)
  assert.match(explanation, /no ROAD attack alerts/)
})

test('prediction submission requires an available alert set and labeled inputs', () => {
  assert.equal(renderToStaticMarkup(<SubmitSection sets={[]} />), '')
  const html = renderToStaticMarkup(<SubmitSection sets={['heldout']} />)
  assert.match(html, /for="submission-set"/)
  assert.match(html, /for="submission-name"/)
  assert.match(html, /for="submission-file"/)
  assert.match(html, /\/api\/benchmark\/explainers\/heldout\/packets/)
  assert.equal(runLabel('glm-5.3_v2-dosv1_alert'), 'glm-5.3 (v2, Oct 21 DoS line)')
})

test('unlabeled capture still supports explanation without displaying accuracy', () => {
  const html = renderToStaticMarkup(<MetricsPanel report={report} alertCount={2} explainerLabel="Gemma" />)
  assert.match(html, /Explain remaining alerts with Gemma/)
  assert.match(html, /0 \/ 2 responses cached/)
  assert.match(html, /accuracy and detection metrics are unavailable/)
  assert.doesNotMatch(html, /class="label">Precision/)
})

test('uncached explanation keeps measured evidence available and requests explicit generation', () => {
  const html = renderToStaticMarkup(<ExplanationPanel detail={{ alert, evidence: {
    items: [{ id: 'E0', kind: 'metadata', text: '100 frames measured' }],
  } }} explainerLabel="Gemma" />)
  assert.match(html, /Explain with Gemma/)
  assert.match(html, /100 frames measured/)
  assert.doesNotMatch(html, /LLM replies usually/)
})

test('a model fallback is identified and citations are not described as factual grounding', () => {
  const html = renderToStaticMarkup(<ExplanationPanel detail={{ alert,
    evidence: { items: [] }, explanation: { attack_type: 'dos', model: 'mock',
      fallback: true, claims: [], grounded: true, summary: 'Flood detected' },
  }} />)
  assert.match(html, /response uses the offline control/)
  assert.match(html, /valid citations/)
  assert.match(html, /not whether they support the claim/)
})

test('an unclassified alert is not marked as an incorrect prediction', () => {
  const html = renderToStaticMarkup(<AlertList alerts={[alert]} labeled />)
  assert.match(html, /truth: dos/)
  assert.doesNotMatch(html, /✗/)
})

test('binary attack labels do not imply an attack-type classification target', () => {
  const explanation = { attack_type: 'dos', severity: 'high' }
  const html = renderToStaticMarkup(<AlertList alerts={[{ ...alert, true_type: 'injected', explanation }]} labeled />)
  assert.match(html, /attack labeled; type unavailable/)
  assert.doesNotMatch(html, /✗|✓|mismatch|truth:/)
  const unknown = renderToStaticMarkup(<AlertList alerts={[{ ...alert, true_type: 'unknown', explanation }]} labeled />)
  assert.doesNotMatch(unknown, /✗|✓|mismatch|truth:/)
  const typed = renderToStaticMarkup(<AlertList alerts={[{ ...alert, true_type: 'fuzzing', explanation }]} labeled />)
  assert.match(typed, /✗ fuzzing/)
})

test('upload sends separate baseline and metadata and every chosen detector parameter', async () => {
  const before = globalThis.fetch
  let called
  globalThis.fetch = async (url, options) => {
    called = { url, options }
    return { ok: true, json: async () => ({ analysis_id: 'test' }) }
  }
  try {
    const file = new Blob(['timestamp,id\n1,000'])
    await api.uploadLog(file, { detector: 'forest', window_s: 1, stride_s: 0.5, threshold: 0.75 },
      { baselineFile: file, metadataFile: new Blob(['{}']), baselineSeconds: 20 })
    const url = new URL(called.url, 'http://localhost')
    assert.equal(url.searchParams.get('threshold'), '0.75')
    assert.equal(url.searchParams.get('window_s'), '1')
    assert.equal(url.searchParams.get('stride_s'), '0.5')
    assert.equal(url.searchParams.get('detector'), 'forest')
    assert.equal(url.searchParams.has('baseline_s'), false)
    assert.ok(called.options.body.get('file'))
    assert.ok(called.options.body.get('baseline_file'))
    assert.ok(called.options.body.get('metadata_file'))
    assert.equal(called.options.headers, undefined)
    await api.uploadLog(file, { detector: 'rule', window_s: 0.5, stride_s: 0.25, threshold: 0.55 }, { baselineSeconds: 60 })
    assert.equal(new URL(called.url, 'http://localhost').searchParams.get('baseline_s'), '60')
  } finally { globalThis.fetch = before }
})

test('upload preserves detailed server validation errors', async () => {
  const before = globalThis.fetch
  globalThis.fetch = async () => ({ ok: false, status: 400, json: async () => ({ detail: 'Baseline includes attacks' }) })
  try {
    await assert.rejects(api.uploadLog(new Blob(['test']), {}), /400: Baseline includes attacks/)
  } finally { globalThis.fetch = before }
})


test('stopping a batch finishes and publishes the in-flight request but schedules no next request', async () => {
  let stopped = false
  let finish
  const requests = [], results = []
  const batch = runExplanationQueue({
    items: [1, 2, 3], isStopped: () => stopped, isCurrent: () => true,
    explain: async (item) => { requests.push(item); await new Promise((resolve) => { finish = resolve }) },
    onResult: async (item) => { results.push(item) },
  })
  assert.deepEqual(requests, [1])
  stopped = true
  finish()
  await batch
  assert.deepEqual(requests, [1])
  assert.deepEqual(results, [1])
})

test('capture or model change discards a stale batch response and stops further requests', async () => {
  let current = true
  let finish
  const requests = [], results = []
  const batch = runExplanationQueue({
    items: [1, 2], isStopped: () => false, isCurrent: () => current,
    explain: async (item) => { requests.push(item); await new Promise((resolve) => { finish = resolve }) },
    onResult: async (item) => { results.push(item) },
  })
  current = false
  finish()
  await batch
  assert.deepEqual(requests, [1])
  assert.deepEqual(results, [])
})

test('batch failure retains completed results and stops new requests', async () => {
  const requests = [], results = []
  await assert.rejects(runExplanationQueue({
    items: [1, 2, 3], isStopped: () => false, isCurrent: () => true,
    explain: async (item) => { requests.push(item); if (item === 2) throw new Error('Model unavailable') },
    onResult: async (item) => { results.push(item) },
  }), /Model unavailable/)
  assert.deepEqual(requests, [1, 2])
  assert.deepEqual(results, [1])
})


test('downsampled timeline discloses display coverage without changing evaluation scope', () => {
  const html = renderToStaticMarkup(<TimelineChart timeline={{
    points: [{ t: 0, msg_rate: 50, score: 0 }], downsampled: true, original_point_count: 5000,
  }} />)
  assert.match(html, /Displaying 1 representative measurements from 5,000 windows/)
  assert.match(html, /evaluation uses all windows/)
})


test('benchmark fallbacks cannot receive credit for the control prediction', () => {
  const result = { attack_type: 'dos', fallback: true, model: 'mock' }
  const html = renderToStaticMarkup(<Prediction alert={alert} result={result} />)
  assert.equal(predictionType(result), 'request_failed')
  assert.match(html, /mismatch/)
  assert.match(html, /request_failed/)
  assert.equal(predictionType({ attack_type: 'dos', model: 'mock (fallback: Timeout)' }), 'request_failed')
  assert.equal(predictionType({ attack_type: 'dos', model: 'mock' }), 'dos')
})


test('saved detector comparison retains all six results, negative outcomes, and scope cautions', () => {
  const runs = Array.from({ length: 6 }, (_, index) => ({
    id: `run-${index}`, dataset: 'ROAD', profile: `profile-${index}`, detector: index % 2 ? 'forest' : 'rule',
    scope: 'all', metrics: { precision: .77, recall: index === 5 ? .0925 : .509, f1: .613,
      false_positive_rate: index === 4 ? .404 : .1026, windows_evaluated: 6353 },
    normal_metrics: index === 0 ? null : { false_positive_rate: .00466 },
    source: `out/detectors/run-${index}.json`, methodology: 'Separate normal calibration and evaluation',
  }))
  const html = renderToStaticMarkup(<DetectionBenchmarkPanel data={{ runs, errors: [] }} />)
  assert.match(html, /Saved detector comparisons · 6 results/)
  for (let i = 0; i < 6; i++) assert.match(html, new RegExp(`profile-${i}`))
  assert.match(html, /9.3%/)
  assert.match(html, /40.4%/)
  assert.match(html, /different baselines and normal holdouts/)
  assert.match(html, /can hide false positives in attack captures/)
  assert.match(html, /n\/a/)
  assert.match(html, /out\/detectors\/run-5.json/)
})

test('detection benchmark uses the read-only saved-results endpoint', async () => {
  const before = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options })
    return { ok: true, json: async () => ({ runs: [], errors: [] }) }
  }
  try {
    assert.deepEqual(await api.detectionBenchmark(), { runs: [], errors: [] })
    assert.equal(calls.length, 1)
    assert.equal(calls[0].url, '/api/benchmark/detectors')
    assert.equal(calls[0].options.method, undefined)
    assert.equal(calls[0].options.body, undefined)
  } finally { globalThis.fetch = before }
})


const identifierWarnings = [{ code: 'can_id_not_in_evidence', field: 'summary', token: '0x55',
  canonical_id: '0x055', start: 9, end: 13, message: 'This CAN ID is absent from the supplied evidence.' }]

test('live identifier warnings stay separate from valid citations and predictions', () => {
  const explanation = { attack_type: 'spoofing', model: 'glm-5.3', grounded: true,
    claims: [], summary: 'Anomaly on 0x55.', validation_warnings: identifierWarnings }
  const before = JSON.stringify(explanation)
  const html = renderToStaticMarkup(<ExplanationPanel detail={{ alert,
    evidence: { items: [] }, explanation }} />)
  assert.match(html, /Identifier review · 1 reference to check/)
  assert.match(html, /ID absent from evidence/)
  assert.match(html, /Summary · <span class="mono">0x55/)
  assert.match(html, /valid citations/)
  assert.match(html, /spoofing/)
  assert.match(html, /It does not validate the explanation/)
  assert.doesNotMatch(html, /citation issues/)
  assert.equal(JSON.stringify(explanation), before)
})

test('saved benchmark reasoning displays identifier review without changing citation or label status', () => {
  const runs = [{ id: 'control', label: 'Control', explainer: 'mock' }, { id: 'glm', label: 'GLM', explainer: 'rcd' }]
  const html = renderToStaticMarkup(<AlertReasoning alert={{ ...alert, capture: 'sample', results: {
    control: { attack_type: 'dos', summary: 'Control summary' },
    glm: { attack_type: 'dos', summary: 'Review 0x55', grounded: true, grounded_as_run: true,
      claims: [], validation_warnings: identifierWarnings },
  } }} runs={runs} llms={[runs[1]]} />)
  assert.match(html, /Identifier review/)
  assert.match(html, /valid citations/)
  assert.match(html, /badge match">dos/)
})

test('ambiguous hex is a review note, and absent warnings produce no assurance badge', () => {
  const html = renderToStaticMarkup(<ValidationWarnings warnings={[{
    code: 'ambiguous_hex_reference', field: 'claims[0].text', token: '0x55', start: 0,
    message: 'This hexadecimal reference needs context review.',
  }]} />)
  assert.match(html, /Ambiguous hexadecimal reference/)
  assert.match(html, /Claim 1/)
  assert.doesNotMatch(html, /ID absent from evidence/)
  assert.equal(renderToStaticMarkup(<ValidationWarnings warnings={[]} />), '')
  assert.equal(renderToStaticMarkup(<ValidationWarnings />), '')
})


test('delayed ID details do not delay the core analysis view', async () => {
  let finishIds
  const published = []
  const { coreDone, idsDone } = loadAnalysisViews({
    loadCore: async () => 'alerts ready',
    loadIds: () => new Promise((resolve) => { finishIds = resolve }),
    isCurrent: () => true,
    onCore: (value) => published.push(value),
    onIds: () => published.push('ID details ready'),
    onIdsError: () => assert.fail('unexpected ID error'),
  })
  await coreDone
  assert.deepEqual(published, ['alerts ready'])
  finishIds([{ can_id: '0x001' }])
  await idsDone
  assert.deepEqual(published, ['alerts ready', 'ID details ready'])
})

test('late IDs from an obsolete capture are suppressed', async () => {
  let finishIds, current = true
  const published = []
  const { coreDone, idsDone } = loadAnalysisViews({
    loadCore: async () => 'capture A',
    loadIds: () => new Promise((resolve) => { finishIds = resolve }),
    isCurrent: () => current,
    onCore: (value) => published.push(value),
    onIds: () => published.push('stale IDs'),
    onIdsError: () => published.push('stale error'),
  })
  await coreDone
  current = false
  finishIds([{ can_id: '0x001' }])
  await idsDone
  assert.deepEqual(published, ['capture A'])
})

test('ID view discloses loading and capped results rather than an empty complete table', () => {
  const loading = renderToStaticMarkup(<IdView ids={[]} loading totalIds={100} />)
  assert.match(loading, /Loading per-ID details/)
  assert.doesNotMatch(loading, /0 matching/)
  const capped = renderToStaticMarkup(<IdView ids={[]} totalIds={100} />)
  assert.match(capped, /0 displayed IDs of 100 total/)
  assert.match(capped, /Highest-interest IDs are shown first/)
})


test('a model change does not discard pending ID details for the same capture', async () => {
  let finishIds, currentModel = true
  const published = []
  const { coreDone, idsDone } = loadAnalysisViews({
    loadCore: async () => 'capture A',
    loadIds: () => new Promise((resolve) => { finishIds = resolve }),
    isCurrent: () => currentModel,
    isIdsCurrent: () => true,
    onCore: (value) => published.push(value),
    onIds: () => published.push('capture A IDs'),
    onIdsError: () => assert.fail('unexpected ID error'),
  })
  await coreDone
  currentModel = false
  finishIds([{ can_id: '0x001' }])
  await idsDone
  assert.deepEqual(published, ['capture A', 'capture A IDs'])
})
