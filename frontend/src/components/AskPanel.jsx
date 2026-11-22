import { useEffect, useRef, useState } from 'react'
import { api } from '../api'

const SUGGESTIONS = [
  'Which alert is the most severe and why?',
  'What changed on 0x2C0 during the flagged window?',
  'Were any expected IDs missing at any point?',
]

export default function AskPanel({ analysisId, explainer }) {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const request = useRef(null)
  useEffect(() => {
    request.current?.abort()
    setAnswer(null); setBusy(false); setError(null)
    return () => request.current?.abort()
  }, [analysisId, explainer])

  const submit = async (q) => {
    const text = (q ?? question).trim()
    if (!text || !analysisId || busy) return
    request.current?.abort()
    const abort = new AbortController()
    request.current = abort
    setBusy(true); setError(null); setAnswer(null)
    try {
      const res = await api.ask(analysisId, text, explainer, abort.signal)
      if (!abort.signal.aborted) setAnswer(res)
    } catch (e) {
      if (!abort.signal.aborted) setError(e.message)
    } finally {
      if (!abort.signal.aborted) setBusy(false)
    }
  }

  return (
    <div>
      <form className="row ask-form" onSubmit={(e) => { e.preventDefault(); submit() }}>
        <input aria-label="Question about this capture" value={question}
          placeholder="Ask about this capture" onChange={(e) => setQuestion(e.target.value)} />
        <button disabled={busy || !analysisId}>{busy ? 'Thinking...' : 'Ask'}</button>
      </form>
      <div className="chips" style={{ marginTop: 8 }}>
        {SUGGESTIONS.map((s) => (
          <button key={s} type="button" className="chip" disabled={busy || !analysisId}
            onClick={() => { setQuestion(s); submit(s) }}>{s}</button>
        ))}
      </div>
      {error ? <p className="error" style={{ marginTop: 10 }}>{error}</p> : null}
      {answer ? (
        <div className="ask-answer">
          {answer.answer}
          <div className="small muted" style={{ marginTop: 6 }}>answered by: {answer.explainer}</div>
        </div>
      ) : null}
    </div>
  )
}
