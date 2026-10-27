import { useCallback, useEffect, useState } from 'react'
import { api, fmt } from './api'
import AlertList from './components/AlertList'
import AskPanel from './components/AskPanel'
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
  const [report, setReport] = useState(null)
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)
  const [explaining, setExplaining] = useState(false)
  const [tab, setTab] = useState('analysis')
  const [appearance, setAppearance] = useState(
    () => document.documentElement.getAttribute('data-appearance') || 'pastel')
  const isPastel = appearance === 'pastel'
  const [themes, setThemes] = useState(() => ({
    original: document.documentElement.getAttribute('data-original-theme') || 'dark',
    pastel: document.documentElement.getAttribute('data-pastel-theme') || 'light',
  }))
  const theme = themes[appearance]

  const loadAll = useCallback(async (analysisId) => {
    const [tl, al, idRows, rep] = await Promise.all([
      api.timeline(analysisId),
      api.alerts(analysisId),
      api.ids(analysisId),
      api.metrics(analysisId),
    ])
    setTimeline(tl)
    setAlerts(al)
    setIds(idRows)
    setReport(rep)
    // Metrics generates every explanation, so refresh the alert list to pick them up.
    setAlerts(await api.alerts(analysisId))
    if (al.length) setSelected(al[0].alert_id)
  }, [])

  const run = useCallback(async () => {
    setBusy(true); setError(null); setDetail(null); setSelected(null)
    try {
      const s = await api.analyzeSynthetic(params)
      setSummary(s)
      await loadAll(s.analysis_id)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }, [params, loadAll])

  const upload = useCallback(async (file) => {
    setBusy(true); setError(null); setDetail(null); setSelected(null)
    try {
      const s = await api.uploadLog(file, params.detector)
      setSummary(s)
      await loadAll(s.analysis_id)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }, [params.detector, loadAll])

  useEffect(() => { run() }, []) // analyze once on load so the page is never empty

  useEffect(() => {
    if (!summary || selected === null) { setDetail(null); return }
    let live = true
    api.alert(summary.analysis_id, selected)
      .then((d) => { if (live) setDetail(d) })
      .catch((e) => setError(e.message))
    return () => { live = false }
  }, [summary, selected])

  const reExplain = async () => {
    if (!summary || selected === null) return
    setExplaining(true)
    try {
      await api.explain(summary.analysis_id, selected, { force: true })
      setDetail(await api.alert(summary.analysis_id, selected))
      setAlerts(await api.alerts(summary.analysis_id))
    } catch (e) {
      setError(e.message)
    } finally {
      setExplaining(false)
    }
  }

  const m = report?.detection
  const outside = ids.filter((r) => !r.known).length

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
              <span className="cell">baseline <b>{fmt.num(summary.baseline_end, 0)}s</b></span>
            </>
          ) : null}
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
              <div className="review-state" role="status">
                <span className={`led ${busy ? 'busy' : ''}`} />
                {busy ? 'Analyzing capture' : summary ? 'Analysis ready' : 'Waiting for a capture'}
              </div>
            </div>
          ) : null}
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
                  <div className="note">{timeline ? `${outside} outside baseline` : ''}</div></div>
                <div className="kpi alert-kpi"><div className="label">Alerts</div>
                  <div className={`value ${summary.alert_count ? 'hot' : ''}`}>{summary.alert_count}</div>
                  <div className="note">{summary.window_count} windows scored</div></div>
                {m?.labeled ? (
                  <>
                    <div className="kpi"><div className="label">Precision / recall</div>
                      <div className="value small">{fmt.pct(m.precision)} / {fmt.pct(m.recall)}</div>
                      <div className="note">F1 {fmt.num(m.f1, 3)}</div></div>
                    <div className="kpi"><div className="label">Ground truth</div>
                      <div className="value small">{summary.attack_intervals.length} intervals</div>
                      <div className="note">{[...new Set(summary.attack_intervals.map((i) => i.type))].join(', ')}</div></div>
                  </>
                ) : null}
              </div>
            </section>
          ) : null}

          <section className={`panel workspace reveal d2 ${busy ? 'loading' : ''}`}>
            <div className="tabs" role="tablist">
              {[['analysis', 'Analysis'], ['ids', 'Per-ID view'], ['metrics', 'Evaluation'], ['ask', 'Ask']]
                .map(([key, label], i) => (
                  <button key={key} className="tab" role="tab" aria-selected={tab === key}
                    onClick={() => setTab(key)}><span className="num">0{i + 1}</span>{label}</button>
                ))}
            </div>

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
                    <ExplanationPanel detail={detail} onReExplain={reExplain} busy={explaining} compact={isPastel} />
                  </div>
                </div>
              </div>
            ) : null}

            {tab === 'ids' ? <IdView analysisId={summary?.analysis_id} ids={ids} /> : null}
            {tab === 'metrics' ? <MetricsPanel report={report} /> : null}
            {tab === 'ask' ? <AskPanel analysisId={summary?.analysis_id} /> : null}
          </section>
        </main>
      </div>

      <footer className="foot">
        CANalyst, CPSC 8580 course project. Detection is statistical; classification and
        explanation come from the configured explainer. Every claim links to the measurement
        behind it, so nothing has to be taken on trust.
      </footer>
    </div>
  )
}
