import { useEffect, useMemo, useRef, useState } from 'react'
import { api, fmt } from '../api'

/* Saved real-data runs, side by side. Everything here is read from the
   result files the evaluation harness wrote; opening this tab never calls a
   model, so it is safe to show in a demo with no network. */

const FILTERS = [
  ['all', 'All alerts'],
  ['ai-wrong', 'LLM wrong'],
  ['disagree', 'Explainers disagree'],
  ['false-alarm', 'False alarms'],
]

const isAttack = (a) => a.true_type && a.true_type !== 'normal'
const secs = (v) => (v === null || v === undefined ? 'n/a' : `${Math.round(v)} s`)

function Prediction({ alert, result }) {
  if (!result) return <span className="muted">n/a</span>
  const cls = isAttack(alert) ? (result.attack_type === alert.true_type ? 'match' : 'mismatch')
    : (result.attack_type === 'benign' ? 'match' : '')
  return <span className={`badge ${cls}`}>{result.attack_type}</span>
}

export default function BenchmarkPanel() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [dsKey, setDsKey] = useState(null)
  const [filter, setFilter] = useState('all')
  const [open, setOpen] = useState(null)
  const detailRef = useRef(null)

  useEffect(() => {
    api.benchmark()
      .then((d) => { setData(d); setDsKey(d.datasets[0]?.key ?? null) })
      .catch((e) => setError(e.message))
  }, [])

  const ds = data?.datasets.find((d) => d.key === dsKey)
  const runs = ds?.runs ?? []
  const llms = runs.filter((r) => r.explainer !== 'mock')

  const byType = useMemo(() => {
    if (!ds) return []
    const types = [...new Set(ds.alerts.filter(isAttack).map((a) => a.true_type))].sort()
    return types.map((t) => {
      const rows = ds.alerts.filter((a) => a.true_type === t)
      return {
        type: t,
        n: rows.length,
        correct: Object.fromEntries(runs.map((r) => [r.id,
          rows.filter((a) => a.results[r.id]?.attack_type === t).length])),
      }
    })
  }, [ds, runs])

  const rows = useMemo(() => {
    if (!ds) return []
    return ds.alerts.filter((a) => {
      if (filter === 'false-alarm') return !isAttack(a)
      if (filter === 'ai-wrong') {
        return isAttack(a) && llms.some((r) => a.results[r.id]?.attack_type !== a.true_type)
      }
      if (filter === 'disagree') {
        return new Set(runs.map((r) => a.results[r.id]?.attack_type)).size > 1
      }
      return true
    })
  }, [ds, filter, runs, llms])

  useEffect(() => {
    if (open) detailRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [open])

  if (error) return <p className="error">Could not load saved results: {error}</p>
  if (!data) return <p className="muted">Loading saved results...</p>
  if (!ds) {
    return (
      <p className="muted">
        No saved runs yet. Run <span className="mono">scripts.evaluate_midterm --explainer</span> to
        create one.
      </p>
    )
  }

  const chosen = rows.find((a) => `${a.capture}-${a.alert_id}` === open)
  const attacks = ds.alerts.filter(isAttack).length
  const falseAlarms = ds.alerts.length - attacks
  const commit = llms.find((r) => r.git?.commit)?.git.commit

  return (
    <div className="benchmark">
      <div className="benchmark-head">
        <div>
          <h3>Saved benchmark</h3>
          <p className="small muted">
            Read-only results from the evaluation harness. The same detected alerts, explained by
            each explainer; loading this tab makes no model calls.
          </p>
        </div>
        <div className="chips" role="group" aria-label="Dataset">
          {data.datasets.map((d) => (
            <button key={d.key} type="button" className="chip" aria-pressed={d.key === dsKey}
              onClick={() => { setDsKey(d.key); setOpen(null) }}>{d.label}</button>
          ))}
        </div>
      </div>

      <div className="kpis" style={{ marginBottom: 16 }}>
        {runs.map((r) => (
          <div className="kpi" key={r.id}>
            <div className="label">{r.label}</div>
            <div className="value">{fmt.pct(r.summary.classification.accuracy)}</div>
            <div className="note">
              {byType.reduce((s, t) => s + t.correct[r.id], 0)} of {attacks} attack alerts correct
            </div>
          </div>
        ))}
        <div className="kpi">
          <div className="label">Alerts explained</div>
          <div className="value">{ds.alerts.length}</div>
          <div className="note">{attacks} attacks, {falseAlarms} false alarms</div>
        </div>
      </div>

      <div className="benchmark-grid">
        <div>
          <h3>Comparison</h3>
          <table>
            <thead>
              <tr><th className="left">measure</th>{runs.map((r) => <th key={r.id}>{r.label}</th>)}</tr>
            </thead>
            <tbody>
              <tr><td className="left">Accuracy on attack alerts</td>
                {runs.map((r) => <td key={r.id}>{fmt.pct(r.summary.classification.accuracy)}</td>)}</tr>
              <tr><td className="left">Grounded, as run</td>
                {runs.map((r) => <td key={r.id}>{fmt.pct(r.summary_as_run.grounding.grounded_rate)}</td>)}</tr>
              <tr><td className="left">Grounded, after E0 rescore</td>
                {runs.map((r) => <td key={r.id}>{fmt.pct(r.summary.grounding.grounded_rate)}</td>)}</tr>
              <tr><td className="left">False alarms called benign</td>
                {runs.map((r) => <td key={r.id}>{r.summary.false_alarms_called_benign} of {r.summary.false_alarms}</td>)}</tr>
              <tr><td className="left">Fallbacks to the control</td>
                {runs.map((r) => <td key={r.id}>{r.explainer === 'mock' ? 'n/a' : r.summary.fallbacks}</td>)}</tr>
              <tr><td className="left">Median / slowest per alert</td>
                {runs.map((r) => (
                  <td key={r.id}>{r.explainer === 'mock' ? 'instant'
                    : `${secs(r.summary.latency_s_median)} / ${secs(r.summary.latency_s_max)}`}</td>
                ))}</tr>
            </tbody>
          </table>
        </div>
        <div>
          <h3>Correct by attack type</h3>
          <table>
            <thead>
              <tr><th className="left">true type</th><th>alerts</th>
                {runs.map((r) => <th key={r.id}>{r.label}</th>)}</tr>
            </thead>
            <tbody>
              {byType.map((t) => (
                <tr key={t.type}>
                  <td className="left">{t.type}</td><td>{t.n}</td>
                  {runs.map((r) => (
                    <td key={r.id}>
                      <span className={`badge ${t.correct[r.id] === t.n ? 'match' : t.correct[r.id] ? '' : 'mismatch'}`}>
                        {t.correct[r.id]} / {t.n}
                      </span>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="benchmark-alerts-head">
        <h3>Alerts</h3>
        <div className="chips" role="group" aria-label="Filter alerts">
          {FILTERS.map(([key, label]) => (
            <button key={key} type="button" className="chip" aria-pressed={filter === key}
              onClick={() => { setFilter(key); setOpen(null) }}>{label}</button>
          ))}
        </div>
        <span className="small muted">{rows.length} shown. Select a row for the model's reasoning.</span>
      </div>
      <div className="scroll benchmark-table">
        <table>
          <thead>
            <tr>
              <th className="left">capture</th><th className="left">window</th>
              <th className="left">true type</th>
              {runs.map((r) => <th key={r.id} className="left">{r.label}</th>)}
              {llms.map((r) => <th key={`${r.id}-t`}>time</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => {
              const key = `${a.capture}-${a.alert_id}`
              const selected = open === key
              const toggle = () => setOpen(selected ? null : key)
              return (
                <tr key={key} className={`benchmark-row ${selected ? 'highlight' : ''}`} tabIndex={0}
                  aria-selected={selected} onClick={toggle}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle() } }}>
                  <td className="left mono small">{a.capture.replace(/_dataset$/, '')} · #{a.alert_id}</td>
                  <td className="left mono small">{fmt.sec(a.start)} to {fmt.sec(a.end)}</td>
                  <td className="left">{isAttack(a) ? a.true_type : <span className="muted">false alarm</span>}</td>
                  {runs.map((r) => <td key={r.id} className="left"><Prediction alert={a} result={a.results[r.id]} /></td>)}
                  {llms.map((r) => <td key={`${r.id}-t`} className="mono small">{secs(a.results[r.id]?.latency_s)}</td>)}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {chosen ? <AlertReasoning alert={chosen} runs={runs} llms={llms} panelRef={detailRef}
        onClose={() => setOpen(null)} /> : null}

      <p className="small muted" style={{ marginTop: 14 }}>
        Detector frozen{commit ? <> at <span className="mono">{commit.slice(0, 7)}</span></> : null};
        temperature {llms[0]?.temperature ?? 'n/a'}. Accuracy counts alerts on labeled attack frames;
        false alarms are excluded. {runs.find((r) => r.rescore_method)?.rescore_method}
        {' '}Sources: {runs.map((r) => r.source).join(', ')}.
      </p>
    </div>
  )
}

function AlertReasoning({ alert, runs, llms, panelRef, onClose }) {
  const control = alert.results[runs[0].id]
  return (
    <section className="benchmark-detail-panel" ref={panelRef} aria-label="Selected alert reasoning">
      <div className="explain-head">
        <h3>
          {alert.capture.replace(/_dataset$/, '')} · alert {alert.alert_id}
          <span className="mono">{fmt.sec(alert.start)} to {fmt.sec(alert.end)}</span>
        </h3>
        <div className="spacer" />
        <span className="badge">true type: {isAttack(alert) ? alert.true_type : 'false alarm'}</span>
        <button className="secondary" type="button" onClick={onClose}>Close</button>
      </div>
      {llms.map((r) => {
        const res = alert.results[r.id]
        if (!res) return null
        return (
          <div key={r.id} className="benchmark-reasoning">
            <div className="row" style={{ margin: '12px 0 8px', flexWrap: 'wrap' }}>
              <strong>{r.label}</strong>
              <Prediction alert={alert} result={res} />
              <span className="badge">confidence {fmt.pct(res.confidence)}</span>
              <span className={`badge ${res.grounded ? 'ok' : 'mismatch'}`}>
                <span className="dot" />{res.grounded ? 'all claims cited' : 'uncited claims'}
                {res.grounded !== res.grounded_as_run ? ' after E0 rescore' : ''}
              </span>
              <span className="badge">{secs(res.latency_s)}</span>
            </div>
            <p className="benchmark-summary">{res.summary}</p>
            <ul className="claims">
              {(res.claims ?? []).map((c, i) => (
                <li key={i}>
                  {c.text}
                  {(c.cites ?? []).map((id) => <span key={id} className="cite">{id}</span>)}
                </li>
              ))}
            </ul>
            {res.recommended_action ? (
              <div className="action"><strong>Next step</strong><br />{res.recommended_action}</div>
            ) : null}
            {res.raw_response ? (
              <details className="evidence-disclosure">
                <summary>Raw model reply</summary>
                <pre className="raw-reply">{res.raw_response}</pre>
              </details>
            ) : null}
          </div>
        )
      })}
      {control ? (
        <div className="benchmark-reasoning">
          <div className="row" style={{ margin: '12px 0 8px', flexWrap: 'wrap' }}>
            <strong>{runs[0].label}</strong>
            <Prediction alert={alert} result={control} />
          </div>
          <p className="benchmark-summary">{control.summary}</p>
        </div>
      ) : null}
    </section>
  )
}

