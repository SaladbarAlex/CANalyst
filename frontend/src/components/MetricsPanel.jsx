import {
  Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { fmt } from '../api'

const AXIS = { stroke: 'var(--axis)', tick: { fill: 'var(--text-muted)', fontSize: 11 } }

export default function MetricsPanel({ report }) {
  if (!report) return <p className="muted">Run an analysis to see evaluation metrics.</p>
  const d = report.detection
  if (!d.labeled) {
    return (
      <p className="muted">
        This log has no ground-truth labels, so detection metrics cannot be computed.
        Load a labeled dataset (Car-Hacking, ROAD, or the synthetic generator) to evaluate.
      </p>
    )
  }
  const byType = Object.entries(d.per_attack_type).map(([k, v]) => ({
    type: k, recall: v.recall, detected: v.detected, windows: v.windows,
  }))
  const c = report.classification
  const g = report.grounding

  return (
    <div>
      <div className="kpis" style={{ marginBottom: 16 }}>
        <div className="kpi"><div className="label">Precision</div><div className="value">{fmt.pct(d.precision)}</div>
          <div className="note">{d.true_positive} TP / {d.false_positive} FP</div></div>
        <div className="kpi"><div className="label">Recall</div><div className="value">{fmt.pct(d.recall)}</div>
          <div className="note">{d.false_negative} missed windows</div></div>
        <div className="kpi"><div className="label">F1</div><div className="value">{fmt.num(d.f1, 3)}</div>
          <div className="note">{d.windows_evaluated} windows scored</div></div>
        <div className="kpi"><div className="label">False positive rate</div><div className="value">{fmt.pct(d.false_positive_rate)}</div>
          <div className="note">on benign windows</div></div>
        <div className="kpi"><div className="label">Classification</div>
          <div className="value">{c.accuracy === null ? 'n/a' : fmt.pct(c.accuracy)}</div>
          <div className="note">{c.scored_alerts} labeled alerts</div></div>
        <div className="kpi"><div className="label">Grounded explanations</div>
          <div className="value">{g.grounded_rate === null ? 'n/a' : fmt.pct(g.grounded_rate)}</div>
          <div className="note">{g.uncited_claims ?? 0} of {g.total_claims ?? 0} claims uncited</div></div>
      </div>

      <h3>Recall by attack type</h3>
      <div className="legend"><span className="key muted">Share of that attack's windows the detector flagged</span></div>
      <ResponsiveContainer width="100%" height={40 + byType.length * 34}>
        <BarChart data={byType} layout="vertical" margin={{ top: 4, right: 48, bottom: 4, left: 8 }}>
          <CartesianGrid stroke="var(--grid)" strokeDasharray="2 4" horizontal={false} />
          <XAxis type="number" domain={[0, 1]} {...AXIS} tickFormatter={(v) => `${v * 100}%`} />
          <YAxis type="category" dataKey="type" width={90} {...AXIS} />
          <Tooltip contentStyle={{ background: 'var(--surface-1)', border: '1px solid var(--border)',
            borderRadius: 8, fontSize: 12 }}
            formatter={(v, _n, p) => [`${(v * 100).toFixed(1)}% (${p.payload.detected}/${p.payload.windows})`, 'recall']} />
          <Bar dataKey="recall" fill="var(--series-1)" radius={[0, 4, 4, 0]} barSize={16}>
            <LabelList dataKey="recall" position="right" formatter={(v) => `${(v * 100).toFixed(0)}%`}
              style={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <h3>Confusion (true type versus predicted)</h3>
      {c.scored_alerts ? (
        <table>
          <thead><tr><th className="left">true</th><th className="left">predicted</th><th>alerts</th></tr></thead>
          <tbody>
            {Object.entries(c.confusion).flatMap(([t, preds]) =>
              Object.entries(preds).map(([p, n]) => (
                <tr key={`${t}-${p}`}>
                  <td className="left">{t}</td>
                  <td className="left">
                    <span className={`badge ${t === p ? 'match' : 'mismatch'}`}>{p}</span>
                  </td>
                  <td>{n}</td>
                </tr>
              )))}
          </tbody>
        </table>
      ) : <p className="muted">No labeled alerts to score.</p>}

      <p className="small muted" style={{ marginTop: 14 }}>
        Detector: {report.detector}. Explainer: {report.explainer}. The mock explainer reads the
        same features the detector scores, so its classification accuracy is a control condition,
        not a measurement of LLM performance.
      </p>
    </div>
  )
}
