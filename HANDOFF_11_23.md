# CANalyst handoff: November 23, 2026

**Continue from `main`. Use the reviewed deck and final report linked below.**

The application, four-dataset evaluation, human agreement results, presentation, animation, and six-page report are prepared.
Both reviewers completed 40 claims. Eight disagreements remain for human adjudication.
The remaining human tasks are rehearsal, video playback, course-template comparison, and final submission.

## 1. Get the shared work

Repository: <https://github.com/SaladbarAlex/CANalyst>

```sh
git clone --branch main git@github.com:SaladbarAlex/CANalyst.git
cd CANalyst
```

For an existing checkout, preserve local changes first.

```sh
git fetch origin
git switch main
git pull --ff-only
```

On November 24, `main` fast-forwarded to the completed project at `2c21a6f` without conflicts.
It contains the CTT work, teammate's TUE runs, both human ratings, and final integration fixes.
The final presentation, report, video, and handoff are all on `main`.
Use `git log -1 --oneline` for the current handoff revision.
The `rcd-llm-backend` branch remains available for history. Use new task branches from `main` for further work.
Pushing these files does not deploy the application.

## 2. Open these files

| File | Purpose |
| --- | --- |
| [Reviewed final deck](output/presentation/CANalyst_Final_Presentation_20min_Class.pptx) | 20-minute talk, 26 slides, detailed notes, embedded animation. |
| [Experiment video](output/presentation/assets/experiment-flow.mp4) | 42-second standalone fallback for slide 4. |
| [Presentation guide](docs/FINAL_PRESENTATION_GUIDE.md) | Timing, presenter split, demo, and Q&A. |
| [Final report PDF](output/paper/CANalyst_Final_Report.pdf) | Six-page ACM report. |
| [Report source and build](paper/README.md) | LaTeX source, bibliography, compilation, and template caveat. |
| [Current results](docs/FINAL_RESULTS_2026-11-23.md) | Readable findings and scientific limits. |
| [Verified evidence](backend/out/final_2026-11-23/model_results.md) | Exact counts and reproduction commands. |
| [Human review](docs/HUMAN_REVIEW.md) | Original ratings, agreement, and adjudication procedure. |
| [Adjudication sheet](backend/out/claim_review/heldout/adjudication.csv) | Eight blank human decisions. |
| [Dataset notes](docs/ADDITIONAL_DATASETS.md) | Downloads, licenses, hashes, adapters, and frozen runs. |

The older presentation files remain historical. Use the file ending in `_Class.pptx`.
The historical midterm is in `docs/midterm/`.
The original Clemson reference deck is in `docs/presentation_template/`.

## 3. Clear remaining tasks

| Owner | Task | Acceptance check |
| --- | --- | --- |
| Nicholas and Alexander | Rehearse together and confirm the symposium date. | Talk finishes by 19:30, followed by three minutes of questions. |
| Presenters | Test slide 4 and the offline demo on the class computer. | Video plays, citation opens, and fallback screenshots are available. |
| Human reviewers or third adjudicator | Resolve the eight disputed claims in the separate CSV. | Each row has a final S/U/C label, adjudicator, date, and reason. |
| Authors | Compare the report with Canvas's `cpsc8580template.zip`. | Course format matches without changing its class or margins. |
| Authors | Read the full paper and submit the approved version. | All claims match saved evidence. Submission completes before December 3, 8 p.m. EST. |

No new dataset download or hosted model run is needed for the current presentation.
The report and deck disclose unresolved ratings. They do not invent adjudicated support rates.

### Follow-up task for a review agent

After humans finish `adjudication.csv`:

1. Validate its eight IDs, labels, names, dates, and reasons.
2. Combine those decisions with the 32 originally agreed labels.
3. Report adjudicated counts across all 40 claims and all ten claims per arm.
4. Preserve original agreement of 80% and kappa of 0.521.
5. Update report and deck in a new version.
6. Render every changed page or slide and check its numbers.

