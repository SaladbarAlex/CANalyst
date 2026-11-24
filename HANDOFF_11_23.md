# CANalyst handoff: November 23, 2026

**Continue from `rcd-llm-backend`. Use the 20-minute final presentation.**

The application, saved experiments, review form, presentation, and video are ready to share.
Both human rating files are now complete. Eight disagreements need human adjudication.
The final ACM report remains incomplete.

### Update after both reviews

The two reviewers agreed on 32 of 40 claims (80%). Cohen's kappa is 0.521.
See [review results](backend/out/claim_review/heldout/results.md) and [current workflow](docs/HUMAN_REVIEW.md).
Keep both original CSVs unchanged. Record final adjudication decisions separately.

The teammate also added CTT and TU Eindhoven experiments through commit `12f21b8`.
Audit these new experiments before updating the presentation's dataset claims.
The original handoff below describes the earlier snapshot, including its then-pending dataset work.

## 1. Get the shared work

Repository: <https://github.com/SaladbarAlex/CANalyst>

Clone the working branch:

```sh
git clone --branch rcd-llm-backend git@github.com:SaladbarAlex/CANalyst.git
cd CANalyst
```

For an existing checkout, preserve local changes before switching branches:

```sh
git fetch origin
git switch rcd-llm-backend
git pull --ff-only
```

The branch includes `origin/main` through `ab491d5` and all previously unpushed project work.
Merge commit `803f4db` resolved the integration. Commit `a3a3d86` added the final deck and review workflow.
This handoff adds the midterm sources and presentation template inside the repository.
Use `git log -1 --oneline` for the current handoff commit.

Work on this branch or create a task branch from it. Avoid replacing saved experiments with regenerated files.
The branch push publishes these files. It does not merge the branch into `main` or deploy the application.

## 2. Open these files first

| File | Purpose |
| --- | --- |
| [Final 20-minute PPTX](output/presentation/CANalyst_Final_Presentation_20min.pptx) | Current class presentation. Includes 20 main slides, six backup slides, and speaker notes. |
| [Experiment video](output/presentation/assets/experiment-flow.mp4) | Standalone 42-second fallback. The same video is embedded on slide 4. |
| [Presentation guide](docs/FINAL_PRESENTATION_GUIDE.md) | Timing, presenter handoff, demo instructions, and Q&A facts. |
| [Verified final results](docs/FINAL_RESULTS_2026-11-22.md) | Use these numbers and caveats in the report and presentation. |
| [Human review instructions](docs/HUMAN_REVIEW.md) | Independent ratings and CSV collection. |
| [Offline review form](frontend/public/human-review.html) | Self-contained form with 40 blinded claims. |
| [Additional datasets](docs/ADDITIONAL_DATASETS.md) | Download links, licenses, hashes, parsing checks, and adapter requirements. |
| [Midterm LaTeX](docs/midterm/paper/midterm.tex) | Historical paper source to extend for the final report. |
| [Midterm bibliography](docs/midterm/paper/references.bib) | Existing references. |
| [Midterm PDF](docs/midterm/paper/midterm.pdf) | Historical results and original paper structure. |
| [Midterm presentation](docs/midterm/presentation/CANalyst_midterm_presentation.pptx) | Original talk for continuity. |
| [Clemson presentation template](docs/presentation_template/LibreCAN_Presentation_Clemson_Final.pptx) | Nicholas's reference design. Its research content is not CANalyst evidence. |

The older 15-minute deck remains in Git for history. Use the 20-minute deck for class.
Some historical notes name sibling folders. Their midterm and template files now have the repository paths above.

## 3. Next tasks and acceptance checks

| Priority | Owner | Work | Done when |
| --- | --- | --- | --- |
| 1 | Nicholas and Alexander | Confirm the symposium date. Rehearse the talk and demo. Test slide 4 in PowerPoint. | Talk finishes by 19:30. Video plays on the class computer. The saved-screen fallback is ready. |
| 2 | Two human reviewers | Complete all 40 claims independently. Use separate browser profiles or devices. | Both original CSVs contain 40 actual human labels. No labels come from an agent. |
| 2 | Review agent and coordinator | Validate returned CSVs, score agreement, and retain disagreements for human adjudication. | Validated originals, scorer outputs, and separate adjudication decisions exist with clear denominators. |
| 3 | Report agent and authors | Extend the midterm paper using the course ACM template. Use the verified results and limitations. | A reviewed 6 to 8 page double-column PDF compiles and covers all required sections. |
| 4 | Dataset agent | Add adapters and label catalogs for the downloaded datasets. Freeze vehicle and session splits first. | Tests cover source formats and labels. Split manifests prevent duplicate or derived-session leakage. |
| 5 | Evaluation agent | Benchmark the new datasets after adapter checks. Keep detection and explanation metrics separate. | Results include source hashes, settings, failures, denominators, and reproducible commands. |

