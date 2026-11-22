import { useEffect, useMemo, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, ErrorBar, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api } from '../api'

/* Saved benchmark results: how detectors and explainers compare on the
   frozen evaluation sets. Nothing here is computed in the browser beyond
   formatting; every number comes from the scripts' saved output. */

const AXIS = { stroke: 'var(--axis)', tick: { fill: 'var(--text-secondary)', fontSize: 10.5, fontFamily: 'IBM Plex Mono, monospace' } }
const TIP = { background: 'var(--surface-1)', border: '1px solid var(--border-strong)', borderRadius: 4, fontSize: 12, fontFamily: 'IBM Plex Mono, monospace' }

const SET_INFO = {
  heldout: 'Held-out set: 70 Car-Hacking attack alerts and seven ROAD false alarms. It contains no ROAD attack alerts.',
  midterm100: 'The 100 alerts of the October 21 run. Prompt v2 and control rules v2 were developed on these, so treat gains here as development results.',
}

export function runLabel(run, meta = {}) {
  if (run.startsWith('submitted-')) return `${run.slice(10)} (submitted)`
  const m = run.match(/^control-(v\d)_(alert|window)$/)
  if (m) return `Rule control ${m[1]}${m[2] === 'window' ? ', pre-fix evidence' : ''}`
  const abl = run.match(/^(.*)_v2-dosv1_alert$/)
  if (abl) return `${abl[1]} (v2, Oct 21 DoS line)`
  const r = run.match(/^(.*)_(v\d)_(alert|window)$/)
  if (r) {
    const legacy = r[2] === 'v1' || r[3] === 'window'
    return legacy ? `${r[1]} (Oct 21 prompt${r[3] === 'window' ? ', pre-fix evidence' : ''})` : r[1]
  }
  return meta.model || run
}

const pct = (v, d = 0) => (v === null || v === undefined ? 'n/a' : `${(v * 100).toFixed(d)}%`)
const ci = (p) => (p && p.n ? `${pct(p.value)} (${p.k}/${p.n})` : 'n/a')
const ciRange = (p) => (p && p.n ? `${pct(p.lo)} to ${pct(p.hi)}` : '')

function Shade({ p, children }) {
  // One-hue sequential encoding for accuracy cells; text stays in ink colors.
  if (!p || !p.n) return <td className="muted">n/a</td>
  const strength = Math.round(8 + p.value * 40)
  return (
    <td style={{ background: `color-mix(in oklab, var(--series-1) ${strength}%, transparent)` }}
      title={`95% interval ${ciRange(p)}`}>{children ?? ci(p)}</td>
  )
}

/* ---------------------------------------------------------------- explainers */

