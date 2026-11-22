import { useCallback, useEffect, useRef, useState } from 'react'
import { api, fmt } from './api'
import { runExplanationQueue } from './explanationQueue'
import { loadAnalysisViews } from './analysisLoad'
import AlertList from './components/AlertList'
import AsciiCar from './components/AsciiCar'
import AskPanel from './components/AskPanel'
import BenchmarkPanel from './components/BenchmarkPanel'
import Controls from './components/Controls'
import ExplanationPanel from './components/ExplanationPanel'
import IdView from './components/IdView'
import MetricsPanel from './components/MetricsPanel'
import TimelineChart from './components/TimelineChart'

const DEFAULTS = {
  duration_s: 150,
  seed: 1,
  window_s: 0.5,
  stride_s: 0.25,
  threshold: 0.55,
  detector: 'rule',
  attacks: ['dos', 'fuzzing', 'spoofing', 'replay', 'masquerade'],
}

export default function App() {
  const [params, setParams] = useState(DEFAULTS)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [summary, setSummary] = useState(null)
  const [timeline, setTimeline] = useState(null)
  const [alerts, setAlerts] = useState([])
  const [ids, setIds] = useState([])
  const [idsLoading, setIdsLoading] = useState(false)
  const [idsError, setIdsError] = useState(null)
  const [report, setReport] = useState(null)
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)
  const [explaining, setExplaining] = useState(false)
  const [scoring, setScoring] = useState(false)
  const [progress, setProgress] = useState(null)
  const generation = useRef(0)
  const captureGeneration = useRef(0)
  const started = useRef(false)
  const stopScoring = useRef(false)
  const activeView = useRef({})
  activeView.current = { analysisId: summary?.analysis_id, selected, explainer: null }
  const [tab, setTab] = useState('analysis')
  // The offline control is the default: it is instant, so loading a capture
  // never waits on a model. LLM explanations are fetched one alert at a time.
  const [explainers, setExplainers] = useState([])
  const [explainer, setExplainer] = useState('mock')
  activeView.current.explainer = explainer
  const explainerLabel = explainers.find((o) => o.kind === explainer)?.label ?? 'Offline control'
  const [appearance, setAppearance] = useState(
    () => document.documentElement.getAttribute('data-appearance') || 'pastel')
  const isPastel = appearance === 'pastel'
  const [themes, setThemes] = useState(() => ({
    original: document.documentElement.getAttribute('data-original-theme') || 'dark',
    pastel: document.documentElement.getAttribute('data-pastel-theme') || 'light',
  }))
  const theme = themes[appearance]

  useEffect(() => {
    api.explainers()
      .then((d) => { setExplainers(d.options); setExplainer(d.default) })
      .catch(() => setExplainers([]))
  }, [])

  const loadAll = useCallback(async (s, ticket, captureTicket, kind) => {
    const { coreDone } = loadAnalysisViews({
      loadCore: () => Promise.all([
        api.timeline(s.analysis_id), api.alerts(s.analysis_id, kind), api.metrics(s.analysis_id, kind),
      ]),
      loadIds: () => api.ids(s.analysis_id),
      isCurrent: () => generation.current === ticket,
      isIdsCurrent: () => captureGeneration.current === captureTicket,
      onCore: ([tl, al, rep]) => {
        setSummary(s); setTimeline(tl); setAlerts(al); setReport(rep)
        setSelected(al[0]?.alert_id ?? null)
      },
      onIds: (rows) => { setIds(rows); setIdsLoading(false) },
      onIdsError: (e) => { setIdsError(e.message); setIdsLoading(false) },
    })
    await coreDone
  }, [])

  const analyze = useCallback(async (request) => {
    const ticket = ++generation.current
    const captureTicket = ++captureGeneration.current
    stopScoring.current = true
    setBusy(true); setError(null); setDetail(null); setSelected(null)
    setSummary(null); setTimeline(null); setAlerts([]); setIds([]); setReport(null)
    setIdsLoading(true); setIdsError(null)
    setScoring(false); setProgress(null); setExplaining(false)
    try {
      await loadAll(await request(), ticket, captureTicket, explainer)
    } catch (e) {
      if (ticket === generation.current) { setError(e.message); setIdsLoading(false) }
    } finally {
      if (ticket === generation.current) setBusy(false)
    }
  }, [loadAll, explainer])

  const run = useCallback(() => analyze(() => api.analyzeSynthetic(params)), [params, analyze])
  const upload = useCallback((file, options) => analyze(() => api.uploadLog(file, params, options)), [params, analyze])

  useEffect(() => {
    if (!started.current) {
      started.current = true
      if (new URLSearchParams(window.location.search).get('dataset') === 'synthetic') run()
      else analyze(() => api.analyzeRealExample())
    }
  }, []) // open installed real ROAD traffic; synthetic demos remain available in settings

  useEffect(() => {
    setDetail(null); setExplaining(false)
    if (!summary || selected === null) return
    const abort = new AbortController()
    const id = summary.analysis_id
    ;(async () => {
      try {
        const d = await api.alert(id, selected, explainer, abort.signal)
        if (abort.signal.aborted) return
        setDetail(d)
        // The local control is instant. Hosted requests require the Explain action.
        if (d.explanation || explainer !== 'mock') return
        setExplaining(true)
        await api.explain(id, selected, { explainer })
        if (abort.signal.aborted) return
        const [next, al, rep] = await Promise.all([
          api.alert(id, selected, explainer, abort.signal),
          api.alerts(id, explainer, abort.signal), api.metrics(id, explainer),
        ])
        if (!abort.signal.aborted) { setDetail(next); setAlerts(al); setReport(rep) }
      } catch (e) {
        if (!abort.signal.aborted) setError(e.message)
      } finally {
        if (!abort.signal.aborted) setExplaining(false)
      }
    })()
    return () => abort.abort()
  }, [summary, selected, explainer])

  const reExplain = async () => {
    if (!summary || selected === null || scoring) return
    const ticket = generation.current
    const id = summary.analysis_id
    const alertId = selected
    setExplaining(true); setError(null)
    try {
      await api.explain(id, alertId, { explainer, force: !!detail?.explanation })
      const [next, al, rep] = await Promise.all([
        api.alert(id, alertId, explainer), api.alerts(id, explainer), api.metrics(id, explainer),
      ])
      if (ticket !== generation.current) return
      setAlerts(al); setReport(rep)
      if (activeView.current.selected === alertId) setDetail(next)
    } catch (e) {
      if (ticket === generation.current) setError(e.message)
    } finally {
      if (ticket === generation.current && activeView.current.selected === alertId) setExplaining(false)
    }
  }

  const changeExplainer = async (next) => {
    const ticket = ++generation.current
    stopScoring.current = true
    setExplainer(next); setDetail(null); setAlerts([]); setReport(null)
    setScoring(false); setProgress(null); setExplaining(false); setError(null)
    if (!summary) return
    try {
      const [al, rep] = await Promise.all([
        api.alerts(summary.analysis_id, next), api.metrics(summary.analysis_id, next),
      ])
      if (ticket === generation.current) { setAlerts(al); setReport(rep) }
    } catch (e) { if (ticket === generation.current) setError(e.message) }
  }

  const scoreAll = async () => {
    if (!summary || scoring || explaining) return
    const ticket = generation.current
    const id = summary.analysis_id
    const pending = alerts.filter((a) => !a.explanation)
    const cached = alerts.length - pending.length
    stopScoring.current = false
    setScoring(true); setError(null)
    setProgress({ done: cached, total: alerts.length, stopping: false })
    try {
      await runExplanationQueue({
        items: pending,
        isStopped: () => stopScoring.current,
        isCurrent: () => ticket === generation.current,
        explain: (alert) => api.explain(id, alert.alert_id, { explainer }),
        onResult: async (_alert, i) => {
          const [al, rep] = await Promise.all([api.alerts(id, explainer), api.metrics(id, explainer)])
          if (ticket !== generation.current) return
          setAlerts(al); setReport(rep)
          setProgress({ done: cached + i + 1, total: alerts.length, stopping: stopScoring.current })
          const active = activeView.current.selected
          if (active !== null) {
            const d = await api.alert(id, active, explainer)
            if (ticket === generation.current && activeView.current.selected === active) setDetail(d)
          }
        },
      })
    } catch (e) {
      if (ticket === generation.current) setError(e.message)
    } finally {
      if (ticket === generation.current) setScoring(false)
    }
  }

  const stopBatch = () => {
    stopScoring.current = true
    setProgress((p) => p ? { ...p, stopping: true } : p)
  }

  const m = report?.detection
  const outside = ids.filter((r) => !r.known).length
  const outsideNote = summary?.unknown_ids_count != null ? `${summary.unknown_ids_count} outside baseline`
    : idsLoading ? 'ID details loading…' : idsError ? 'ID details unavailable'
      : `${outside} outside baseline${summary && ids.length < summary.unique_ids ? ` among ${ids.length} displayed IDs` : ''}`

  const toggleTheme = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    setThemes((previous) => ({ ...previous, [appearance]: next }))
    document.documentElement.setAttribute('data-theme', next)
    document.documentElement.setAttribute(`data-${appearance}-theme`, next)
    try {
      localStorage.setItem(isPastel ? 'canalyst-pastel-theme' : 'canalyst-theme', next)
    } catch (e) { /* storage blocked */ }
    const url = new URL(window.location.href)
    url.searchParams.set('appearance', appearance)
    url.searchParams.set('theme', next)
    window.history.replaceState(null, '', url)
  }

  const changeAppearance = (next) => {
    setAppearance(next)
    document.documentElement.setAttribute('data-appearance', next)
    document.documentElement.setAttribute('data-theme', themes[next])
    try { localStorage.setItem('canalyst-appearance', next) } catch (e) { /* storage blocked */ }
    const url = new URL(window.location.href)
    url.searchParams.set('appearance', next)
    url.searchParams.set('theme', themes[next])
    window.history.replaceState(null, '', url)
  }

  const captureControls = (
    <>
      <Controls onRun={run} onUpload={upload} busy={busy} params={params} setParams={setParams} />
      {!isPastel && error ? <p role="alert" className="error" style={{ marginTop: 14, marginBottom: 0 }}>{error}</p> : null}
    </>
  )

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path d="M1 6h4l2-4 3 14 3-10 2 4h4" stroke="var(--accent)" strokeWidth="1.6"
                strokeLinejoin="round" strokeLinecap="round" />
            </svg>
          </div>
          <div>
            <h1>CAN<span>alyst</span></h1>
            <div className="sub">CAN bus attack analysis</div>
          </div>
        </div>
        <div className="status">
          <span className="cell"><span className={`led ${busy ? 'busy' : ''}`} />{busy ? 'analyzing' : 'ready'}</span>
          {summary ? (
            <>
              <span className="cell">{isPastel ? 'Source ' : 'src '}<b>{summary.source}</b></span>
              <span className="cell">{isPastel ? 'Detector ' : 'det '}<b>{summary.detector}</b></span>
              <span className="cell">baseline <b>{summary.baseline_source || `${fmt.num(summary.baseline_end, 0)}s`}</b></span>
            </>
          ) : null}
        </div>
        <div className="appearance-controls">
          <label htmlFor="explainer">Explainer</label>
          <select id="explainer" aria-label="Explainer" value={explainer} disabled={busy || scoring}
            onChange={(e) => changeExplainer(e.target.value)}>
            {(explainers.length ? explainers : [{ kind: 'mock', label: 'Offline control', available: true }])
              .map((o) => (
                <option key={o.kind} value={o.kind} disabled={!o.available}
                  title={o.detail}>
                  {o.label}{o.available ? '' : ' (unavailable)'}
                </option>
              ))}
          </select>
        </div>
        <div className="appearance-controls">
          <label htmlFor="appearance">Appearance</label>
          <select id="appearance" aria-label="Appearance" value={appearance} onChange={(e) => changeAppearance(e.target.value)}>
            <option value="original">Original</option>
            <option value="pastel">Pastel</option>
          </select>
        </div>
        <button className="icon-btn" onClick={toggleTheme}
          title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}>
          {theme === 'dark' ? (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
              <circle cx="8" cy="8" r="3.2" />
              <path d="M8 1v2M8 13v2M1 8h2M13 8h2M3 3l1.4 1.4M11.6 11.6 13 13M3 13l1.4-1.4M11.6 4.4 13 3" strokeLinecap="round" />
            </svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
              <path d="M13.5 9.5A5.5 5.5 0 0 1 6.5 2.5a5.5 5.5 0 1 0 7 7Z" strokeLinejoin="round" />
            </svg>
          )}
        </button>
      </header>

      <div className="layout">
        <aside className="panel rig reveal">
          {isPastel ? (
            <details className="capture-settings">
              <summary>
                <span className="capture-settings-title">Capture settings</span>
                <span className="capture-settings-description">Generate demo traffic or upload a log</span>
                <span className="capture-settings-action">Configure <span aria-hidden="true">＋</span></span>
              </summary>
              <div className="capture-settings-body">{captureControls}</div>
            </details>
          ) : <><h2>Capture</h2>{captureControls}</>}
          {isPastel && error ? <p role="alert" className="error">{error}</p> : null}
        </aside>

        <main>
          {isPastel ? (
            <div className="review-intro">
              <div>
                <p className="eyebrow">Capture review</p>
                <h2>Understand the alerts.</h2>
                <p>Select a detection to explore its explanation and supporting evidence.</p>
              </div>
              <AsciiCar />
              <div className="review-state" role="status">
                <span className={`led ${busy ? 'busy' : ''}`} />
                {busy ? 'Analyzing capture' : summary ? 'Analysis ready' : 'Waiting for a capture'}
              </div>
            </div>
          ) : <AsciiCar className="ascii-car-original" />}
          {summary ? (
            <section className="readouts reveal d1">
              <div className="kpis">
                <div className="kpi"><div className="label">Frames</div>
                  <div className="value">{summary.frame_count.toLocaleString()}</div>
                  <div className="note">{fmt.num(summary.duration_s, 0)}s capture</div></div>
                <div className="kpi"><div className="label">Bus load</div>
                  <div className="value">{fmt.num(summary.mean_rate, 0)}</div>
                  <div className="note">msg/s mean</div></div>
                <div className="kpi"><div className="label">Unique IDs</div>
                  <div className="value">{summary.unique_ids}</div>
                  <div className="note">{timeline ? outsideNote : ''}</div></div>
                <div className="kpi alert-kpi"><div className="label">Alerts</div>
                  <div className={`value ${summary.alert_count ? 'hot' : ''}`}>{summary.alert_count}</div>
                  <div className="note">{summary.window_count} windows scored{summary.timing_s?.total != null ? ` · ${fmt.num(summary.timing_s.total, 2)}s processing` : ''}</div></div>
                {m?.labeled ? (
                  <>
                    <div className="kpi"><div className="label">Precision / recall</div>
                      <div className="value small">{fmt.pct(m.precision)} / {fmt.pct(m.recall)}</div>
                      <div className="note">F1 {fmt.num(m.f1, 3)}</div></div>
                    <div className="kpi"><div className="label">Ground truth</div>
                      <div className="value small">{summary.metrics?.per_attack_type?.injected ? 'binary labels' : `${summary.attack_intervals.length} intervals`}</div>
                      <div className="note">{summary.metrics?.per_attack_type?.injected ? 'attack type unavailable' : [...new Set(summary.attack_intervals.map((i) => i.type))].join(', ')}</div></div>
                  </>
                ) : null}
              </div>
            </section>
          ) : null}

          <section className={`panel workspace reveal d2 ${busy ? 'loading' : ''}`}>
            <div className="tabs" role="tablist">
              {[['analysis', 'Analysis'], ['ids', 'Per-ID view'], ['metrics', 'Evaluation'], ['ask', 'Ask'],
                ['benchmark', 'Benchmark']]
                .map(([key, label], i) => (
                  <button key={key} className="tab" role="tab" aria-selected={tab === key}
                    onClick={() => setTab(key)}><span className="num">0{i + 1}</span>{label}</button>
                ))}
            </div>

            {scoring ? <div className="batch-status" role="status">
              <span>{progress?.done} / {progress?.total} alerts explained with {explainerLabel}.
                {progress?.stopping ? ' Stopping after the current request.' : ' You can continue reviewing this capture.'}</span>
              <button className="secondary" onClick={stopBatch} disabled={progress?.stopping}>Stop after current</button>
            </div> : null}
            {tab === 'analysis' ? (
              <div className="analysis-workspace">
                <div className="traffic-context">
                  {isPastel ? <div className="traffic-heading"><h3>Traffic context</h3><p>Message rate and detector score across the capture</p></div> : null}
                  <TimelineChart timeline={timeline} selectedAlert={selected} onSelectAlert={setSelected}
                    busy={busy} compact={isPastel} />
                </div>
                <div className="split" style={{ marginTop: isPastel ? 0 : 22 }}>
                  <div className="alerts-column">
                    <div className="section-title">Alerts {isPastel ? <span className="section-count">{alerts.length}</span> : null}</div>
                    {isPastel ? <p className="section-description">Select an alert to review</p> : null}
                    <AlertList alerts={alerts} selected={selected} onSelect={setSelected}
                      labeled={summary?.labeled} busy={busy} />
                  </div>
                  <div className="explanation-column">
                    <div className="section-title">Explanation and evidence</div>
                    <ExplanationPanel detail={detail} onReExplain={reExplain} busy={explaining} batchBusy={scoring} compact={isPastel}
                      explainerLabel={explainerLabel} slow={explainer !== 'mock'} />
                  </div>
                </div>
              </div>
            ) : null}

            {tab === 'ids' ? <IdView analysisId={summary?.analysis_id} ids={ids}
              loading={idsLoading} error={idsError} totalIds={summary?.unique_ids} /> : null}
            {tab === 'metrics' ? (
              <MetricsPanel report={report} explainer={explainer} explainerLabel={explainerLabel}
                alertCount={alerts.length} onScore={scoreAll} scoring={scoring} progress={progress} onStop={stopBatch} explaining={explaining} />
            ) : null}
            {tab === 'ask' ? <AskPanel analysisId={summary?.analysis_id} explainer={explainer} /> : null}
            {tab === 'benchmark' ? <BenchmarkPanel /> : null}
          </section>
        </main>
      </div>

      <footer className="foot">
        CANalyst, CPSC 8580 course project. Detection is statistical; classification and
        explanation come from the configured explainer. Citations link claims to measurements; their validity does not establish that a claim or attack label is correct.
      </footer>
    </div>
  )
}