Prioritize rehearsal, human review, and the report before expanding experiments.
Do not delay the class presentation to imply unmeasured results from the new datasets.

### Presentation and report requirements

- The symposium dates are November 24, December 1, and December 3, 2026. The assigned team date remains unconfirmed.
- The talk gets 20 minutes, followed by three minutes of Q&A.
- Presentation grading covers timing, structure, presentation quality, and content quality.
- The final report is due December 3, 2026, at 8:00 p.m. EST.
- Use the course's unchanged ACM LaTeX template. Write 6 to 8 double-column pages.
- Include abstract, introduction, background, related work, methodology, results, conclusion with future work, and references.
- System design counts double. Evaluation counts triple.
- Download `cpsc8580template.zip` from Canvas. The course-provided ZIP is not available in this repository.
- Nicholas confirmed an exception to the course's general AI restriction for this work.

The current midterm source uses `acmart`. It is a starting point, not proof of final-template compliance.
The final ACM report has not been written. `tools/build_report.py` builds an older project-status PDF, not that report.

## 4. Run the application locally

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

| URL | Use |
| --- | --- |
| <http://127.0.0.1:5173/> | Main dashboard. Default startup requires the local ROAD capture. |
| <http://127.0.0.1:5173/?dataset=synthetic> | Working demo without raw dataset downloads. Identify it as synthetic. |
| <http://127.0.0.1:5173/human-review.html> | Blinded human review. |
| <http://127.0.0.1:5173/api/health> | Health check. Expect `status: ok` and `explainer: mock`. |
| <http://127.0.0.1:8000/docs> | Local API documentation. |

These are local URLs. Each teammate must run the servers on their own computer.
The standalone review HTML also works without servers or an internet connection.
The saved benchmarks and offline control require no API key or Clemson VPN.

Use **Evaluation > Frozen benchmarks** for November comparisons. Use **Benchmark** for the historical October comparisons.
Restarting the backend clears in-memory analyses. It does not remove saved experiment files.

### Real-data installation

Raw captures are intentionally absent from Git. Install them before reproducing detection runs or the default ROAD demo.