export function ExplainerSection({ data }) {
  const sets = Object.keys(data)
  const [setName, setSetName] = useState(sets.includes('heldout') ? 'heldout' : sets[0])
  const s = data[setName]
  const runs = useMemo(() => Object.entries(s?.runs ?? {})
    .sort((a, b) => (b[1].accuracy?.all?.value ?? 0) - (a[1].accuracy?.all?.value ?? 0)), [s])
  const [a, setA] = useState('')
  const [b, setB] = useState('')
  useEffect(() => {
    const names = runs.map(([n]) => n)
    const control = names.find((n) => n.startsWith('control-v2')) || names[0]
    setA(control)
    setB(names.find((n) => n !== control) || '')
  }, [setName, runs])

  if (!s) return <p className="muted">No explainer runs scored yet.</p>
  const types = [...new Set(runs.flatMap(([, r]) => Object.keys(r.accuracy_by_type || {})))].sort()
  const chart = runs.filter(([, r]) => r.accuracy.all.n > 0).map(([n, r]) => ({
    name: runLabel(n, r), value: r.accuracy.all.value,
    err: [r.accuracy.all.value - r.accuracy.all.lo, r.accuracy.all.hi - r.accuracy.all.value],
    k: r.accuracy.all.k, n: r.accuracy.all.n,
  }))

  return (
    <div className="bench-block">
      <div className="bench-head">
        <h3>Explainers: which labels and explanations hold up</h3>
        <select value={setName} onChange={(e) => setSetName(e.target.value)} aria-label="Alert set">
          {sets.map((x) => <option key={x} value={x}>{x} ({data[x].alerts} alerts)</option>)}
        </select>
      </div>
      <p className="small muted">{SET_INFO[setName] || ''} Every explainer saw the same frozen
        evidence packets. A failed or empty reply counts as wrong.</p>

      <div className="legend"><span className="key muted">Attack-label accuracy with 95% Wilson intervals</span></div>
      <div className="table-scroll" tabIndex={0} role="region" aria-label="Accuracy chart">
      <div className="bench-chart">
      <ResponsiveContainer width="100%" height={46 + chart.length * 30}>
        <BarChart data={chart} layout="vertical" margin={{ top: 4, right: 56, bottom: 4, left: 8 }}>
          <CartesianGrid stroke="var(--grid)" strokeDasharray="2 4" horizontal={false} />
          <XAxis type="number" domain={[0, 1]} {...AXIS} tickFormatter={(v) => `${v * 100}%`} />
          <YAxis type="category" dataKey="name" width={230} {...AXIS} />
          <Tooltip contentStyle={TIP} formatter={(v, _n, p) => [`${(v * 100).toFixed(1)}% (${p.payload.k}/${p.payload.n})`, 'accuracy']} />
          <Bar dataKey="value" fill="var(--series-1)" radius={[0, 2, 2, 0]} barSize={14} isAnimationActive={false}>
            <ErrorBar dataKey="err" width={5} strokeWidth={1.4} stroke="var(--text-secondary)" direction="x" />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      </div>
      </div>

      <div className="table-scroll" tabIndex={0} role="region" aria-label="Explainer results">
        <table>
          <thead><tr>
            <th className="left">explainer</th>
            {s.datasets.map((d) => <th key={d}>{d === 'hcrl' ? 'Car-Hacking' : d.toUpperCase()}</th>)}
            <th>no answer</th><th>false alarms called benign</th><th>claims citing real evidence</th>
            <th>median latency</th><th>median output tokens</th>
          </tr></thead>
          <tbody>
            {runs.map(([n, r]) => (
              <tr key={n}>
                <td className="left">{runLabel(n, r)}</td>
                {s.datasets.map((d) => <Shade key={d} p={r.accuracy[d]} />)}
                <td>{r.no_answer ?? 0}</td>
                <td>{ci(r.false_alarms_called_benign)}</td>
                <td>{ci(r.claims_with_valid_citations)}</td>
                <td>{r.latency_s ? `${r.latency_s.median.toFixed(1)} s` : 'n/a'}</td>
                <td>{r.completion_tokens ? r.completion_tokens.median.toLocaleString() : 'n/a'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>Accuracy by true attack type</h3>
      <div className="table-scroll" tabIndex={0} role="region" aria-label="Attack type accuracy">
        <table>
          <thead><tr><th className="left">explainer</th>{types.map((t) => <th key={t}>{t.replace('hcrl/', 'Car-Hacking ').replace('road/', 'ROAD ')}</th>)}</tr></thead>
          <tbody>
            {runs.map(([n, r]) => (
              <tr key={n}><td className="left">{runLabel(n, r)}</td>
                {types.map((t) => <Shade key={t} p={r.accuracy_by_type?.[t]} />)}</tr>
            ))}
          </tbody>
        </table>
      </div>

      <PairMatrix pairs={s.pairs} runs={runs} />
      <Disagreements setName={setName} runs={runs} a={a} b={b} setA={setA} setB={setB} />
    </div>
  )
}

function PairMatrix({ pairs, runs }) {
  const names = runs.map(([n]) => n)
  const cell = (x, y) => {
    const fwd = pairs[`${x} vs ${y}`]?.all
    const rev = pairs[`${y} vs ${x}`]?.all
    if (fwd) return { diff: (fwd.a_correct - fwd.b_correct) / fwd.n, p: fwd.mcnemar_p, n: fwd.n }
    if (rev) return { diff: (rev.b_correct - rev.a_correct) / rev.n, p: rev.mcnemar_p, n: rev.n }
    return null
  }
  return (
    <>
      <h3>Paired accuracy comparisons</h3>
      <p className="small muted">Row minus column accuracy on shared alert records, with the exact
        McNemar p-value. Failed or missing predictions count as wrong. Tinted cells have p below 0.05.</p>
      <div className="table-scroll" tabIndex={0} role="region" aria-label="Paired comparisons">
        <table className="pair-matrix">
          <thead><tr><th className="left">row vs column</th>{names.map((n) => <th key={n}>{runLabel(n)}</th>)}</tr></thead>
          <tbody>
            {names.map((x) => (
              <tr key={x}><td className="left">{runLabel(x)}</td>
                {names.map((y) => {
                  if (x === y) return <td key={y} className="muted">·</td>
                  const c = cell(x, y)
                  if (!c) return <td key={y} className="muted">n/a</td>
                  const sig = c.p < 0.05
                  return (
                    <td key={y} className={sig ? (c.diff > 0 ? 'sig-up' : 'sig-down') : ''}
                      title={`n = ${c.n}, p = ${c.p.toFixed(4)}`}>
                      {c.diff > 0 ? '+' : ''}{(c.diff * 100).toFixed(0)} pts
                      <span className="pval">p {c.p < 0.0001 ? '< 0.0001' : c.p.toFixed(3)}</span>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

function Disagreements({ setName, runs, a, b, setA, setB }) {
  const [data, setData] = useState(null)
  const [open, setOpen] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    setData(null)
    setOpen(null)
    setError(null)
    if (!a || !b || a === b) { setData(null); return }
    let live = true
    api.benchmarkCompare(setName, a, b).then((d) => { if (live) { setData(d); setOpen(null) } })
      .catch((e) => live && setError(e.message))
    return () => { live = false }
  }, [setName, a, b])
  const names = runs.map(([n]) => n)
  return (
    <>
      <h3>Where two explainers disagree</h3>
      <div className="bench-controls">
        <select value={a} onChange={(e) => setA(e.target.value)} aria-label="First explainer">
          {names.map((n) => <option key={n} value={n}>{runLabel(n)}</option>)}
        </select>
        <span className="muted">versus</span>
        <select value={b} onChange={(e) => setB(e.target.value)} aria-label="Second explainer">
          {names.map((n) => <option key={n} value={n}>{runLabel(n)}</option>)}
        </select>
        {data ? <span className="small muted">{data.total} alert(s) where exactly one is right, or false alarms labeled differently</span> : null}
      </div>
      {error ? <p className="error" role="alert">{error}</p> : null}
      {!error && !data && a && b && a !== b ? <p role="status">Loading comparison...</p> : null}
      {data && data.alerts.length === 0 ? <p className="muted">These two agree on every alert.</p> : null}
      <div className="disagree-list">
        {data?.alerts.map((al) => (
          <div key={al.id} className={`disagree ${open === al.id ? 'open' : ''}`}>
            <button className="disagree-row" onClick={() => setOpen(open === al.id ? null : al.id)}
              aria-expanded={open === al.id}>
              <span className="mono">{al.id}</span>
              <span>{al.dataset === 'hcrl' ? 'Car-Hacking' : 'ROAD'}</span>
              <span>truth: <b>{al.true_type}</b></span>
              <span className={`badge ${al.a.correct ? 'match' : 'mismatch'}`}>{al.a.label}</span>
              <span className={`badge ${al.b.correct ? 'match' : 'mismatch'}`}>{al.b.label}</span>
            </button>
            {open === al.id ? (
              <div className="disagree-body">
                <div className="evidence-col">
                  <div className="section-title">Evidence both saw</div>
                  {al.evidence.map((e) => <p key={e.id} className="small"><span className="mono">{e.id}</span> {e.text}</p>)}
                </div>
                {[['a', a], ['b', b]].map(([k, run]) => (
                  <div key={k} className="reply-col">
                    <div className="section-title">{runLabel(run)}: {al[k].label}</div>
                    {al[k].error ? <p className="small error">{al[k].error}</p> : null}
                    {al[k].summary ? <p className="small">{al[k].summary}</p> : null}
                    <ul className="small">
                      {al[k].claims.map((c, i) => (
                        <li key={i}>{c.text} <span className="mono muted">{(c.cites || []).join(' ')}</span></li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </>
  )
}

/* ----------------------------------------------------------------- detection */

const DETECTOR_LABELS = {
  'rule@0.55': 'Rule detector v1 (six components)',
  'rule_v2@0.55': 'Rule detector v2 (three components)',
  'rule@tuned': 'Rule detector v1, tuned threshold',
  id_whitelist: 'ID whitelist',
  interval: 'Message interval',
  whitelist_interval: 'ID whitelist + message interval',
  id_entropy: 'ID entropy',
  iforest: 'IsolationForest',
  ocsvm: 'One-class SVM',
}

export function DetectionSection({ data }) {
  const [dsName, setDsName] = useState(data.datasets[0]?.dataset)
  const ds = data.datasets.find((d) => d.dataset === dsName)
  const refs = Object.keys(ds?.references ?? {})
  const [ref, setRef] = useState(refs.includes('pooled') ? 'pooled' : refs[0])
  useEffect(() => { setRef(refs.includes('pooled') ? 'pooled' : refs[0]) }, [dsName]) // eslint-disable-line
  const r = ds?.references?.[ref]
  if (!r) return null
  const rows = Object.entries(r.detectors).sort((x, y) => (y[1].f1.value || 0) - (x[1].f1.value || 0))
  const types = [...new Set(rows.flatMap(([, v]) => Object.keys(v.recall_by_type || {})))].sort()
  const iv = (m) => `${m.value.toFixed(3)}`
  return (
    <div className="bench-block">
      <div className="bench-head">
        <h3>Detectors: held-out captures only</h3>
        <div className="bench-controls">
          <select value={dsName} onChange={(e) => setDsName(e.target.value)} aria-label="Dataset">
            {data.datasets.map((d) => <option key={d.dataset} value={d.dataset}>{d.dataset === 'hcrl' ? 'Car-Hacking' : 'ROAD'}</option>)}
          </select>
          {refs.length > 1 ? (
            <select value={ref} onChange={(e) => setRef(e.target.value)} aria-label="Reference">
              {refs.map((x) => <option key={x} value={x}>{x === 'pooled' ? 'pooled reference' : 'single reference'}</option>)}
            </select>
          ) : null}
        </div>
      </div>
      <p className="small muted">{ds.split.evaluation.windows.toLocaleString()} evaluation windows
        ({ds.split.evaluation.attack_windows.toLocaleString()} attack) from captures no threshold or rule was
        fitted on. Reference: {r.reference_captures.length} attack-free capture(s), {Math.round(r.reference_seconds).toLocaleString()} s.
        Hover a value for its 95% block-bootstrap interval.</p>
      <div className="table-scroll" tabIndex={0} role="region" aria-label="Detector results">
        <table>
          <thead><tr><th className="left">detector</th><th>precision</th><th>recall</th><th>F1</th>
            <th>false-positive rate</th><th>AUROC</th></tr></thead>
          <tbody>
            {rows.map(([k, v]) => (
              <tr key={k}>
                <td className="left">{DETECTOR_LABELS[k] || k}</td>
                {['precision', 'recall', 'f1', 'fpr'].map((m) => (
                  <td key={m} title={Number.isFinite(v[m].lo) && Number.isFinite(v[m].hi)
                    ? `95% interval ${v[m].lo.toFixed(3)} to ${v[m].hi.toFixed(3)}` : 'Interval unavailable'}>
                    {Number.isFinite(v[m].value) ? iv(v[m]) : 'n/a'}</td>
                ))}
                <td>{v.auroc === null ? 'n/a' : v.auroc.toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3>Recall by attack type</h3>
      <div className="table-scroll" tabIndex={0} role="region" aria-label="Attack type recall">
        <table>
          <thead><tr><th className="left">detector</th>{types.map((t) => <th key={t}>{t}</th>)}</tr></thead>
          <tbody>
            {rows.map(([k, v]) => (
              <tr key={k}><td className="left">{DETECTOR_LABELS[k] || k}</td>
                {types.map((t) => {
                  const c = v.recall_by_type?.[t]
                  return <Shade key={t} p={c ? { ...c, lo: c.ci?.[0], hi: c.ci?.[1] } : null} />
                })}</tr>
            ))}
          </tbody>
        </table>
      </div>
      {ds.coverage?.length ? <Coverage rows={ds.coverage} /> : null}
    </div>
  )
}

function Coverage({ rows }) {
  const pts = rows.map((r) => ({ s: Math.round(r.reference_seconds), fpr: r.fpr_ambient.value, recall: r.recall }))
  return (
    <>
      <h3>False alarms by reference coverage</h3>
      <p className="small muted">Rule detector v1 at 0.55, scored on held-out normal driving, as attack-free
        captures are added to the reference.</p>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={pts} margin={{ top: 8, right: 24, bottom: 18, left: 8 }}>
          <CartesianGrid stroke="var(--grid)" strokeDasharray="2 4" />
          <XAxis dataKey="s" type="number" scale="log" domain={['dataMin', 'dataMax']} {...AXIS}
            tickFormatter={(v) => `${Math.round(v / 60)} min`}
            label={{ value: 'reference length', position: 'insideBottom', offset: -10, fill: 'var(--text-secondary)', fontSize: 11 }} />
          <YAxis domain={[0, 'auto']} {...AXIS} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} width={44} />
          <Tooltip contentStyle={TIP} formatter={(v) => [`${(v * 100).toFixed(1)}%`, 'false-positive rate']}
            labelFormatter={(v) => `${Math.round(v / 60)} min of reference`} />
          <Line dataKey="fpr" stroke="var(--series-2)" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </>
  )
}

/* ---------------------------------------------------------------- submission */

export function SubmitSection({ sets, onSubmitted }) {
  const [setName, setSetName] = useState(sets.includes('heldout') ? 'heldout' : sets[0])
  const [modelName, setModelName] = useState('')
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)
  const submit = async (e) => {
    e.preventDefault()
    if (!file || !modelName || !setName || busy) return
    setBusy(true); setMsg(null)
    try {
      const r = await api.benchmarkSubmit(setName, modelName, file)
      setMsg({ ok: true, text: `Scored ${r.predictions} predictions as "${modelName}"${r.missing_alerts ? `; ${r.missing_alerts} alert(s) had no prediction` : ''}.` })
      onSubmitted()
    } catch (err) {
      setMsg({ ok: false, text: err.message })
    } finally { setBusy(false) }
  }
  if (!sets.length) return null
  return (
    <div className="bench-block">
      <h3>Add a model</h3>
      <p className="small muted">Run any model on the frozen evidence packets, then upload its predictions.
        Packet downloads exclude ground-truth labels. The file uses the same scoring code as every run above.
        One JSON object per line: <span className="mono">{'{"id": "A0000", "attack_type": "dos", "claims": [{"text": "...", "cites": ["E2"]}]}'}</span>.
        Labels: dos, fuzzing, spoofing, replay, masquerade, benign, unknown.</p>
      <form className="bench-controls" onSubmit={submit}>
        <div className="submit-field">
        <label htmlFor="submission-set">Prediction alert set</label>
        <select id="submission-set" value={setName} onChange={(e) => setSetName(e.target.value)} disabled={busy}>
          {sets.map((x) => <option key={x} value={x}>{x}</option>)}
        </select>
        </div>
        <a className="button-link" href={api.benchmarkPacketsUrl(setName)} download={`${setName}_packets.jsonl`}>Download packets</a>
        <div className="submit-field">
        <label htmlFor="submission-name">Model name</label>
        <input id="submission-name" value={modelName} onChange={(e) => setModelName(e.target.value)}
          maxLength={48} pattern="[A-Za-z0-9_.-]+" title="Use letters, digits, periods, underscores, or hyphens" required disabled={busy} />
        </div>
        <div className="submit-field">
        <label htmlFor="submission-file">Predictions file</label>
        <input id="submission-file" type="file" accept=".jsonl,.json,.txt" onChange={(e) => setFile(e.target.files?.[0] || null)} required disabled={busy} />
        </div>
        <button disabled={busy || !file || !modelName}>{busy ? 'Scoring...' : 'Submit'}</button>
      </form>
      {msg ? <p role={msg.ok ? 'status' : 'alert'} className={msg.ok ? 'small' : 'small error'}>{msg.text}</p> : null}
    </div>
  )
}

/* -------------------------------------------------------------------- panel */

export default function EvaluationBenchmarkPanel() {
  const [det, setDet] = useState(null)
  const [exp, setExp] = useState(null)
  const [error, setError] = useState(null)
  const [detectionError, setDetectionError] = useState(null)
  const load = () => {
    setError(null)
    setDetectionError(null)
    api.benchmarkExplainers().then(setExp).catch((e) => setError(e.message))
    api.benchmarkDetection().then(setDet).catch((e) => setDetectionError(e.message))
  }
  useEffect(load, [])
  if (error) return <div><p className="error" role="alert">Could not load saved benchmarks: {error}</p>
    <button type="button" onClick={load}>Retry benchmarks</button></div>
  if (!exp) return <p className="muted" role="status">Loading saved benchmarks...</p>
  return (
    <div className="benchmarks">
      <ExplainerSection data={exp} />
      {det ? <DetectionSection data={det} /> : null}
      {detectionError ? <p className="error" role="alert">Could not load detection benchmarks: {detectionError}</p> : null}
      <SubmitSection sets={Object.keys(exp)} onSubmitted={load} />
    </div>
  )
}
