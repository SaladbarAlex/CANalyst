# CANalyst

LLM-assisted analysis of CAN bus attacks. CPSC 8580 course project, Clemson University.

Nicholas DiGennaro (ndigenn@clemson.edu), Alexander Salazar (salaza7@clemson.edu)

A detector flags suspicious windows of in-vehicle CAN traffic. An explanation
layer then classifies each flagged window, explains it in plain language, and
links every claim back to the measurement behind it.

## Quick start

Two terminals. The backend first.

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000               # API docs at localhost:8000/docs
```

**Python 3.10 or newer is required** (3.12 recommended). The macOS system
Python is 3.9 and will fail on numpy. `brew install python@3.12` if you need it,
then use `python3.12` to create the venv.

Then the frontend.

```bash
cd frontend
npm install
npm run dev                                           # dashboard at localhost:5173
```

The dashboard analyzes a synthetic capture as soon as it loads, so it is never
empty. Vite proxies `/api` to port 8000, so there is no CORS setup in development.

## What runs where

```
backend/
  app/synth.py       synthetic CAN generator: 12 periodic IDs, 5 attack types, ground truth
  app/loader.py      normalizes Car-Hacking, ROAD, and synthetic logs into one DataFrame
  app/features.py    baseline learning + windowed features (rate, inter-arrival, entropy, bit flips)
  app/detector.py    RuleDetector (interpretable, default) and ForestDetector (IsolationForest)
  app/evidence.py    builds the compact evidence packet, with an id per item for citations
  app/llm.py         Explainer interface: MockExplainer, ClaudeExplainer, OpenAIExplainer
  app/metrics.py     precision / recall / F1, per-attack recall, classification, grounding
  app/pipeline.py    orchestration and the in-memory analysis store
  app/main.py        FastAPI routes
  scripts/evaluate.py  command-line harness that produces the numbers for the paper
  tests/             pytest suite (9 tests)
frontend/
  src/App.jsx        layout, data loading, tab state
  src/components/    TimelineChart, AlertList, ExplanationPanel, IdView, MetricsPanel, AskPanel, Controls
  src/styles.css     design tokens, light and dark
```

The pipeline is a five-stage flow: **ingest, feature extraction, detection,
explanation, dashboard.** Stages 1 to 3 are statistics with no model involved.
Stage 4 is the only place an LLM appears.

## The explanation layer

`app/llm.py` defines `Explainer`. Pick one with the `EXPLAINER` environment variable:

```bash
export EXPLAINER=mock                 # default: offline, deterministic, no key
export EXPLAINER=claude ANTHROPIC_API_KEY=sk-...
export EXPLAINER=openai OPENAI_API_KEY=sk-...
```

Three properties matter for the evaluation:

1. **The LLM never sees raw traffic.** It receives an evidence packet: measured
   deviations, per-ID statistics, and at most six sample frames. A capture can
   hold hundreds of thousands of frames, so summarizing is what makes this
   affordable and keeps the model from inventing detail.
2. **Every claim must cite an evidence id.** `_check_citations` drops citations
   that resolve to nothing and marks the explanation ungrounded. That flag is
   what the faithfulness metric counts, and the dashboard shows it per alert.
3. **A failed API call falls back to the mock.** The panel is never blank, and
   the model field says a fallback happened.

`MockExplainer` is also the **control condition** for the evaluation: it reads
the same features the detector scores, so its classification accuracy measures
the rule set, not a language model. Do not report it as LLM accuracy.

## Evaluation

```bash
cd backend
python -m scripts.evaluate --seeds 1 2 3 4 5 --duration 150
python -m scripts.evaluate --detector forest          # learned baseline for comparison
python -m scripts.evaluate --csv path/to/real_log.csv --out report.json
```

Current numbers on synthetic data with the rule detector and 0.5s windows, five
seeds:

| metric | value |
|---|---|
| precision | 0.977 (sd 0.013) |
| recall | 0.950 (sd 0.006) |
| F1 | 0.963 (sd 0.004) |
| recall: dos / fuzzing / spoofing | 1.00 / 1.00 / 0.98 |
| recall: masquerade | 0.82 |

Masquerade is the weak case, which is the expected result: the message rate stays
normal and only the timing changes, so detection rests on jitter collapse alone.
This is the gap that clock-skew fingerprinting (CIDS) was built for, and it is
worth naming as a limitation rather than hiding.

**Synthetic data is scaffolding, not a result.** It exists so the pipeline can be
built and tested before the real datasets arrive. Every number in the paper should
come from Car-Hacking and ROAD.

## Loading real data

Use the "Load a CSV log" button, or `POST /api/analyze/upload`.

- **HCRL Car-Hacking**: `Timestamp, CAN ID, DLC, DATA[0..7], Flag`. The published
  attack files have no header row; the loader detects this.
- **ORNL ROAD**: the `Label, Time, ID, Data` layout is handled. Other ROAD layouts
  may need a small change in `load_road`.
- A log with no label column still works. Detection runs, but the metrics tab
  reports that it cannot be evaluated.

Put real logs in `backend/data/` (gitignored).

## API

| method | path | purpose |
|---|---|---|
| POST | `/api/analyze/synthetic` | generate and analyze a synthetic capture |
| POST | `/api/analyze/upload` | analyze an uploaded CSV |
| GET | `/api/analysis/{id}/summary` | counts, params, detection metrics |
| GET | `/api/analysis/{id}/timeline` | per-window rate and score, plus alert and ground-truth spans |
| GET | `/api/analysis/{id}/ids` | per-ID table (capped; fuzzing creates hundreds of one-off IDs) |
| GET | `/api/analysis/{id}/ids/{can_id}/series` | rate over time for one ID |
| GET | `/api/analysis/{id}/alerts` | alert list with explanations |
| GET | `/api/analysis/{id}/alerts/{alert_id}` | alert, evidence packet, explanation |
| POST | `/api/analysis/{id}/alerts/{alert_id}/explain` | generate or regenerate one explanation |
| GET | `/api/analysis/{id}/metrics` | full evaluation report |
| POST | `/api/analysis/{id}/ask` | natural-language question over the analysis |

Analyses are held in memory and capped at eight, so restarting the API clears them.
A database is unnecessary for a demo and would be the first change for a real deployment.

## Tests

```bash
cd backend && python -m pytest -q
```

The suite checks that the generator labels what it injects, that the baseline
stretch stays clean, that every injected interval produces an alert, that every
explanation claim cites real evidence, and that the evidence packet stays small.

## Known limitations

- Offline analysis, not an in-vehicle IDS. Nothing here runs in real time on a bus.
- Detection thresholds are tuned on synthetic traffic and will need retuning per dataset.
- The natural-language query feature answers from alert metadata unless a hosted
  model is configured.
- Masquerade recall trails the other attack types (see above).
