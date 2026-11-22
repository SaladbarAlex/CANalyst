/** Authorized local-browser QA. Uses existing Playwright/Chrome; installs nothing.
 * Default makes no hosted-model calls. Timing simulations are labeled fixtures.
 * Run from frontend: node scripts/browser-qa.mjs
 */
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
const script = fileURLToPath(import.meta.url)
const frontend = path.resolve(path.dirname(script), '..')
const repo = path.resolve(frontend, '..')
const require = createRequire(import.meta.url)
const modulePath = process.env.CANALYST_PLAYWRIGHT_MODULE || path.resolve(frontend, '../../../soc-hype/node_modules/playwright')
const { chromium } = require(modulePath)
const baseURL = process.env.CANALYST_QA_URL || 'http://127.0.0.1:5173'
const output = process.env.CANALYST_QA_OUTPUT || path.join(repo, 'backend/out/browser_qa_2026-10-30', new Date().toISOString().replaceAll(':', '-'))
mkdirSync(output, { recursive: true })
const results = { started: new Date().toISOString(), browser: 'local Playwright with installed Google Chrome',
  script_sha256: createHash('sha256').update(readFileSync(script)).digest('hex'), baseURL,
  scope: 'live local UI/API plus explicitly labeled route fixtures; no hosted-model calls',
  output, checks: [], pageErrors: [], consoleErrors: [], httpErrors: [], explanationRequests: [] }
