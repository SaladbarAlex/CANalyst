# CANalyst integration and handoff

The merged branch has verified detector results, matched model comparisons, and a class presentation package. The separate course report and independent human ratings remain open. [Final results](FINAL_RESULTS_2026-11-22.md) · [Presentation guide](FINAL_PRESENTATION_GUIDE.md)

## Git state

- Branch `rcd-llm-backend` merged `origin/main` at `ab491d5`.
- Shared base `b8201f1` had six local commits and thirteen incoming commits after it.
- Local snapshot `25e918f` preserves all 509 previously staged files.
- Merge commit `803f4db` combines the local snapshot with `origin/main`.
- The expansion outputs, source snapshot, and proposal files passed a credential scan for the local commit.
- Remote push and deployment require Nicholas's approval.

## Completed work

- Integrated real ROAD startup, separate baseline uploads, strict metadata validation, and the synthetic fallback. The dashboard keeps hosted requests explicit and supports cached metrics and cancellation after the current request.
- Preserved the October Benchmark view and added November detector and explainer results under Evaluation. All 54 saved incoming files remain byte-for-byte unchanged.
- Rebuilt the measurement caches and reran both detector datasets. ROAD v2 reduced single-reference false positives from 1,461 to 50 of 9,598 normal windows. Attack detections fell from 911 to 910 of 1,954. [Merged detector verification](../backend/out/final_2026-11-22/detection/verification.md)
- Kept detector v1 as the shared demo default. On HCRL, v1 detected 56 more gear spoofing windows than v2 and produced one false positive. V2 is a candidate for reducing ROAD false alarms. [Fresh benchmark](../backend/out/final_2026-11-22/detection/results.md)
- Verified the October v4 comparisons against the frozen evidence. GLM and the rule control got the same 86/89 attack alerts right. Qwen3-30B-A3B scored 38/89. Gemma-4-12B and GPTOSS-120B each produced one smoke reply. [Model results and provenance](../backend/out/final_2026-11-22/model_results.json)
- Reconciled the November prompt ablation. The `heldout` corpus contains 70 HCRL attacks and seven ROAD false alarms. The missing GLM `midterm100` ablation reply was one ROAD false alarm. The report records how it affects the benign-call denominator. [Final results](FINAL_RESULTS_2026-11-22.md)
- Recorded prior use of both datasets in October development. The November splits separate reference, tuning, and evaluation roles within that protocol. Independent ROAD attack classification and new-vehicle transfer remain open. [Provenance](FINAL_RESULTS_2026-11-22.md#provenance-and-limits)
- Prepared the 15-minute presentation with 15 timed slides and thirteen backup slides. The guide includes speaker handoffs, demo checks, and fallback steps. [Presentation](../output/presentation/CANalyst_Final_Presentation_15min.pptx) · [Presentation guide](FINAL_PRESENTATION_GUIDE.md)

## Remaining work

1. **Nicholas and Alexander**. Confirm the assigned symposium slot. Rehearse to 14:30 and reserve thirty seconds for transitions. Allow three minutes for questions afterward. Prewarm the offline ROAD dashboard and test one citation link and the Frozen benchmarks view. Keep the deck screenshots available. [Presentation guide](FINAL_PRESENTATION_GUIDE.md)
2. **Review coordinator and two independent human raters**. Distribute the blinded sheets and rubric. Keep the key private until both raters submit all 40 labels. Keep both sheets blank until the raters enter their judgments. Preserve both original sheets and adjudicate disagreements separately. Report agreement and support rates with their denominators. [Review rubric and materials](../backend/out/claim_review/heldout/)
3. **Report author**. Draft the 6 to 8 page, double-column final report in the supplied ACM template. Use the verified tables and exact denominators. State the outstanding human review and vehicle coverage limits. The report is due December 3, 2026, at 8 p.m. EST. [Report requirements](FINAL_PRESENTATION_GUIDE.md#separate-final-report-deadline)
4. **Future evaluation agent**. Define the ROAD attack evaluation protocol for an additional vehicle. Fix the split before reviewing any model replies. Measure detector recall and label accuracy on detected alerts. Treat this as follow-up research after class. [Coverage limits](FINAL_RESULTS_2026-11-22.md#provenance-and-limits)

After both raters submit, score the sheets from `backend/`:

```sh
.venv/bin/python -m scripts.claim_review score --set heldout
```

## Verification

- Backend passed 164 tests. Frontend passed 23 tests and the production build. The build retains its large JavaScript bundle advisory.
- Browser verification passed 19 checks, including installed ROAD startup, real ROAD uploads, and desktop and mobile benchmark views. It reported zero unexpected errors. [UI audit](../.impeccable/audit/2026-11-22T22-44-41Z__c-components-evaluationbenchmarkpanel-jsx-fbfa76a8.md)
- The offline verifier reproduced model results byte for byte. The fresh detector run used local traffic and made zero hosted model calls. [Model verification](../backend/scripts/summarize_final_models.py) · [Detector verification](../backend/out/final_2026-11-22/detection/verification.md)
- The presentation passed package, layout, font, and editable-chart checks. Reviewers checked all 28 rendered slides after export. The deck contains three editable charts, thirteen editable tables, and speaker notes throughout.

Run these checks from the repository root.

```sh
cd backend
.venv/bin/python -m pytest tests -q
cd ../frontend
npm test
npm run build
```
