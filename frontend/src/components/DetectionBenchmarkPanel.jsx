import { fmt } from '../api'

// Detection measurements remain distinct from conditional alert classification.
export default function DetectionBenchmarkPanel({ data, error }) {
  const runs = data?.runs ?? []
  return (
    <details className="evidence-disclosure detection-benchmarks" style={{ marginBottom: 20 }}>
      <summary>Saved detector comparisons{data ? ` · ${runs.length} results` : ''}</summary>
      <div className="disclosure-body">
        <p className="small muted">
          Window-level detection on saved captures, including unsuccessful calibration experiments.
          Profiles can use different baselines and normal holdouts; compare detectors within the same
          profile before comparing profiles. Inspect recall alongside false-positive rate.
        </p>
        {error ? <p className="error" role="status">Could not load detector results: {error}</p> : null}
        {!data && !error ? <p className="muted">Loading saved detector results…</p> : null}
        {data?.errors?.length ? <p className="error" role="status">
          {data.errors.length} detector result file(s) could not be loaded; available results appear below.
        </p> : null}
        {data && !runs.length ? <p className="muted">No completed detector comparisons are available.</p> : null}
        {runs.length ? <>
          <div className="scroll">
            <table>
              <thead><tr>
                <th className="left">Dataset / profile</th><th className="left">Detector</th>
                <th>Precision</th><th>Recall</th><th>F1</th><th>FPR, all windows</th>
                <th>FPR, normal holdouts</th><th>Windows</th>
              </tr></thead>
              <tbody>{runs.map((run) => <tr key={run.id}>
                <td className="left">{run.dataset}<br /><span className="small muted">{run.profile}</span></td>
                <td className="left">{run.detector}</td>
                <td>{fmt.pct(run.metrics?.precision)}</td>
                <td>{fmt.pct(run.metrics?.recall)}</td>
                <td>{fmt.num(run.metrics?.f1, 3)}</td>
                <td>{fmt.pct(run.metrics?.false_positive_rate)}</td>
                <td>{fmt.pct(run.normal_metrics?.false_positive_rate)}</td>
                <td>{run.metrics?.windows_evaluated?.toLocaleString() ?? 'n/a'}</td>
              </tr>)}</tbody>
            </table>
          </div>
          <p className="small muted">
            FPR is measured on benign windows within the stated scope. Normal-holdout FPR is a
            separate subset and can hide false positives in attack captures. These saved comparisons
            do not change the selected detector.
          </p>
          <details className="evidence-disclosure">
            <summary>Detector protocols and sources</summary>
            {runs.map((run) => <div key={run.id} className="small muted" style={{ margin: '10px 0', overflowWrap: 'anywhere' }}>
              <strong>{run.dataset} · {run.profile} · {run.detector}</strong><br />
              Scope: {run.scope}; saved {run.created_utc ?? 'date unavailable'}<br />
              Method: {typeof run.methodology === 'object' ? JSON.stringify(run.methodology) : run.methodology ?? 'not recorded'}<br />
              Source: <span className="mono">{run.source}</span>
            </div>)}
          </details>
        </> : null}
      </div>
    </details>
  )
}