Do not edit `rater_A.csv`, `rater_B.csv`, or `originals/`.
Do not regenerate the frozen review sample.
Rater B was an independent volunteer, not Alexander. Keep the submitted provenance accurate.

### Course requirements

The talk lasts 20 minutes, followed by three minutes of Q&A.
The listed sessions are November 24, December 1, and December 3.
The assigned team date still needs confirmation.
The presentation counts for 28% of the project grade.

The report counts for 42% and is due December 3, 2026, at 8 p.m. EST.
Use the unchanged ACM course template and six to eight double-column pages.
Include abstract, introduction, background, related work, methodology, results, conclusion, future work, and references.
System design counts double. Evaluation counts triple.

The final report uses installed `acmart` in `sigconf` format, extending the midterm.
The course ZIP was unavailable locally. Browser access was unavailable during the final revision.
Exact course-template compliance needs the comparison above.
Nicholas confirmed a course exception to the general AI restriction.

## 4. Run locally

Use Python 3.12 and Node.js. Start from the repository root.

Terminal 1:

```sh
cd backend
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
EXPLAINER=mock .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Terminal 2:

```sh
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --strictPort
```

| URL | Purpose |
| --- | --- |
| <http://127.0.0.1:5173/> | ROAD dashboard. Requires local raw captures. |
| <http://127.0.0.1:5173/?dataset=synthetic> | Clearly labeled synthetic fallback. |
| <http://127.0.0.1:5173/human-review.html> | Blinded claim-review form. |
| <http://127.0.0.1:5173/api/health> | Expect status `ok` and explainer `mock`. |
| <http://127.0.0.1:8000/docs> | API documentation. |

Each teammate runs these local URLs on their own computer.
The standalone `frontend/public/human-review.html` also works without a server.
Saved benchmarks and the offline control require no API key or VPN.
Restart the backend after pulling code changes.

### Raw data

Raw datasets are intentionally outside Git.
Follow [dataset notes](docs/ADDITIONAL_DATASETS.md) for DTU and TUE.
Existing local roots are:

- `backend/data/raw/hcrl-car-hacking/`
- `backend/data/raw/road/road/`
- `backend/data/raw/can-train-and-test-v2/extracted/cantrainandtest/can-train-and-test/`
- `backend/data/raw/tu-eindhoven-can-v2/`

The ROAD demo requires `attacks/correlated_signal_attack_3.log`, `ambient/ambient_dyno_drive_basic_short.log`, and `attacks/capture_metadata.json`.
Place these under the ROAD root above.
Download ROAD from [Zenodo](https://zenodo.org/records/10462796).
Download HCRL from the [publisher](https://ocslab.hksecurity.net/Datasets/CAN-intrusion-dataset).

## 5. Findings to present

| Experiment | Result | Limit |
| --- | --- | --- |
| ROAD detection | V1: 911 TP, 1,461 FP. V2: 910 TP, 50 FP. | Recall stays near 46.6%. V2 detects only 3/971 masquerade windows. |
| HCRL detection | V1: 8,450 TP, 1 FP. V2: 8,394 TP, 0 FP. | V2 misses 56 additional spoofing windows. V1 remains the live default. |
| October corrected explanations | GLM and control-v5 each score 86/89 attack labels. | Same three ROAD masquerade misses. Multiple corrections changed together. |
| November later slices | 70 HCRL attacks and seven ROAD false alarms. | Zero ROAD attack targets. Source recordings appeared in earlier development. |
| HCRL DoS-line experiment | Gemma 69 to 70, GLM 59 to 70, Qwen 37 to 69, each out of 70. | All six runs already score 17/17 on DoS. Gains occur in spoofing. |
| DTU / CTT | Control-v2 29/42. Hosted v2: Gemma 23, GLM 31, Qwen 34, each out of 42. | Per-vehicle references. Only 59 of 154 false alarms enter explanation scoring. |
| TU Eindhoven | Every arm scores 2/44 attack labels. | Only DoS labels are correct. Payload-fuzzing captures produce no alerts. |
| Human review | 32/40 agreement, kappa 0.521. Agreed labels: 26 supported, six unsupported. | Eight disagreements. Agreed-only support is not full-sample support. |

Keep windows, alerts, and claims as separate units.
Keep October corrected evidence separate from November historical prompt experiments.
A valid citation ID does not prove that its claim is supported.
No study establishes faster or more accurate human analysis.

All 42 selected CTT source files and 14 TUE source files match their frozen manifest hashes.
TUE training and testing are disjoint segments of one drive per vehicle.
TUE attacks are offline edits of the same testing segment.
The archived CTT freeze-script hash has no matching reachable source revision.
Current code fixes must not silently replace historical experiment outputs.

## 6. Code and evidence map

| Path | Responsibility |
| --- | --- |
| `backend/app/datasets.py`, `loader.py` | Dataset discovery, parsing, labels, and role definitions. |
| `backend/app/detector.py`, `features.py` | Measurements and detector profiles. |
| `backend/app/evidence.py`, `llm.py` | Evidence packets, control rules, prompts, and output validation. |
| `backend/app/benchmarks.py` | Saved experiment API and full-target reporting. |
| `backend/scripts/freeze_alerts.py` | Frozen target selection and provenance. |
| `backend/scripts/run_explanations.py`, `score_explanations.py` | Hosted runs, target records, and label scoring. |
| `backend/scripts/summarize_final_models.py` | Offline consolidated evidence verification. |
| `backend/out/final_2026-11-22/detection/` | Verified window-level results. |
| `backend/out/final_2026-11-23/` | Current explanation and human-review summary. |
| `backend/out/alerts/`, `explanations/` | Frozen packets and original replies. |
| `backend/out/claim_review/heldout/` | Review sheet, original ratings, results, and pending adjudication. |

The live path uses evidence-v4, control-v5, and prompt `can-evidence-v3`.
Detector v2, control-v2, and prompt v2 describe different settings.
Hosted inference needs individual credentials and Clemson access.
Do not start paid or hosted runs merely to inspect saved results.

## 7. Rebuild and verify

Run application checks:

```sh
cd backend
.venv/bin/python -m pytest tests -q
cd ../frontend
npm test
npm run build
```

Reproduce the offline evidence summary from `backend/`:

```sh
.venv/bin/python -m scripts.summarize_final_models --verify-raw \
  --out out/final_verify/model_results.json \
  --markdown out/final_verify/model_results.md
