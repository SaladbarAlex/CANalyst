import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

/* Two stacked panels share one x axis. Message rate and detector score are
   different measures, so they never share a y axis. */

const AXIS = { stroke: 'var(--axis)', tick: { fill: 'var(--text-muted)', fontSize: 11 } }

function RateTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="tooltip">
      <div className="t">t = {Number(label).toFixed(2)}s</div>
      <div>{p.msg_rate.toFixed(0)} msg/s</div>
      <div className="t">score {p.score.toFixed(2)}{p.flagged ? ' (flagged)' : ''}</div>
    </div>
  )
}

export default function TimelineChart({ timeline, selectedAlert, onSelectAlert }) {
  const points = timeline?.points ?? []
  const intervals = timeline?.attack_intervals ?? []
  const alerts = timeline?.alerts ?? []
  const threshold = timeline?.threshold ?? 0.55

  const handleClick = (state) => {
    const t = state?.activeLabel
    if (t === undefined || !onSelectAlert) return
    const hit = alerts.find((a) => t >= a.start - 0.3 && t <= a.end + 0.3)
    if (hit) onSelectAlert(hit.alert_id)
  }

  return (
    <div>
      <div className="legend">
        <span className="key"><span className="swatch" /> Message rate (msg/s)</span>
        <span className="key"><span className="swatch score" /> Detector score</span>
        <span className="key"><span className="swatch band" /> Labeled attack interval</span>
        <span className="key">
          <span className="swatch" style={{ background: 'var(--series-3)' }} /> Baseline rate (dashed)
        </span>
        <span className="key">
          <span className="swatch" style={{ background: 'var(--critical)' }} /> Alert threshold (dashed)
        </span>
        <span className="key muted">Click a shaded region to open its alert</span>
      </div>

      <ResponsiveContainer width="100%" height={180}>
        <AreaChart data={points} onClick={handleClick} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--grid)" strokeDasharray="2 4" vertical={false} />
          <XAxis dataKey="t" type="number" domain={['dataMin', 'dataMax']} {...AXIS}
            tickFormatter={(v) => `${v}s`} height={18} />
          <YAxis {...AXIS} width={52} label={{ value: 'msg/s', angle: -90, position: 'insideLeft',
            fill: 'var(--text-muted)', fontSize: 11 }} />
          <Tooltip content={<RateTooltip />} />
          {intervals.map((iv, i) => (
            <ReferenceArea key={`gt${i}`} x1={iv.start} x2={iv.end}
              fill="var(--critical)" fillOpacity={0.14} stroke="none" />
          ))}
          {alerts.map((a) => (
            <ReferenceArea key={`al${a.alert_id}`} x1={a.start} x2={a.end}
              fill="var(--series-2)" fillOpacity={a.alert_id === selectedAlert ? 0.3 : 0.1}
              stroke={a.alert_id === selectedAlert ? 'var(--series-2)' : 'none'} strokeWidth={2} />
          ))}
          {timeline?.baseline_rate ? (
            <ReferenceLine y={timeline.baseline_rate} stroke="var(--series-3)" strokeDasharray="4 4" />
          ) : null}
          <Area type="monotone" dataKey="msg_rate" stroke="var(--series-1)" strokeWidth={2}
            fill="var(--series-1)" fillOpacity={0.12} dot={false} activeDot={{ r: 4 }} />
        </AreaChart>
      </ResponsiveContainer>

      <ResponsiveContainer width="100%" height={120}>
        <LineChart data={points} onClick={handleClick} margin={{ top: 4, right: 12, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="var(--grid)" strokeDasharray="2 4" vertical={false} />
          <XAxis dataKey="t" type="number" domain={['dataMin', 'dataMax']} {...AXIS}
            tickFormatter={(v) => `${v}s`} />
          <YAxis domain={[0, 1]} {...AXIS} width={52}
            label={{ value: 'score', angle: -90, position: 'insideLeft', fill: 'var(--text-muted)', fontSize: 11 }} />
          <Tooltip content={<RateTooltip />} />
          <ReferenceLine y={threshold} stroke="var(--critical)" strokeDasharray="4 4" />
          <Line type="monotone" dataKey="score" stroke="var(--series-2)" strokeWidth={2} dot={false}
            activeDot={{ r: 4 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
