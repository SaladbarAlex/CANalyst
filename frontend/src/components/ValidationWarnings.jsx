function fieldLabel(field = '') {
  const claim = /^claims\[(\d+)\]\.text$/.exec(field)
  if (claim) return `Claim ${Number(claim[1]) + 1}`
  return ({ summary: 'Summary', affected_function: 'Affected function', recommended_action: 'Recommended action' })[field]
    ?? field.replaceAll('_', ' ')
}

// Identifier membership is separate from citation validity and label accuracy.
export default function ValidationWarnings({ warnings }) {
  if (!warnings?.length) return null
  return (
    <details className="evidence-disclosure identifier-warnings">
      <summary>Identifier review · {warnings.length} {warnings.length === 1 ? 'reference' : 'references'} to check</summary>
      <div className="disclosure-body">
        <ul className="claims">
          {warnings.map((warning, index) => <li key={`${warning.field}-${warning.start}-${index}`}>
            <strong>{warning.code === 'can_id_not_in_evidence'
              ? 'ID absent from evidence' : warning.code === 'ambiguous_hex_reference'
                ? 'Ambiguous hexadecimal reference' : 'Identifier review note'}</strong>
            {' · '}{fieldLabel(warning.field)}{' · '}<span className="mono">{warning.token}</span>
            <div>{warning.message}</div>
          </li>)}
        </ul>
        <p className="small muted">This check concerns identifier presence only. It does not validate the explanation.</p>
      </div>
    </details>
  )
}
