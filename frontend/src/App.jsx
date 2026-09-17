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
  const [theme, setTheme] = useState(null)

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

  return (
    <div className="app">
      <header className="top">
        <div>
          <h1>CANalyst</h1>
          <div className="sub">LLM-assisted analysis of CAN bus attacks</div>
        </div>
        <div className="row">
          {summary ? (
            <span className="small muted">
              source: {summary.source} | detector: {summary.detector} | baseline learned from the
              first {fmt.num(summary.baseline_end, 0)}s
            </span>
          ) : null}
          <button className="secondary" onClick={() => {
            const next = theme === 'dark' ? 'light' : 'dark'
            setTheme(next)
            document.documentElement.setAttribute('data-theme', next)
          }}>{theme === 'dark' ? 'Light' : 'Dark'} theme</button>
        </div>
      </header>

      <div className="card">
        <h2>Capture</h2>
        <Controls onRun={run} onUpload={upload} busy={busy} params={params} setParams={setParams} />
        {error ? <p className="error" style={{ marginTop: 12 }}>{error}</p> : null}
      </div>

      {summary ? (
        <div className="card">
          <h2>Overview</h2>
          <div className="kpis">
            <div className="kpi"><div className="label">Frames</div>
              <div className="value">{summary.frame_count.toLocaleString()}</div>
              <div className="note">{fmt.num(summary.duration_s, 0)}s capture</div></div>
            <div className="kpi"><div className="label">Mean bus load</div>
              <div className="value">{fmt.num(summary.mean_rate, 0)}</div>
              <div className="note">msg/s</div></div>
            <div className="kpi"><div className="label">Unique IDs</div>
              <div className="value">{summary.unique_ids}</div>
              <div className="note">{timeline ? `${ids.filter((r) => !r.known).length} outside baseline` : ''}</div></div>
            <div className="kpi"><div className="label">Alerts</div>
              <div className="value">{summary.alert_count}</div>
              <div className="note">{summary.window_count} windows scored</div></div>
            {m?.labeled ? (
              <>
                <div className="kpi"><div className="label">Precision / recall</div>
                  <div className="value small">{fmt.pct(m.precision)} / {fmt.pct(m.recall)}</div>
                  <div className="note">F1 {fmt.num(m.f1, 3)}</div></div>
                <div className="kpi"><div className="label">Ground truth</div>
                  <div className="value small">{summary.attack_intervals.length} intervals</div>
                  <div className="note">{summary.attack_intervals.map((i) => i.type).join(', ')}</div></div>
              </>
            ) : null}
          </div>
        </div>
      ) : null}

      <div className="card">
        <div className="tabs">
          {[['analysis', 'Analysis'], ['ids', 'Per-ID view'], ['metrics', 'Evaluation'], ['ask', 'Ask']]
            .map(([key, label]) => (
              <button key={key} className="tab" aria-selected={tab === key}
                onClick={() => setTab(key)}>{label}</button>
            ))}
        </div>

        {tab === 'analysis' ? (
          <>
            <TimelineChart timeline={timeline} selectedAlert={selected} onSelectAlert={setSelected} />
            <div className="split" style={{ marginTop: 16 }}>
              <div>
                <h2>Alerts</h2>
                <AlertList alerts={alerts} selected={selected} onSelect={setSelected}
                  labeled={summary?.labeled} />
              </div>
              <div>
                <h2>Explanation and evidence</h2>
                <ExplanationPanel detail={detail} onReExplain={reExplain} busy={explaining} />
              </div>
            </div>
          </>
        ) : null}

        {tab === 'ids' ? <IdView analysisId={summary?.analysis_id} ids={ids} /> : null}
        {tab === 'metrics' ? <MetricsPanel report={report} /> : null}
        {tab === 'ask' ? <AskPanel analysisId={summary?.analysis_id} /> : null}
      </div>

      <p className="small muted">
        CANalyst, CPSC 8580 course project. Detection is statistical; classification and
        explanation come from the configured explainer. Every claim links to the measurement
        behind it, so nothing has to be taken on trust.
      </p>
    </div>
  )
}
