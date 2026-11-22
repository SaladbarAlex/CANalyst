# CANalyst integration and agent handoff

The integration combines the local dashboard and evidence corrections with the incoming November benchmark tools.
Use the tasks below to assign the remaining research and release work.

## Git state

- Branch: `rcd-llm-backend`.
- Incoming revision: `origin/main` at `ab491d5`.
- Shared base: `b8201f1`. The branches contained six local commits and thirteen incoming commits.
- Local snapshot: `25e918f` preserves all 509 previously staged files.
- Merge commit: `803f4db` combines the local snapshot with `origin/main`.
- Existing untracked files remain separate. They include model expansion outputs, source snapshots, proposal documents, and `.gitattributes`.
- No remote push or deployment was requested.

## Combined behavior

- Keep the real ROAD startup example, separate baseline uploads, metadata validation, and synthetic demo.
- Keep explicit hosted-model actions, model selection, cached-only metrics, and cancellation after the current explanation.
- Keep corrected live evidence, identifier warnings, normal-only forest calibration, and blinded question context.
- Add explicit detector profiles, historical control rules, historical prompts, and alert/window evidence scopes.
- Keep the existing Benchmark view for October experiments.
- Add November detection results, frozen explainer comparisons, packet downloads, and prediction submissions under Evaluation.
- Serve October detector history at `/api/benchmark/detectors`.
- Serve November detection results at `/api/benchmark/detection`.
- Keep saved experiment files unchanged. Convert nonfinite saved metrics to JSON `null` only when serving responses.

The live defaults and historical experiment versions serve different purposes.
Do not treat matching version numbers across these families as matching inputs or behavior.

## Current evidence

The November detection benchmark reports lower ROAD false-positive rates with profile v2.
With its single reference, reported FPR falls from 0.152 to 0.005, while rounded recall remains 0.466.
These are saved upstream results, not a new run of the merged implementation.
The live default remains profile v1.

The incoming held-out explainer set contains 77 alerts: 70 HCRL attacks and seven ROAD false alarms.
It cannot establish ROAD attack classification performance.
The detection benchmark separately includes ROAD attack windows.
Review prior October data use before calling any merged-project evaluation untouched.

The DoS prompt-line ablation already exists for GLM, Gemma, and Qwen.
The ROAD-only midterm GLM ablation has 30 replies for 31 target alerts.
Its manifest records one unfinished false-alarm reply.

The local Qwen3-30b-a3b-instruct-fp8 expansion contains complete 69-alert HCRL and 31-alert ROAD runs.
The comparator verified matching evidence and targets against the local v4 control.
Qwen classified 24/69 HCRL attacks correctly, versus 69/69 for the control.
Qwen classified 14/20 ROAD attacks correctly, versus 17/20 for the control.
Gemma-4-12b and GPTOSS-120b have one-alert smoke outputs only.
These expansion artifacts remain untracked.
The October model-expansion document predates these outputs.

Both held-out human rating sheets contain 40 unanswered rows.
Citation validity and automated checks do not substitute for independent human ratings.

Sources:

- [November detection results](../backend/out/benchmark/results.md)
- [Held-out explainer results](../backend/out/explanations/heldout/scores.md)
- [Held-out alert manifest](../backend/out/alerts/heldout/manifest.json)
- [Incomplete GLM ablation manifest](../backend/out/explanations/midterm100/glm-5.3_v2-dosv1_alert/run.json)
- [Human review rubric](../backend/out/claim_review/heldout/rubric.md)
- [October development audit](PROGRESS_2026-10-30.md)

## Agent tasks

### 1. Reconcile experiment provenance and results

Assign one evaluation agent. Complete this task before selecting a new default or updating headline performance claims.

- Inspect `app/datasets.py`, `scripts/benchmark.py`, both frozen-corpus families, and their saved manifests.
- Document capture overlap and prior development use across October and November experiments.
- Save the verified Qwen comparison against `explanations_v4_2026-10-30_control_v5` using `scripts.compare_models`.
- Write comparisons to a new directory. Confirm each destination does not exist before running the comparator.
- Record corpus hashes, attempted counts, failures, latency, and semantic warnings.
- Verify results from the merged detector before proposing profile v2 as the live default.
- Use new output paths for fresh experiments. Preserve all saved results and frozen packets.
- Rebuild measurement caches with `scripts.build_cache --force` when input or measurement code changes.

The cache builder skips existing paths without checking source or code changes.
No measurement caches existed locally during this integration.

Done when: one results table identifies each corpus, protocol, model setting, failure denominator, and limitation.
Include a written recommendation about the default detector with supporting measurements.

### 2. Complete independent claim review

Assign a review coordinator and two independent human raters.

- Give both raters the existing blinded sheet and `backend/out/claim_review/heldout/rubric.md`.
- Keep `key.json` hidden from raters until their labels are final.
- Collect all 40 labels in each of `rater_A.csv` and `rater_B.csv`.
- Run `.venv/bin/python -m scripts.claim_review score --set heldout` from `backend/`.
- Adjudicate disagreements separately. Preserve the original ratings.
- Report agreement and support rates with their denominators.

Done when: both sheets are complete, agreement results exist, and disagreements have recorded decisions.
Agents can prepare the materials but must not invent independent human judgments.

### 3. Close model and ROAD coverage gaps

Assign one experiment agent after task 1 establishes the protocol.

- Define new ROAD attack evaluation coverage before inspecting model answers.
- Distinguish detected-alert classification from detector recall.
- Record the missing GLM ROAD ablation answer as missing, or run an explicitly named follow-up.
- Decide whether full Gemma-4-12b and GPTOSS-120b runs justify additional hosted calls.
- Confirm current service access and model names before any new hosted experiment.
- Preserve exact prompts, evidence, model settings, failures, usage, and latency.

Done when: the report either includes matching ROAD attack comparisons or explicitly limits its claims to measured coverage.
Do not present one-alert smoke results as full comparisons.

### 4. Update the report and prepare publication

Assign one documentation agent after tasks 1 and 2.

- Update the current report and presentation using the reconciled results table.
- Explain the October and November experiment families separately.
- Replace outdated model-expansion status with verified artifact counts.
- Identify untracked files that belong in version control, including expansion outputs and `.gitattributes`.
- Keep credentials, raw datasets, caches, and generated temporary files out of version control.
- Obtain Nicholas's approval before pushing, opening a public review, or deploying.

Done when: documentation matches the measured results and the proposed publication diff is ready for review.

## Verification

- Backend: 163 tests passed after final integration changes.
- Frontend: 23 tests and the production build passed.
- Incoming artifacts: all 54 saved files match `origin/main` byte for byte.
- Source checks: no conflict markers or whitespace errors remain outside preserved result artifacts.
- Hosted calls: none were made during integration verification.
- Browser: 19 checks passed, including actual ROAD uploads, installed ROAD startup, and desktop/mobile benchmark views.
- Browser errors: no page errors or unexpected HTTP/console errors occurred.
- UI audit: no critical or high-priority findings remain in the changed view.

Browser evidence is saved locally at `/private/tmp/canalyst-merge-ui-2026-11-22/results.json`.
The audit is saved at `.impeccable/audit/2026-11-22T22-44-41Z__c-components-evaluationbenchmarkpanel-jsx-fbfa76a8.md`.

The frontend build retains its existing large JavaScript bundle advisory.
Full detector benchmarks and hosted-model experiments were not rerun for this merge.

Run the automated checks from the repository root:

```sh
cd backend
.venv/bin/python -m pytest tests -q
cd ../frontend
npm test
npm run build
```
