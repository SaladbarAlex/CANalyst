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

### Appearance

The Appearance menu switches between Original and Pastel. Pastel uses a compact
traffic chart above the alerts and explanations. Both appearances have a
sun/moon toggle, and each remembers its own light/dark preference.

- [Pastel light](http://127.0.0.1:5173/?appearance=pastel&theme=light)
- [Pastel dark](http://127.0.0.1:5173/?appearance=pastel&theme=dark)
- [Original](http://127.0.0.1:5173/?appearance=original)

The [two-page dataset brief](../CANalyst_midterm/paper/CANalyst_Dataset_Brief.pdf)
explains the real-data results, what to inspect in the UI, and the remaining
work. The dashboard opens synthetic traffic; it does not automatically display
the saved real-data benchmark results.

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
  scripts/evaluate.py  synthetic and single-capture evaluation harness
  scripts/evaluate_midterm.py  reproducible real-data benchmark with separate normal baselines
  tests/             pytest suite (13 tests)
frontend/
  src/App.jsx        layout, data loading, tab state
  src/components/    TimelineChart, AlertList, ExplanationPanel, IdView, MetricsPanel, AskPanel, Controls
  src/styles.css     original design tokens, light and dark
  src/pastel.css     separately scoped Pastel layout and light/dark palettes
```

The pipeline is a five-stage flow: **ingest, feature extraction, detection,
explanation, dashboard.** Stages 1 to 3 use statistical features and detectors with no LLM calls.
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
| precision | 1.000 (sd 0.000) |
| recall | 0.907 (sd 0.011) |
| F1 | 0.951 (sd 0.006) |
| recall: dos / fuzzing / spoofing | 1.00 / 1.00 / 0.81 |
| recall: masquerade | 0.82 |

Masquerade is the weak case, which is the expected result: the message rate stays
normal and only the timing changes, so detection rests on jitter collapse alone.
This is the gap that clock-skew fingerprinting (CIDS) was built for, and it is
worth naming as a limitation rather than hiding.

These synthetic results were reproduced on October 20, 2026 with seeds 1–5,
150-second captures, the current rule detector, and threshold 0.55. The earlier
README's F1 of 0.963 came from an older detector configuration. The current
IsolationForest synthetic comparison has mean F1 0.540. Synthetic results check
pipeline behavior; the real-data benchmark below measures the current detector
on recorded vehicle traffic.

### October 20 preliminary real-data benchmark

The current rule detector was run at its existing 0.55 threshold with separate
normal baseline data, 0.5-second windows, and a 0.25-second stride. Metrics pool
window confusion counts across the specified evaluation captures, including
held-out normal traffic. No hosted LLM was called in this benchmark.

| dataset and scope | evaluated frame records | precision | recall | F1 | false positive rate |
|---|---:|---:|---:|---:|---:|
| HCRL: all four complete attack files + 120 s normal holdout | 16,803,792 | 0.997 | 0.980 | 0.989 | 0.003 |
| ROAD: 29 labeled attack captures + two 120 s ambient excerpts | 3,808,639 | 0.770 | 0.509 | 0.613 | 0.103 |

HCRL used the first 120 seconds of its separate normal recording for baseline
learning and seconds 121–241 for the normal holdout. ROAD used the full
`ambient_dyno_drive_basic_short.log` for baseline learning. Four ROAD accelerator
captures lack injection intervals and were excluded from labeled metrics.

The ROAD result identifies the next work: fabrication/spoofing recall was 92.7%,
but masquerade recall was 8.1%. The normal `extended_short` excerpt also produced
378 false alerts at the window level out of 479 windows, showing that a baseline
from basic driving does not cover all benign operating states. These are
development benchmarks: the rules were previously informed by Car-Hacking,
overlapping windows are correlated, and some source captures share traffic.

Reproduce from `backend/` with the downloaded data present:

```bash
.venv/bin/python -u -m scripts.evaluate_midterm --dataset hcrl --full-hcrl
.venv/bin/python -u -m scripts.evaluate_midterm --dataset road
```

Full confusion counts, per-capture scores, source hashes, baseline details,
exclusions, and limitations are in `backend/out/midterm_2026-10-20/`. Start with
`methodology.txt`, `hcrl_full/results.json`, and `road/results.json`. The separate
`hcrl/` folder preserves an earlier 120-second-per-attack pilot; its metrics must
not be mixed with the full HCRL run. Raw excerpts stay under ignored
`backend/data/evaluation_inputs/`.

## Loading real data

The command-line loader recognizes the downloaded datasets:

- **HCRL Car-Hacking**: `Timestamp, CAN ID, DLC, DATA[0..7], Flag`. The published
  attack files have no header row; the loader detects this.
- **ORNL ROAD**: candump `.log` files use the adjacent `capture_metadata.json`
  for interval/ID labels. The `Label, Time, ID, Data` CSV layout is also handled.
- Real arbitration IDs currently show unknown vehicle functions. The generator's
  signal names are used only for captures with synthetic provenance.

The dashboard's "Load a CSV log" button and `POST /api/analyze/upload` are a
simpler upload route. They do not yet accept a separate normal baseline and
ROAD metadata. Use the benchmark commands for the reported real-data results;
uploading the same file currently does not reproduce that evaluation protocol.

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
- The current fixed threshold was not selected using the October 20 evaluation
  results, but the rules were previously developed with Car-Hacking observations.
  These are preliminary development benchmarks, not untouched final test sets.
- ROAD results expose poor masquerade recall and false alarms under benign
  vehicle-state changes. Broader normal calibration and a separate validation
  protocol are needed before the final comparison.
- The real-data benchmark currently covers the rule detector. IsolationForest
  needs a separate-baseline fitting path before a fair real-data comparison;
  its existing external-baseline route can fall back to fitting evaluation data.
- The natural-language query feature answers from alert metadata unless a hosted
  model is configured.
- Masquerade recall trails the other attack types (see above).