let browser, page, phase = 'initial-live'
const deferred = () => { let resolve; const promise = new Promise((r) => { resolve = r }); return { promise, resolve } }
const explainPath = /\/api\/analysis\/[^/]+\/alerts\/\d+\/explain$/
const listIdsPath = /\/api\/analysis\/[^/]+\/ids$/
const save = () => writeFileSync(path.join(output, 'results.json'), JSON.stringify(results, null, 2))
async function step(name, transport, action) {
  phase = name
  const started = Date.now()
  try {
    const detail = await action()
    results.checks.push({ name, transport, passed: true, elapsed_ms: Date.now() - started, ...detail })
    console.log(`PASS ${name}`)
    save()
  } catch (error) {
    results.checks.push({ name, transport, passed: false, elapsed_ms: Date.now() - started, error: error.message })
    throw error
  }
}
async function screenshot(name) {
  await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true, animations: 'disabled' })
}
async function selectTheme(theme) {
  if (await page.locator('html').getAttribute('data-theme') !== theme)
    await page.getByRole('button', { name: `Switch to ${theme} theme`, exact: true }).click()
  assert.equal(await page.locator('html').getAttribute('data-theme'), theme)
}
async function openSettings() {
  const details = page.locator('details.capture-settings')
  if (await details.count() && await details.getAttribute('open') === null) await details.locator('summary').click()
}
try {
  browser = await chromium.launch({ channel: 'chrome', headless: true })
  results.browserVersion = browser.version()
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' })
  page = await context.newPage()
  page.on('pageerror', (error) => results.pageErrors.push({ phase, error: error.message }))
  page.on('console', (message) => { if (message.type() === 'error') results.consoleErrors.push({ phase, text: message.text(), location: message.location() }) })
  page.on('response', (response) => { if (response.status() >= 400) results.httpErrors.push({ phase, url: response.url(), status: response.status() }) })
  page.on('request', (request) => {
    if (request.method() === 'POST' && explainPath.test(new URL(request.url()).pathname)) {
      results.explanationRequests.push({ phase, path: new URL(request.url()).pathname, ...request.postDataJSON() })
    }
  })
  let syntheticId, firstAlertId
  await step('Initial synthetic analysis and control explanation', 'live API', async () => {
    const response = page.waitForResponse((r) => new URL(r.url()).pathname === '/api/analyze/synthetic')
    await page.goto(`${baseURL}/?dataset=synthetic`, { waitUntil: 'domcontentloaded' })
    const summary = await (await response).json()
    syntheticId = summary.analysis_id
    await page.getByRole('button', { name: 'Re-explain', exact: true }).waitFor({ state: 'visible', timeout: 60000 })
    firstAlertId = Number((await page.locator('.explain-head h3').innerText()).match(/Alert (\d+)/)[1])
    assert.match(await page.locator('.readouts').innerText(), new RegExp(`${summary.unknown_ids_count} outside baseline`))
    results.explainerOptions = await page.locator('#explainer option').evaluateAll((options) => options.map((o) => ({ value: o.value, label: o.textContent, disabled: o.disabled })))
    return { summary, selected_alert: firstAlertId }
  })
  await step('Complete timeline curves and early detector peaks render without reveal delay', 'live timeline API and rendered SVG', async () => {
    const timeline = await (await page.request.get(`${baseURL}/api/analysis/${syntheticId}/timeline`)).json()
    const curves = await page.locator('.scope .recharts-area-curve, .scope .recharts-line-curve').evaluateAll((paths) => paths.map((p) => {
      const length = p.getTotalLength(), first = p.getPointAtLength(0), last = p.getPointAtLength(length)
      return { first_x: first.x, last_x: last.x, svg_width: p.ownerSVGElement.getBoundingClientRect().width,
        path_width: p.getBBox().width, dash: p.getAttribute('stroke-dasharray') }
    }))
    assert.equal(curves.length, 2)
    for (const curve of curves) assert.ok(curve.last_x - curve.first_x >= curve.svg_width - 70, JSON.stringify(curve))
    const earlyPeaks = timeline.points.filter((p) => p.t < 65 && p.score >= .99)
    assert.ok(earlyPeaks.length > 0, 'early DoS/fuzzing score peaks are in the live measurements')
    assert.ok(timeline.points.at(-1).t >= 149)
    await screenshot('complete-initial-timeline')
    return { curves, early_peak_count: earlyPeaks.length, last_time: timeline.points.at(-1).t }
  })
  for (const appearance of ['pastel', 'original']) for (const theme of ['light', 'dark']) {
    await step(`${appearance} ${theme} appearance`, 'live rendered UI', async () => {
      await page.locator('#appearance').selectOption(appearance)
      await selectTheme(theme)
      assert.equal(await page.locator('html').getAttribute('data-appearance'), appearance)
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true)
      await screenshot(`${appearance}-${theme}`)
    })
  }
  await page.locator('#appearance').selectOption('pastel')
  await selectTheme('light')
  await step('Citation opens and highlights its measured evidence', 'live UI and API evidence', async () => {
    const cite = page.locator('.explanation-column .claims button.cite').first()
    const citation = await cite.innerText()
    await cite.click()
    await page.locator('.explanation-column tr.highlight').waitFor({ state: 'visible' })
    assert.equal(await page.locator('.explanation-column tr.highlight td').first().innerText(), citation)
    await screenshot('citation-navigation')
    return { citation }
  })
  await step('Model selection makes no hosted calls and returns to cached control', 'live API; no hosted generation', async () => {
    const before = results.explanationRequests.length
    await page.locator('#explainer').selectOption('rcd:gemma-4-31b')
    await page.getByRole('button', { name: /Explain with gemma-4-31b/ }).waitFor({ state: 'visible' })
    await page.locator('#explainer').selectOption('rcd:glm-5.3')
    await page.getByRole('button', { name: /Explain with glm-5.3/ }).waitFor({ state: 'visible' })
    await page.waitForTimeout(350)
    assert.equal(results.explanationRequests.length, before)
    await page.locator('#explainer').selectOption('mock')
    await page.getByRole('button', { name: 'Re-explain', exact: true }).waitFor({ state: 'visible' })
    assert.equal(results.explanationRequests.length, before)
    return { new_explanation_requests: 0 }
  })
  await step('Explicit local control re-explanation', 'live API, mock control only', async () => {
    const response = page.waitForResponse((r) => explainPath.test(new URL(r.url()).pathname) && r.request().postDataJSON()?.explainer === 'mock')
    await page.getByRole('button', { name: 'Re-explain', exact: true }).click()
    assert.equal((await response).status(), 200)
    await page.getByRole('button', { name: 'Re-explain', exact: true }).waitFor({ state: 'visible' })
  })
  await step('Batch Stop finishes current control request and schedules no next request', 'route delay fixture; completed request uses live mock control', async () => {
    const gate = deferred(), started = deferred()
    let calls = 0
    const handler = async (route) => {
      if (route.request().postDataJSON()?.explainer !== 'mock') return route.continue()
      calls++; started.resolve(); await gate.promise; await route.continue()
    }
    await page.route(explainPath, handler)
    await page.getByRole('tab', { name: /Evaluation$/ }).click()
    await page.getByRole('button', { name: /Explain remaining alerts with Offline control/ }).click()
    await started.promise
    await page.getByRole('button', { name: 'Stop after current', exact: true }).first().click()
    assert.match(await page.locator('.batch-status').innerText(), /Stopping after the current request/)
    gate.resolve()
    await page.locator('.batch-status').waitFor({ state: 'hidden', timeout: 15000 })
    await page.waitForTimeout(300)
    assert.equal(calls, 1)
    await page.unroute(explainPath, handler)
    await screenshot('batch-stopped')
    return { delayed_requests_completed: calls }
  })
  await step('Late hosted response cannot overwrite a new model selection', 'mocked hosted-response route fixture; zero upstream hosted calls', async () => {
    await page.getByRole('tab', { name: /Analysis$/ }).click()
    await page.locator('#explainer').selectOption('rcd:glm-5.3')
    await page.getByRole('button', { name: /Explain with glm-5.3/ }).waitFor({ state: 'visible' })
    const detailPath = `/api/analysis/${syntheticId}/alerts/${firstAlertId}`
    const template = await (await page.request.get(`${baseURL}${detailPath}?explainer=mock`)).json()
    const fake = { ...template.explanation, model: 'MOCKED_DELAYED_GLM', summary: 'MOCKED_STALE_REPLY_MUST_NOT_APPEAR' }
    const gate = deferred(), started = deferred(), returned = deferred()
    const postHandler = async (route) => { started.resolve(); await gate.promise; await route.fulfill({ json: { alert_id: firstAlertId, explanation: fake, evidence: template.evidence } }) }
    const readHandler = async (route) => {
      const url = new URL(route.request().url())
      if (url.pathname === detailPath && url.searchParams.get('explainer') === 'rcd:glm-5.3') {
        await route.fulfill({ json: { ...template, explanation: fake } }); returned.resolve()
      } else await route.continue()
    }
    await page.route(explainPath, postHandler)
    await page.route(/\/api\/analysis\/[^/]+\/alerts\/\d+\?explainer=/, readHandler)
    await page.getByRole('button', { name: /Explain with glm-5.3/ }).click()
    await started.promise
    await page.locator('#explainer').selectOption('mock')
    await page.getByRole('button', { name: 'Re-explain', exact: true }).waitFor({ state: 'visible' })
    gate.resolve(); await returned.promise; await page.waitForTimeout(300)
    assert.equal(await page.locator('#explainer').inputValue(), 'mock')
    assert.doesNotMatch(await page.locator('.explanation-column').innerText(), /MOCKED_STALE/)
    await page.unroute(explainPath, postHandler)
    await page.unroute(/\/api\/analysis\/[^/]+\/alerts\/\d+\?explainer=/, readHandler)
  })
  await step('Saved detector comparisons and v4 identifier warning', 'live saved-result APIs; no model calls', async () => {
    const explanations = page.waitForResponse((r) => new URL(r.url()).pathname === '/api/benchmark')
    const detection = page.waitForResponse((r) => new URL(r.url()).pathname === '/api/benchmark/detectors')
    await page.getByRole('tab', { name: /Benchmark$/ }).click()
    const data = await (await explanations).json(), det = await (await detection).json()
    assert.ok(det.runs.length >= 12)
    await page.locator('.detection-benchmarks > summary').click()
    assert.equal(await page.locator('.detection-benchmarks table tbody tr').count(), det.runs.length)
    assert.ok(det.runs.some((r) => r.metrics.recall < .1))
    assert.ok(det.runs.some((r) => r.metrics.false_positive_rate > .4))
    const ds = data.datasets.find((d) => d.dataset === 'road' && d.runs.some((r) => r.source.includes('explanations_v4_2026-10-30_glm_low')))
    assert.ok(ds, 'v4 ROAD dataset present')
    const run = ds.runs.find((r) => r.source.includes('explanations_v4_2026-10-30_glm_low'))
    const alert = ds.alerts.find((a) => a.results[run.id]?.validation_warnings?.some((w) => w.token === '0x55'))
    assert.ok(alert, 'saved v4 0x55 warning is present')
    await page.getByRole('button', { name: ds.label, exact: true }).click()
    await page.locator('tr.benchmark-row').filter({ hasText: `${alert.capture.replace(/_dataset$/, '')} · #${alert.alert_id}` }).click()
    const warning = page.locator('.benchmark-detail-panel .identifier-warnings').filter({ hasText: '0x55' })
    await warning.locator('summary').click()
    assert.match(await warning.innerText(), /ID absent from evidence/)
    assert.equal(await warning.locator('.mono').filter({ hasText: '0x55' }).count() > 0, true)
    await screenshot('saved-benchmarks-identifier-warning')
    return { detector_rows: det.runs.length, detector_source_files: new Set(det.runs.map((r) => r.source)).size,
      warning_capture: alert.capture, warning_alert_id: alert.alert_id, warning_run: run.source }
  })
  await step('Frozen benchmarks integrate with live capture evaluation', 'live saved-result APIs; no model calls', async () => {
    const explanations = page.waitForResponse((r) => new URL(r.url()).pathname === '/api/benchmark/explainers')
    const detection = page.waitForResponse((r) => new URL(r.url()).pathname === '/api/benchmark/detection')
    await page.getByRole('tab', { name: /Evaluation$/ }).click()
    await page.getByRole('button', { name: 'Frozen benchmarks', exact: true }).click()
    const data = await (await explanations).json(), det = await (await detection).json()
    assert.ok(data.heldout.runs)
    assert.ok(det.datasets.length)
    await page.getByRole('heading', { name: 'Explainers: which labels and explanations hold up' }).waitFor()
    await page.getByRole('heading', { name: 'Detectors: held-out captures only' }).waitFor()
    assert.match(await page.locator('.benchmarks').innerText(), /no ROAD attack alerts/)
    const compare = page.waitForResponse((r) => new URL(r.url()).pathname.endsWith('/heldout/compare'))
    await page.getByRole('combobox', { name: 'Second explainer', exact: true }).selectOption('control-v1_alert')
    assert.equal((await compare).status(), 200)
    await page.getByRole('combobox', { name: 'Dataset', exact: true }).selectOption('hcrl')
    assert.equal(await page.locator('#submission-set').inputValue(), 'heldout')
    assert.match(await page.getByRole('link', { name: 'Download packets' }).getAttribute('href'), /heldout\/packets$/)
    await screenshot('frozen-benchmarks')
    for (const appearance of ['original', 'pastel']) for (const theme of ['light', 'dark']) {
      await page.locator('#appearance').selectOption(appearance)
      await selectTheme(theme)
      await page.setViewportSize({ width: 390, height: 844 })
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true)
      await screenshot(`frozen-benchmarks-mobile-${appearance}-${theme}`)
    }
    await page.setViewportSize({ width: 1440, height: 1000 })
    await page.locator('#appearance').selectOption('original')
    await selectTheme('dark')
    await page.getByRole('button', { name: 'This capture', exact: true }).click()
    await page.getByRole('button', { name: /Explain remaining alerts/ }).waitFor()
    return { sets: Object.keys(data), detector_datasets: det.datasets.map((d) => d.dataset), viewport: [390, 844] }
  })
  await step('Invalid ROAD metadata is reported before analysis', 'live upload API, deliberately invalid metadata', async () => {
    await page.getByRole('tab', { name: /Analysis$/ }).click()
    await openSettings()
    await page.locator('#traffic-file').setInputFiles(path.join(repo, 'backend/data/raw/road/road/attacks/correlated_signal_attack_3.log'))
    await page.locator('#baseline-file').setInputFiles(path.join(repo, 'backend/data/raw/road/road/ambient/ambient_dyno_drive_basic_short.log'))
    await page.locator('#metadata-file').setInputFiles({ name: 'capture_metadata.json', mimeType: 'application/json', buffer: Buffer.from('{invalid json') })
    assert.equal(await page.locator('#baseline-seconds').isDisabled(), true)
    const response = page.waitForResponse((r) => new URL(r.url()).pathname === '/api/analyze/upload')
    await page.getByRole('button', { name: 'Analyze selected log', exact: true }).click()
    assert.equal((await response).status(), 400)
    await page.getByRole('alert').waitFor({ state: 'visible' })
    assert.match(await page.getByRole('alert').innerText(), /Could not analyze capture/)
    await screenshot('invalid-road-metadata')
  })
  await step('Real ROAD capture with separate baseline and metadata', 'live upload and analysis API', async () => {
    await page.locator('#metadata-file').setInputFiles(path.join(repo, 'backend/data/raw/road/road/attacks/capture_metadata.json'))
    const response = page.waitForResponse((r) => new URL(r.url()).pathname === '/api/analyze/upload', { timeout: 60000 })
    await page.getByRole('button', { name: 'Analyze selected log', exact: true }).click()
    const res = await response, summary = await res.json()
    assert.equal(res.status(), 200)
    assert.equal(summary.source, 'correlated_signal_attack_3.log')
    assert.equal(summary.baseline_source, 'separate capture')
    assert.equal(summary.labeled, true)
    assert.equal(summary.detector, 'rule')
    assert.equal(summary.params.window_s, .5)
    assert.equal(summary.params.stride_s, .25)
    assert.equal(summary.params.threshold, .55)
    await page.getByRole('button', { name: 'Re-explain', exact: true }).waitFor({ state: 'visible', timeout: 60000 })
    assert.match(await page.locator('.status').innerText(), /correlated_signal_attack_3.log/)
    await screenshot('road-upload-analysis')
    return { summary }
  })
  await step('Binary-label upload shows no unsupported type-correctness badge', 'live upload API with generated binary-labeled CSV fixture', async () => {
    await openSettings()
    const csv = (n, rate, label) => Buffer.from('Time,ID,Data,Label\n' + Array.from({ length: n }, (_, i) => `${i / rate},100,0000000000000000,${label}`).join('\n'))
    await page.locator('#traffic-file').setInputFiles({ name: 'binary-attack.csv', mimeType: 'text/csv', buffer: csv(5000, 1000, 1) })
    await page.locator('#baseline-file').setInputFiles({ name: 'binary-normal.csv', mimeType: 'text/csv', buffer: csv(500, 100, 0) })
    await page.locator('#metadata-file').setInputFiles([])
    const response = page.waitForResponse((r) => new URL(r.url()).pathname === '/api/analyze/upload', { timeout: 60000 })
    await page.getByRole('button', { name: 'Analyze selected log', exact: true }).click()
    const res = await response, summary = await res.json()
    assert.equal(res.status(), 200)
    assert.equal(summary.labeled, true)
    await page.getByRole('button', { name: 'Re-explain', exact: true }).waitFor({ state: 'visible', timeout: 15000 })
    assert.match(await page.locator('.alert-list').innerText(), /attack labeled; type unavailable/)
    assert.doesNotMatch(await page.locator('.alert-list').innerText(), /✗ injected|✓ injected/)
    assert.match(await page.locator('.readouts').innerText(), /binary labels/)
    assert.match(await page.locator('.readouts').innerText(), /attack type unavailable/)
    await screenshot('binary-label-upload')
    return { summary, generated_fixture: { traffic_frames: 5000, baseline_frames: 500, label_scope: 'binary only' } }
  })
  await step('Core alerts render while IDs wait; model switch preserves pending IDs', 'delayed-ID route fixture with live core analysis and live ID results', async () => {
    const gate = deferred(), started = deferred()
    const handler = async (route) => { started.resolve(); await gate.promise; await route.continue() }
    await page.route(listIdsPath, handler)
    await page.reload({ waitUntil: 'domcontentloaded' })
    await started.promise
    await page.getByRole('button', { name: 'Re-explain', exact: true }).waitFor({ state: 'visible', timeout: 60000 })
    await page.getByRole('tab', { name: /Per-ID view$/ }).click()
    await page.getByRole('status').filter({ hasText: 'Loading per-ID details' }).waitFor({ state: 'visible' })
    await page.locator('#explainer').selectOption('rcd:glm-5.3')
    gate.resolve()
    await page.getByText(/matching \/ .*displayed IDs/).waitFor({ state: 'visible', timeout: 15000 })
    assert.doesNotMatch(await page.locator('main').innerText(), /Loading per-ID details/)
    await page.unroute(listIdsPath, handler)
    await screenshot('ids-loaded-after-model-switch')
  })
  await step('Obsolete delayed ID results cannot overwrite a new capture', 'stale-ID route fixture; both core analyses use live API', async () => {
    const gate = deferred(), started = deferred(), returned = deferred()
    let intercepted = false
    const handler = async (route) => {
      if (intercepted) return route.continue()
      intercepted = true; started.resolve(); await gate.promise
      await route.fulfill({ json: [{ can_id: '0x055', name: 'MOCKED_STALE_ID_ROW', function: 'MOCKED_STALE_ID_ROW',
        known: true, count: 1, rate: 1, baseline_rate: 1, iat_mean_ms: 1, iat_std_ms: 0, entropy: 0 }] })
      returned.resolve()
    }
    await page.route(listIdsPath, handler)
    await page.reload({ waitUntil: 'domcontentloaded' })
    await started.promise
    await page.getByRole('button', { name: 'Re-explain', exact: true }).waitFor({ state: 'visible', timeout: 60000 })
    await openSettings()
    await page.locator('#seed').fill('2')
    await page.getByRole('button', { name: 'Run demo analysis', exact: true }).click()
    await page.getByRole('button', { name: 'Re-explain', exact: true }).waitFor({ state: 'visible', timeout: 60000 })
    await page.getByRole('tab', { name: /Per-ID view$/ }).click()
    await page.getByText(/matching \/ .*displayed IDs/).waitFor({ state: 'visible', timeout: 15000 })
    gate.resolve(); await returned.promise; await page.waitForTimeout(300)
    assert.doesNotMatch(await page.locator('main').innerText(), /MOCKED_STALE_ID_ROW/)
    await page.unroute(listIdsPath, handler)
  })
  await step('Installed ROAD capture opens by default', 'live startup API with separate normal baseline', async () => {
    const response = page.waitForResponse((r) => new URL(r.url()).pathname === '/api/analyze/real-example')
    await page.goto(baseURL, { waitUntil: 'domcontentloaded' })
    const summary = await (await response).json()
    assert.equal(summary.frame_count, 41829)
    assert.match(summary.source, /correlated_signal_attack_3/)
    assert.ok(summary.baseline_source)
    await page.getByRole('button', { name: 'Re-explain', exact: true }).waitFor({ state: 'visible', timeout: 60000 })
    await screenshot('real-road-default-startup')
    return { frame_count: summary.frame_count, source: summary.source, baseline_source: summary.baseline_source }
  })
  assert.equal(results.pageErrors.length, 0)
  results.unexpectedHttpErrors = results.httpErrors.filter((e) =>
    !(e.phase === 'Invalid ROAD metadata is reported before analysis' && e.status === 400))
  results.unexpectedConsoleErrors = results.consoleErrors.filter((e) =>
    !(e.phase === 'Invalid ROAD metadata is reported before analysis' && e.text.includes('400')))
  assert.deepEqual(results.unexpectedHttpErrors, [])
  assert.deepEqual(results.unexpectedConsoleErrors, [])
  results.hostedUpstreamCalls = 0
  results.passed = true
} catch (error) {
  results.passed = false
  results.failure = { phase, message: error.message, stack: error.stack }
  if (page) {
    await page.screenshot({ path: path.join(output, 'failure.png'), fullPage: true, animations: 'disabled' }).catch(() => {})
    writeFileSync(path.join(output, 'failure.txt'), await page.locator('body').innerText().catch(() => 'Page unavailable'))
  }
  console.error(error.message)
  process.exitCode = 1
} finally {
  results.finished = new Date().toISOString()
  save()
  if (browser) await browser.close()
  console.log(`QA artifacts: ${output}`)
}