```

Omit `--verify-raw` when raw datasets are unavailable.
Keep a checkout with historical revision `11dc0ab` for archived hash verification.

Build the paper using [paper/README.md](paper/README.md).
Edit ordinary slide wording directly in PowerPoint when appropriate.
Scripted presentation rebuilds use `tools/build_clemson_final_presentation.mjs`.
They require the Codex Artifact Tool runtime and presentation skill helpers.
Set `RUNTIME_NODE_MODULES`, `RUNTIME_PYTHON`, and optionally `PRESENTATION_SKILL_DIR`.
Choose a new `PRESENTATION_OUTPUT_NAME` before running with `--final`.
The finalizer refuses to overwrite an existing final output.

Preserve historical artifacts. Use a new dated directory for changed experiments.
Keep raw data, credentials, installed dependencies, temporary renders, and Office lock files outside Git.

## 8. Final checks

- Backend: 192 tests passed after the shared-scoring fixes.
- Frontend: 23 tests and the production build passed. The existing bundle-size advisory remains.
- Saved replies: the offline verifier reproduced the summary byte for byte.
- Source data: all 56 selected CTT and TUE capture hashes matched.
- Human review: both original exports passed exact claim, evidence, ID, and label validation.
- Presentation: all 26 slides received individual visual checks. Package, layout, font, and native-chart validation passed.
- Report: all six pages received visual checks. References, denominators, and source claims received an independent review.

Native PowerPoint video playback and exact course-template comparison remain human checks.
The browser access host was unavailable during final verification.
