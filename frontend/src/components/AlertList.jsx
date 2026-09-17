import { fmt } from '../api'

export default function AlertList({ alerts, selected, onSelect, labeled }) {
  if (!alerts?.length) {
    return <p className="muted">No alerts. Either the traffic is clean or the threshold is too high.</p>
  }
  return (
    <div className="alert-list">
      {alerts.map((a) => {
        const exp = a.explanation
        const sev = exp?.severity ?? 'low'
        const pred = exp?.attack_type ?? 'unclassified'
        const truth = a.true_type && a.true_type !== 'normal' ? a.true_type : null
        const match = truth ? (truth === pred ? 'match' : 'mismatch') : null
        return (
          <button
            key={a.alert_id}
            className={`alert-row sev-${sev}`}
            aria-current={a.alert_id === selected}
            onClick={() => onSelect(a.alert_id)}
          >
            <span className="when">
              {fmt.sec(a.start)} to {fmt.sec(a.end)}
            </span>
            <span className="score">score {fmt.num(a.score)}</span>
            <span className="meta">
              <span className={`badge ${sev}`}><span className="dot" />{pred}</span>{' '}
              {a.ids_involved.slice(0, 3).join(', ')}
            </span>
            {labeled && truth ? (
              <span className={`badge ${match} small`}>truth: {truth}</span>
            ) : (
              <span className="small muted">{a.frame_count} frames</span>
            )}
          </button>
        )
      })}
    </div>
  )
}
