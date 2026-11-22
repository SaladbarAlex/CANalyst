import { useState } from 'react'
import { fmt } from '../api'

const ATTACK_TYPES = new Set(['dos', 'fuzzing', 'spoofing', 'replay', 'masquerade'])

export default function AlertList({ alerts, selected, onSelect, labeled, busy }) {
  const [query, setQuery] = useState('')
  const filtered = (alerts ?? []).filter((a) =>
    [a.alert_id, a.explanation?.attack_type, ...(a.ids_involved ?? [])].join(' ').toLowerCase().includes(query.trim().toLowerCase()))
  if (!alerts?.length) {
    return (
      <div className="empty">
        {busy ? 'Scoring windows...' : 'No alerts. Either the traffic is clean or the threshold is too high.'}
      </div>
    )
  }
  return (
    <div>
      <label className="small muted" htmlFor="alert-filter">Filter alerts by CAN ID or classification</label>
      <input id="alert-filter" value={query} placeholder="e.g. 0x000 or dos"
        onChange={(e) => setQuery(e.target.value)} style={{ margin: '6px 0 10px' }} />
      {query ? <p className="small muted">{filtered.length} of {alerts.length} alerts</p> : null}
      <div className="alert-list">
      {filtered.map((a) => {
        const exp = a.explanation
        const sev = exp?.severity ?? 'low'
        const pred = exp?.fallback || exp?.model?.includes('fallback') ? 'request_failed' : exp?.attack_type ?? 'unclassified'
        const truth = ATTACK_TYPES.has(a.true_type) ? a.true_type : null
        const match = truth && exp ? (truth === pred ? 'match' : 'mismatch') : null
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
            <span className="score">{fmt.num(a.score)}</span>
            <span className="meta">
              <span className={`badge ${sev}`}><span className="dot" />{pred}</span>{' '}
              <span>{a.ids_involved.slice(0, 3).join(' ')}</span>
            </span>
            {labeled && truth ? (
              <span className={`badge ${match}`}>{!exp ? 'truth:' : match === 'match' ? '✓' : '✗'} {truth}</span>
            ) : labeled && a.true_type === 'injected' ? (
              <span className="small muted">attack labeled; type unavailable</span>
            ) : (
              <span className="small muted">{a.frame_count} frames</span>
            )}
          </button>
        )
      })}
      </div>
    </div>
  )
}