| Dataset | Download and expected location |
| --- | --- |
| HCRL Car-Hacking | Use the [publisher download](https://ocslab.hksecurity.net/Datasets/car-hacking-dataset/). Place attack CSVs in `backend/data/raw/hcrl-car-hacking/`. |
| HCRL normal traffic | Place the normal file at `backend/data/raw/hcrl-car-hacking/normal_run_data/normal_run_data.txt`. |
| ROAD | Download `road.zip` from [Zenodo](https://zenodo.org/records/10462796). Extract into `backend/data/raw/road/`, preserving the archive's `road/` directory. |
| DTU can-train-and-test v2 | Follow [dataset notes](docs/ADDITIONAL_DATASETS.md). Nicholas has 236 CSVs under `backend/data/raw/can-train-and-test-v2/`. |
| TU Eindhoven CAN v2 | Follow [dataset notes](docs/ADDITIONAL_DATASETS.md). Nicholas has 29 logs under `backend/data/raw/tu-eindhoven-can-v2/`. |

The default ROAD demo needs these three files:

```text
backend/data/raw/road/road/attacks/correlated_signal_attack_3.log
backend/data/raw/road/road/ambient/ambient_dyno_drive_basic_short.log
backend/data/raw/road/road/attacks/capture_metadata.json
```

The two additional datasets are downloaded and checked on Nicholas's computer. Their adapters and benchmark results do not exist yet.
DTU has repeated content across published sets. Keep published splits and check duplicates before pooling.
TU Eindhoven's car attack traces use offline edits of benign captures. Its prototype also includes live testbed attacks.
Keep derived captures with their original session. Preserve source licenses and documented labels.

## 5. Complete human review without contaminating ratings

Suggested assignments are Nicholas as A and Alexander as B. Confirm assignments before collecting labels.
Share only `frontend/public/human-review.html` with raters. Keep the identity key out of their materials.
Keep the tracked identity key and claim-to-model assignments unopened until both reviewers submit their CSVs.
Use different raters if the proposed reviewers already know those assignments.
Do not explain how an agent would label a study claim before humans submit their decisions.

Each reviewer must:

1. Open the HTML or review URL.
2. Choose the assigned reviewer slot.
3. Read the rubric and rate all 40 claims.
4. Select **Download CSV**.
5. Return the assigned `rater_A.csv` or `rater_B.csv` to the coordinator.

Both tracked rater files now contain 40 labels. Agreement is scored, and eight disagreements remain unresolved.
Each arm contributes 3 DoS, 3 fuzzing, 2 spoofing, and 2 ROAD false-alarm claims.
The packet covers 27 unique alerts across one rule control and three hosted prompt-v2 models.
It excludes ROAD attack alerts, summary fields, uncited claims, and the DoS-line ablation.

The review agent must validate returned files before scoring:

- Require exactly the 40 unique IDs `C001` through `C040`.
- Require exact labels `S`, `U`, or `C` on every row.
- Compare each claim and evidence field against the frozen `sheet.csv`.
- Preserve both original exports before installing copies in the matching rater slots.
- Reject duplicate IDs explicitly. The existing scorer collapses duplicates and normalizes label strings.

After both files pass validation, run from the repository root:

```sh
cd backend
.venv/bin/python -m scripts.claim_review score --set heldout
```

The scorer writes `backend/out/claim_review/heldout/results.json` and `results.md`.
It reports agreement and Cohen's kappa from the original paired ratings.
Its per-arm support rates use agreed claims only. Report that denominator explicitly.
Have a human adjudicate disagreements in a separate file. Preserve the original judgments and agreement statistics.
Calculate final adjudicated rates separately before updating the deck or report.

`backend/scripts/summarize_final_models.py` still hardcodes human review as incomplete.
Update that accounting before producing a new consolidated summary. Existing dated summaries remain historical snapshots.
Avoid regenerating the sample with `sample --force`.
Use `node tools/build_human_review.mjs` only to refresh the HTML from the existing frozen sheet.

## 6. Results that can be claimed now

Use [FINAL_RESULTS_2026-11-22.md](docs/FINAL_RESULTS_2026-11-22.md) as the main narrative source.
The saved JSON files contain exact counts, model settings, and source hashes.

| Experiment | Verified result | Limit |
| --- | --- | --- |
| Fresh ROAD detection, single reference | V1: 911 TP, 1,461 FP. V2: 910 TP, 50 FP. Denominators: 1,954 attack and 9,598 normal windows. | Recall stays near 46.6%. Masquerade detections are only 4/971 and 3/971. |
| Fresh HCRL detection, single reference | V1: 8,450 TP, 1 FP. V2: 8,394 TP, 0 FP. Denominators: 8,616 attack and 13,458 normal windows. | V2 misses 56 more spoofing windows. The live default remains v1. |
| October corrected v4 explanations | Control-v5 and GLM each score 69/69 HCRL and 17/20 ROAD attacks. Qwen scores 24/69 and 14/20. | Both leading arms misclassify the same three detected ROAD attack alerts. |
| November heldout-named corpus | Contains 70 HCRL attacks and seven ROAD false alarms. Historical control-v2 scores 70/70 HCRL attacks. | Contains zero ROAD attack alerts. This is not new-vehicle evidence. |
| November DoS-line ablation | HCRL correct labels: Gemma 69 to 70, GLM 59 to 70, Qwen 37 to 69, each out of 70. | All six runs already score 17/17 on DoS. Gains occur in spoofing labels. |
| Prior claim audit | An AI-assisted purposive audit found 13 supported and five unsupported claims among 18. | This is not independent human evaluation or a population support estimate. |

Important distinctions:

- Keep detector windows, classified alerts, and reviewed claims as separate units.
- Keep October corrected evidence separate from November historical prompt experiments.
- Do not credit one correction for the whole midterm-to-v4 improvement. Several inputs and settings changed.
- Do not equate valid citation IDs with supported statements.
- Earlier development touched both datasets' later evaluation recordings. Do not describe them as untouched project-level holdouts.
- No study has established faster or more accurate human analysis.
- New dataset downloads do not establish new benchmark performance.

## 7. Code and evidence map

| Path | Responsibility |
| --- | --- |
| `backend/app/loader.py` | Capture parsing and normalization. |
| `backend/app/datasets.py` | Dataset roots, capture families, and role assignments. |
| `backend/app/features.py`, `windowstats.py`, `detector.py` | Measurements, baseline statistics, and alert profiles. |
| `backend/app/evidence.py` | Evidence scopes, missing values, and packet construction. |
| `backend/app/llm.py` | Offline control, hosted adapters, prompts, and output validation. |
| `backend/app/pipeline.py`, `main.py` | Analysis lifecycle and API routes. |
| `frontend/src/App.jsx`, `frontend/src/components/` | Dashboard, citation navigation, and saved benchmark views. |
| `backend/out/final_2026-11-22/` | Verified model summary and fresh detection results. |
| `backend/out/frozen_2026-10-30_v4/` | Corrected October frozen explanation packets. |
| `backend/out/alerts/`, `backend/out/explanations/` | November targets and saved model replies. |
| `backend/out/claim_review/heldout/` | Frozen review sheet, blank rater files, rubric, and coordinator identity key. |
| `backend/scripts/summarize_final_models.py` | Offline verification of saved model experiments. |
| `backend/scripts/benchmark.py` | November detector benchmark. |
| `backend/scripts/claim_review.py` | Review sampling and agreement scoring. |

The live corrected path uses evidence-v4, control-v5, and prompt `can-evidence-v3`.
November experiments use explicit historical scopes, control versions, and prompt versions.
Detector profile v2 is a different setting from prompt v2 or control-v2.

Use a new dated output directory for each changed experiment. Save inputs, code versions, settings, raw replies, and failures.
Keep the saved October and November artifacts unchanged so comparisons remain traceable.

Hosted inference needs each teammate's own credentials and Clemson network access or CUVPN.
Keep credentials in the ignored local environment. Check current model availability before selecting a new arm.
Do not start new hosted inference merely to run the dashboard or view saved results.

## 8. Presentation editing and rebuilds

Edit the committed PPTX directly in PowerPoint for normal revisions.
The deck uses the supplied Clemson orange and purple template, with native charts and tables.
All 26 final slides passed visual checks. Slide 4's embedded MP4 matches the standalone video byte for byte.
PowerPoint opened the deck without a repair warning. Automation timeouts prevented native playback verification.
Test the video on the presentation computer. Keep the standalone MP4 and screenshot fallback available.

Scripted rebuilds use `tools/build_clemson_final_presentation.mjs` and the tracked template in `docs/presentation_template/`.
They need the Codex Artifact Tool runtime and presentation skill helpers. Regular application dependencies do not provide those tools.

Configure these variables for the agent's installed runtime:

| Variable | Meaning |
| --- | --- |
| `RUNTIME_NODE_MODULES` | Directory containing `@oai/artifact-tool`. |
| `PRESENTATION_SKILL_DIR` | Installed presentation skill directory, including `container_tools`. |
| `RUNTIME_PYTHON` | Python executable with the presentation helper dependencies, including `lxml`. |
| `PRESENTATION_OUTPUT_NAME` | New output filename for a final export. Existing final files are not overwritten. |

Run preview generation from the repository root:

```sh
node tools/build_clemson_final_presentation.mjs
```

Add `--final` and choose a new `PRESENTATION_OUTPUT_NAME` to validate and export a revised final deck.
Review all changed slides and check the embedded video afterward.
The older builder targets the superseded 15-minute deck. Use the Clemson builder for current work.
The Swift animation builder needs macOS AVFoundation. The committed MP4 requires no rebuild to play.

## 9. Verification and known gaps

Last full integration checks passed 164 backend tests, 23 frontend tests, and 19 dashboard browser checks.
The current frontend build also passed. It retains a JavaScript bundle-size advisory.
The human review form passed desktop, keyboard, offline, mobile, draft separation, and CSV round-trip checks.
These results describe the verified implementation before new teammate changes.

Run relevant checks after changes:

```sh
cd backend
.venv/bin/python -m pytest tests -q
cd ../frontend
npm test
npm run build
```

Test review-page behavior only in a disposable browser profile. Use temporary labels and never submit the test CSV as study data.
Verify reload persistence, separate A/B drafts, 40 exported claim rows, and offline operation.

Raw data, credentials, environments, installed packages, caches, private QA renders, and Office lock files remain outside Git.
Reinstall dependencies and download datasets as described above. The final deck, media, paper sources, and review form are versioned.
