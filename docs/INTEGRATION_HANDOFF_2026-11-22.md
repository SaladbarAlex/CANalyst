# CANalyst integration and handoff

The merged branch has verified results, a 20-minute presentation, and an offline human review form. The symposium slot, rehearsal, final report, independent ratings, and new dataset benchmarks remain open. [Final results](FINAL_RESULTS_2026-11-22.md) · [Presentation guide](FINAL_PRESENTATION_GUIDE.md)

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
- Built the offline form for 40 blinded claims. Reviewers A and B can resume separate local drafts and export their own CSV files. Both study sheets have 0 of 40 ratings. [Review form](../frontend/public/human-review.html) · [Reviewer instructions](HUMAN_REVIEW.md)
- Downloaded and extracted can-train-and-test v2 and the TU Eindhoven CAN intrusion dataset v2. Verified the archives and sampled each capture. Benchmarking is pending. [Dataset receipt and parsing checks](ADDITIONAL_DATASETS.md)
- Built and checked the 20-minute deck using the paper presentation's Clemson template. It extends the midterm with corrected results and evaluation limits. All 26 slides have speaker notes. Slide 4 embeds a 42-second experiment video. [Presentation](../output/presentation/CANalyst_Final_Presentation_20min.pptx)
- Updated the rehearsal plan for 20 main slides and six appendix slides. It includes a two-minute dashboard demo and a suggested handoff at 7:20. [Presentation guide](FINAL_PRESENTATION_GUIDE.md)

## Remaining work

| Owner | Task | Acceptance evidence |
|---|---|---|
| Nicholas and Alexander | Confirm the assigned November 24, December 1, or December 3 symposium slot. Rehearse to 19:30. Reserve 30 seconds for recovery and three minutes for Q&A. Test the ROAD demo and video on the presentation computer. | Confirmed date and timed rehearsal. Citation link, Frozen benchmarks, and screenshot fallback ready. [Demo checklist](FINAL_PRESENTATION_GUIDE.md#offline-demo) |
| Review coordinator and two independent raters | Share the standalone HTML. Assign one slot to each rater. Keep the key private until both submit 40 labels. Preserve both returned CSVs and adjudicate disagreements separately. | Two completed CSVs. Report support and agreement with denominators. [Reviewer instructions](HUMAN_REVIEW.md) |
| Report agent and authors | Extend the midterm report in the supplied ACM LaTeX template. Keep all standard sections and use verified denominators. State the current human review and vehicle coverage. Nicholas confirmed a course exception to the general no-AI rule for this work. | A compiled 6 to 8 page double-column report in the unchanged template. Final report due December 3, 2026, at 8 p.m. EST. System design counts double and evaluation counts triple. [Report requirements](FINAL_PRESENTATION_GUIDE.md#separate-final-report-deadline) |
| Evaluation agent | Adapt the two downloaded datasets. Preserve source labels and split provenance. Fix the evaluation splits before inspecting model replies. Keep derived captures grouped by their source session. | Documented splits and reproducible results for each tested vehicle. Report detector recall on windows and classification on detected alerts with separate denominators. [Dataset notes](ADDITIONAL_DATASETS.md) · [Coverage limits](FINAL_RESULTS_2026-11-22.md#provenance-and-limits) |

After both raters submit, score the sheets from `backend/`:

```sh
.venv/bin/python -m scripts.claim_review score --set heldout
```

## Verification

- Backend passed 164 tests. Frontend passed 23 tests and the production build. The build retains its large JavaScript bundle advisory.
- Browser verification passed 19 checks, including installed ROAD startup, real ROAD uploads, and desktop and mobile benchmark views. It reported zero unexpected errors. [UI audit](../.impeccable/audit/2026-11-22T22-44-41Z__c-components-evaluationbenchmarkpanel-jsx-fbfa76a8.md)
- The offline verifier reproduced model results byte for byte. The fresh detector run used local traffic and made zero hosted model calls. [Model verification](../backend/scripts/summarize_final_models.py) · [Detector verification](../backend/out/final_2026-11-22/detection/verification.md)
- Chrome checks covered the review form on desktop, emulated mobile, and offline. The checks verified keyboard selection, separate reviewer drafts, reload, and CSV round trips. All 40 claim IDs, statements, and evidence fields matched the source after export. [Review form audit](../.impeccable/audit/2026-11-23T00-49-03Z__frontend-public-human-review-html.md)
- Rechecked the review form at 320px and 390px after fixing its opaque tap highlight. The Next label stays visible during touch. [Latest review form audit](../.impeccable/audit/2026-11-23T01-46-18Z__frontend-public-human-review-html.md)
- Checked all 26 final slides individually. Native charts, editable tables, fonts, slide geometry, and embedded video relationships passed validation.
- PowerPoint opened the deck without a repair warning. Automation timeouts prevented native slideshow playback verification. Test slide 4 during rehearsal and keep the standalone MP4 available.

Run these checks from the repository root.

```sh
cd backend
.venv/bin/python -m pytest tests -q
cd ../frontend
npm test
npm run build
```
