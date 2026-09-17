import { useEffect, useMemo, useState } from 'react'
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api, fmt } from '../api'

const AXIS = { stroke: 'var(--axis)', tick: { fill: 'var(--text-muted)', fontSize: 11 } }

export default function IdView({ analysisId, ids }) {
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(null)
  const [series, setSeries] = useState(null)

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q ? ids.filter((r) =>
      r.can_id.toLowerCase().includes(q) || r.name.toLowerCase().includes(q) ||
      r.function.toLowerCase().includes(q)) : ids
  }, [ids, query])

  useEffect(() => {
    if (!selected || !analysisId) return
    let live = true
    api.idSeries(analysisId, selected).then((s) => { if (live) setSeries(s) }).catch(() => {})
    return () => { live = false }
  }, [analysisId, selected])

  return (
    <div>
      <div className="row" style={{ marginBottom: 10 }}>
        <input placeholder="Filter by ID, name or function" value={query}
          onChange={(e) => setQuery(e.target.value)} style={{ minWidth: 240 }} />
        <span className="small muted">
          {rows.length} of {ids.length} IDs. Red IDs are absent from the baseline.
        </span>
      </div>

      {selected && series ? (
        <div style={{ marginBottom: 14 }}>
          <div className="legend">
            <span className="key"><span className="swatch" /> {series.can_id} rate (msg/s)</span>
            <span className="key muted">dashed line is the baseline rate</span>
          </div>
          <ResponsiveContainer width="100%" height={150}>
            <LineChart data={series.points} margin={{ top: 6, right: 12, bottom: 4, left: 0 }}>
              <CartesianGrid stroke="var(--grid)" strokeDasharray="2 4" vertical={false} />
              <XAxis dataKey="t" type="number" domain={['dataMin', 'dataMax']} {...AXIS}
                tickFormatter={(v) => `${v}s`} />
              <YAxis {...AXIS} width={52} />
              <Tooltip contentStyle={{ background: 'var(--surface-1)', border: '1px solid var(--border)',
                borderRadius: 8, fontSize: 12 }} />
              <ReferenceLine y={series.baseline_rate} stroke="var(--series-3)" strokeDasharray="4 4" />
              <Line type="monotone" dataKey="rate" stroke="var(--series-1)" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : null}

      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th className="left">CAN ID</th>
              <th className="left">function</th>
              <th>frames</th>
              <th>rate</th>
              <th>baseline</th>
              <th>gap ms</th>
              <th>jitter ms</th>
              <th>entropy</th>
              <th className="left">state</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.can_id} className={`clickable ${r.known ? '' : 'unknown-id'}`}
                aria-current={selected === r.can_id}
                onClick={() => setSelected(r.can_id)}>
                <td className="left mono">{r.can_id}</td>
                <td className="left">{r.known ? r.function : 'not in baseline'}</td>
                <td>{r.count}</td>
                <td>{fmt.num(r.rate)}</td>
                <td>{r.known ? fmt.num(r.baseline_rate) : '-'}</td>
                <td>{fmt.num(r.iat_mean_ms, 1)}</td>
                <td>{fmt.num(r.iat_std_ms, 1)}</td>
                <td>{fmt.num(r.entropy)}</td>
                <td className="left small">
                  {r.in_alert ? <span className="badge high"><span className="dot" />in alert</span>
                    : <span className="muted">normal</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
