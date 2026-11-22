import { useState } from 'react'

const ATTACKS = ['dos', 'fuzzing', 'spoofing', 'replay', 'masquerade']

export default function Controls({ onRun, onUpload, busy, params, setParams }) {
  const [file, setFile] = useState(null)
  const [baselineFile, setBaselineFile] = useState(null)
  const [metadataFile, setMetadataFile] = useState(null)
  const [baselineSeconds, setBaselineSeconds] = useState(20)

  const toggleAttack = (a) => {
    const has = params.attacks.includes(a)
    setParams({
      ...params,
      attacks: has ? params.attacks.filter((x) => x !== a) : [...params.attacks, a],
    })
  }

  return (
    <form className="controls" onSubmit={(e) => {
      e.preventDefault()
      if (e.nativeEvent.submitter?.value === 'upload') {
        if (file) onUpload(file, { baselineFile, metadataFile, baselineSeconds })
      } else onRun()
    }}>
      <div className="field">
        <label htmlFor="duration">Demo length (s)</label>
        <input id="duration" type="number" required min="20" max="900" step="10" value={params.duration_s}
          onChange={(e) => setParams({ ...params, duration_s: Number(e.target.value) })} />
      </div>
      <div className="field">
        <label htmlFor="seed">Seed</label>
        <input id="seed" type="number" required step="1" value={params.seed}
          onChange={(e) => setParams({ ...params, seed: Number(e.target.value) })} />
      </div>
      <div className="field">
        <label htmlFor="window">Window (s)</label>
        <input id="window" type="number" required step="0.05" min="0.1" max="5" value={params.window_s}
          onChange={(e) => setParams({ ...params, window_s: Number(e.target.value) })} />
      </div>
      <div className="field">
        <label htmlFor="threshold">Threshold</label>
        <input id="threshold" type="number" required step="0.01" min="0.05" max="0.99" value={params.threshold}
          onChange={(e) => setParams({ ...params, threshold: Number(e.target.value) })} />
      </div>
      <div className="field">
        <label htmlFor="stride">Stride (s)</label>
        <input id="stride" type="number" required min="0.02" max={params.window_s} step="0.01" value={params.stride_s}
          onChange={(e) => setParams({ ...params, stride_s: Number(e.target.value) })} />
      </div>
      <div className="field">
        <label htmlFor="detector">Detector</label>
        <select id="detector" value={params.detector}
          onChange={(e) => setParams({ ...params, detector: e.target.value })}>
          <option value="rule">Rule based</option>
          <option value="forest">Isolation forest</option>
        </select>
      </div>
      <div className="field span-2">
        <label>Demo attacks</label>
        <div className="chips">
          {ATTACKS.map((a) => (
            <button key={a} type="button" className="chip" aria-pressed={params.attacks.includes(a)}
              onClick={() => toggleAttack(a)}>{a}</button>
          ))}
        </div>
      </div>
      <button className="run-btn span-2" type="submit" value="demo" disabled={busy}>
        {busy ? 'Analyzing…' : 'Run demo analysis'}
      </button>
      <fieldset className="upload-settings">
        <legend>Analyze a traffic log</legend>
        <p className="small muted">Use a separate normal recording for the baseline. ROAD attack labels require its metadata JSON.</p>
        <div className="upload-grid">
          <div className="field">
            <label htmlFor="traffic-file">Traffic capture</label>
            <input id="traffic-file" type="file" accept=".csv,.txt,.log" disabled={busy}
              onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </div>
          <div className="field">
            <label htmlFor="baseline-file">Normal baseline (optional)</label>
            <input id="baseline-file" type="file" accept=".csv,.txt,.log" disabled={busy}
              onChange={(e) => setBaselineFile(e.target.files?.[0] ?? null)} />
          </div>
          <div className="field">
            <label htmlFor="metadata-file">ROAD metadata (optional JSON)</label>
            <input id="metadata-file" type="file" accept=".json" disabled={busy}
              onChange={(e) => setMetadataFile(e.target.files?.[0] ?? null)} />
          </div>
          <div className="field">
            <label htmlFor="baseline-seconds">Clean prefix duration (s)</label>
            <input id="baseline-seconds" type="number" min="1" step="1" required disabled={!!baselineFile} value={baselineSeconds}
              onChange={(e) => setBaselineSeconds(Number(e.target.value))} />
          </div>
        </div>
        <p className="small muted">{baselineFile
          ? `Learn normal behavior from the full separate capture ${baselineFile.name}.`
          : `Without a separate file, the first ${baselineSeconds}s of the capture must contain only normal traffic.`}
          {' '}Detector, window, stride, and threshold above apply to uploads.</p>
        <button className="secondary" type="submit" value="upload" disabled={busy || !file}>
          {busy ? 'Analyzing…' : 'Analyze selected log'}
        </button>
      </fieldset>
    </form>
  )
}
