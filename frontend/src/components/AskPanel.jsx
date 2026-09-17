import { useState } from 'react'
import { api } from '../api'

const SUGGESTIONS = [
  'Which alert is the most severe and why?',
  'What changed on 0x2C0 during the flagged window?',
  'Were any expected IDs missing at any point?',
]

export default function AskPanel({ analysisId }) {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const submit = async (q) => {
    const text = (q ?? question).trim()
    if (!text || !analysisId) return
    setBusy(true); setError(null)
    try {
      const res = await api.ask(analysisId, text)
      setAnswer(res)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <form className="row" onSubmit={(e) => { e.preventDefault(); submit() }}>
        <input style={{ flex: 1, minWidth: 260 }} value={question}
          placeholder="Ask about this capture" onChange={(e) => setQuestion(e.target.value)} />
        <button disabled={busy || !analysisId}>{busy ? 'Thinking...' : 'Ask'}</button>
      </form>
      <div className="chips" style={{ marginTop: 8 }}>
        {SUGGESTIONS.map((s) => (
          <button key={s} type="button" className="chip"
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
