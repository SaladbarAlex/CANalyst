import { useRef, useState } from 'react'

const ATTACKS = ['dos', 'fuzzing', 'spoofing', 'replay', 'masquerade']

export default function Controls({ onRun, onUpload, busy, params, setParams }) {
  const fileRef = useRef(null)
  const [fileName, setFileName] = useState(null)

  const toggleAttack = (a) => {
    const has = params.attacks.includes(a)
    setParams({
      ...params,
      attacks: has ? params.attacks.filter((x) => x !== a) : [...params.attacks, a],
    })
  }

  return (
    <div className="controls">
      <div className="field">
        <label htmlFor="duration">Capture length</label>
        <input id="duration" type="number" min="20" max="900" step="10" value={params.duration_s}
          onChange={(e) => setParams({ ...params, duration_s: Number(e.target.value) })} />
      </div>
      <div className="field">
        <label htmlFor="seed">Seed</label>
        <input id="seed" type="number" value={params.seed}
          onChange={(e) => setParams({ ...params, seed: Number(e.target.value) })} />
      </div>
      <div className="field">
        <label htmlFor="window">Window (s)</label>
        <input id="window" type="number" step="0.1" min="0.1" value={params.window_s}
          onChange={(e) => setParams({ ...params, window_s: Number(e.target.value) })} />
      </div>
      <div className="field">
        <label htmlFor="threshold">Threshold</label>
        <input id="threshold" type="number" step="0.05" min="0.05" max="0.95" value={params.threshold}
          onChange={(e) => setParams({ ...params, threshold: Number(e.target.value) })} />
      </div>
      <div className="field">
        <label htmlFor="detector">Detector</label>
        <select id="detector" value={params.detector}
          onChange={(e) => setParams({ ...params, detector: e.target.value })}>
          <option value="rule">Rule based</option>
          <option value="forest">Isolation forest</option>
        </select>
      </div>
      <div className="field">
        <label>Injected attacks</label>
        <div className="chips">
          {ATTACKS.map((a) => (
            <button key={a} type="button" className="chip" aria-pressed={params.attacks.includes(a)}
              onClick={() => toggleAttack(a)}>{a}</button>
          ))}
        </div>
      </div>
      <button onClick={onRun} disabled={busy}>{busy ? 'Analyzing...' : 'Run analysis'}</button>
      <button className="secondary" type="button" onClick={() => fileRef.current?.click()} disabled={busy}>
        Load a CSV log
      </button>
      <input ref={fileRef} type="file" accept=".csv,.txt" style={{ display: 'none' }}
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) { setFileName(f.name); onUpload(f) }
        }} />
      {fileName ? <span className="small muted">loaded: {fileName}</span> : null}
    </div>
  )
}
