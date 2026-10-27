import { useEffect, useRef, useState } from 'react'
import { fmt } from '../api'

/* The explanation and its evidence live side by side: clicking a citation
   chip scrolls to and highlights the evidence row it refers to, so no claim
   is readable without the number behind it. */

function DetailSection({ title, compact, children, open, onToggle }) {
  if (!compact) return <><h3>{title}</h3>{children}</>
  return (
    <details className="evidence-disclosure" open={open} onToggle={onToggle}>
      <summary>{title}</summary>
      <div className="disclosure-body">{children}</div>
    </details>
  )
}

export default function ExplanationPanel({ detail, onReExplain, busy, compact = false }) {
  const [activeCite, setActiveCite] = useState(null)
  const [evidenceOpen, setEvidenceOpen] = useState(false)
  const rowRefs = useRef({})

  useEffect(() => {
    setActiveCite(null)
    setEvidenceOpen(false)
  }, [detail?.alert?.alert_id])

  useEffect(() => {
    if (activeCite) rowRefs.current[activeCite]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [activeCite, evidenceOpen, compact])

  if (!detail) {
    return <div className="empty">Select an alert to see its explanation and evidence.</div>
  }

  const { alert, evidence, explanation } = detail
  const exp = explanation ?? alert.explanation

  const jumpTo = (id) => {
    setActiveCite(id)
    setEvidenceOpen(true)
    if (!compact || evidenceOpen) rowRefs.current[id]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }

  return (
    <div>
      <div className="explain-head">
        <h3>
          Alert {String(alert.alert_id).padStart(2, '0')}
          <span className="mono">{fmt.sec(alert.start)} to {fmt.sec(alert.end)}</span>
        </h3>
        <div className="spacer" />
        <button className="secondary" onClick={onReExplain} disabled={busy}>
          {busy ? 'Explaining...' : 'Re-explain'}
        </button>
      </div>

      {exp ? (
        <>
          <div className="row" style={{ margin: '10px 0' }}>
            <span className={`badge ${exp.severity}`}><span className="dot" />{exp.attack_type}</span>
            <span className="badge">severity {exp.severity}</span>
            <span className="badge">confidence {fmt.pct(exp.confidence)}</span>
            <span className={`badge ${exp.grounded ? 'ok' : 'mismatch'}`}>
              <span className="dot" />{exp.grounded ? 'all claims cited' : 'uncited claims'}
            </span>
            <span className="badge">model: {exp.model}</span>
          </div>

          <p className="summary-line">{exp.summary}</p>
          <div className="small muted">Affected function: {exp.affected_function}</div>

          <h3>Reasoning</h3>
          <ul className="claims">
            {exp.claims.map((c, i) => (
              <li key={i}>
                {c.text}
                {(c.cites ?? []).map((id) => (
                  <button key={id} className={`cite ${activeCite === id ? 'active' : ''}`}
                    onClick={() => jumpTo(id)} title="Jump to the evidence behind this claim">
                    {id}
                  </button>
                ))}
              </li>
            ))}
          </ul>

          {exp.recommended_action ? (
            <div className="action">
              <strong>Next step</strong><br />
              {exp.recommended_action}
            </div>
          ) : null}
        </>
      ) : (
        <p className="muted">No explanation generated for this alert yet.</p>
      )}

      <DetailSection title="Why the detector flagged it" compact={compact}>
        <ul className="reasons">
          {alert.reasons.map((r, i) => <li key={i}>{r}</li>)}
        </ul>
        <div className="components">
          {Object.entries(alert.components)
            .filter(([, v]) => v > 0)
            .sort((a, b) => b[1] - a[1])
            .map(([k, v]) => (
              <span key={k} className="meter" title={`${k}: ${v}`}>
                {k.replace('_', ' ')}
                <span className="bar"><i style={{ width: `${Math.min(1, v) * 100}%` }} /></span>
                {fmt.num(v)}
              </span>
            ))}
        </div>

      </DetailSection>

      <DetailSection title={`Evidence${compact ? ` · ${evidence.items.length} measurements` : ''}`} compact={compact}
        open={evidenceOpen} onToggle={(event) => setEvidenceOpen(event.currentTarget.open)}>
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th className="left">id</th>
                <th className="left">kind</th>
                <th className="left">measurement</th>
              </tr>
            </thead>
            <tbody>
              {evidence.items.map((it) => (
                <tr key={it.id} ref={(el) => { rowRefs.current[it.id] = el }}
                  className={activeCite === it.id ? 'highlight' : ''}>
                  <td className="left mono">{it.id}</td>
                  <td className="left small muted">{it.kind}</td>
                  <td className="left">{it.text}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

      </DetailSection>


      {evidence.sample_frames?.length ? (
        <DetailSection title="Sample frames" compact={compact}>
          <div className="scroll">
            <table>
              <thead>
                <tr>
                  <th className="left">timestamp</th>
                  <th className="left">CAN ID</th>
                  <th>DLC</th>
                  <th className="left">payload</th>
                </tr>
              </thead>
              <tbody>
                {evidence.sample_frames.map((f, i) => (
                  <tr key={i}>
                    <td className="left mono">{f.timestamp.toFixed(4)}</td>
                    <td className="left mono">{f.can_id}</td>
                    <td>{f.dlc}</td>
                    <td className="left mono">{f.payload}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </DetailSection>
      ) : null}
    </div>
  )
}
