# CANalyst final presentation guide

**Rehearse to 19:30 for the 20-minute talk.** Keep 30 seconds for transitions or demo recovery. Allow three minutes for questions afterward. The symposium runs November 24, December 1, and December 3, 2026. Confirm the assigned group slot. The rubric covers timing, structure, presentation quality, and content quality. Source: Lecture Note 01 on Canvas, slides 25 and 28.

Presenters are Nicholas DiGennaro and Alexander Salazar, Clemson University. Open the [20-minute PowerPoint deck](../output/presentation/CANalyst_Final_Presentation_20min.pptx) in Presenter View to see the speaker notes.

## Rehearsal schedule

Suggested split. Nicholas presents slides 1 through 8. Alexander starts slide 9 at 7:20. Keep slides 21 through 26 available for questions.

| Slide | Allotted | Elapsed | Speaking cue |
|---|---:|---:|---|
| 1. CANalyst | 0:25 | 0:25 | Ask whether an analyst can trace an alert explanation to measured evidence. |
| 2. Project timeline | 0:45 | 1:10 | Trace the midterm baseline, October corrections, and November evaluation. |
| 3. How CANalyst works | 1:00 | 2:10 | Trace traffic from a capture and separate normal reference to windows, alerts, and cited claims. |
| 4. Experiment in motion | 0:55 | 3:05 | Play the 42-second video. Use the remaining time to connect the stages to the experiment. |
| 5. Real-data evaluation setup | 1:15 | 4:20 | Introduce HCRL and ROAD. Distinguish labeled windows, detected alerts, and cited claims. |
| 6. Detector changes | 0:55 | 5:15 | Explain the timing guard and how the v2 profile handles ROAD traffic. |
| 7. Detection on ROAD | 1:20 | 6:35 | Give the false-positive rates, recall, and masquerade counts for both profiles. |
| 8. HCRL detector comparison | 0:45 | 7:20 | Explain the v1 default and the result from the whitelist plus interval baseline. Hand off to Alexander. |
| 9. LLM evaluation on Clemson RCD | 0:45 | 8:05 | Describe equal evidence, the rule control, and the attack-label denominator. |
| 10. First LLM results | 0:55 | 9:00 | Explain what the first development run exposed and how it guided corrections. |
| 11. Corrected v4 results | 1:15 | 10:15 | Give matched October v4 GLM, rule control, and Qwen results on the development alerts. |
| 12. Corrections since midterm | 1:00 | 11:15 | Explain the detector, evidence, and evaluation changes that affect interpretation. |
| 13. November coverage | 0:45 | 12:00 | Give the 77-alert split and identify the reused sessions. State that ROAD supplied false alarms only for this alert set. |
| 14. DoS-line ablation | 0:55 | 12:55 | Describe the one-line change and show where classification and reply counts changed. |
| 15. Claims and citations | 1:05 | 14:00 | Show a cited observation and an unsupported inference. Describe the earlier 18-claim audit. |
| 16. Human review | 1:10 | 15:10 | Show the blinded form and the S, U, and C labels. State that both independent ratings are pending. |
| 17. Dashboard demo | 2:00 | 17:10 | Trace a ROAD alert to one evidence item, then open Frozen benchmarks. |
| 18. Additional datasets | 0:40 | 17:50 | Name the two downloaded datasets and their coverage. Benchmark results are pending. |
| 19. Limits and next steps | 1:10 | 19:00 | Discuss masquerade misses, session reuse, human review, and testing on more vehicles. |
| 20. Questions | 0:30 | 19:30 | Restate the finding and invite questions. |

Suggested handoff at 7:20. “Profile v2 cuts ROAD false alarms. Masquerade recall stays low. Alexander will explain how we evaluated the alerts that reached the explanation stage.”

### Six backup slides

21. ROAD detector results
22. HCRL detector results
23. Data provenance
24. Models and latency
25. Human review coverage
26. References

## Offline demo

### Preflight

1. Confirm the Python environment and frontend dependencies are installed before class. See the [project quick start](../README.md#quick-start).
2. Check that `backend/data/raw/road/road` contains the following files:
   - `attacks/correlated_signal_attack_3.log`
   - `ambient/ambient_dyno_drive_basic_short.log`
   - `attacks/capture_metadata.json`
3. Start the API and dashboard in separate terminals from the repository root. Keep both terminals open.

   ```sh
   cd backend
   EXPLAINER=mock .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

   ```sh
   cd frontend
   npm run dev -- --host 127.0.0.1 --strictPort
   ```

4. Confirm the API returns `status: ok` and `explainer: mock` through the dashboard proxy.

   ```sh
   curl --fail --silent --show-error http://127.0.0.1:5173/api/health
   ```

5. Open the [ROAD dashboard](http://127.0.0.1:5173/). Wait for the installed capture of 41,829 frames to finish loading. Select its alert and test a citation link.
6. Open **Evaluation > Frozen benchmarks** and confirm the saved results load. Keep the [dashboard](../output/presentation/assets/road-dashboard.png), [citation](../output/presentation/assets/citation-navigation.png), and [benchmark](../output/presentation/assets/frozen-benchmarks.png) screenshots ready.
7. Test the video on slide 4 with the presentation computer and projector. Keep the [local MP4](../output/presentation/assets/experiment-flow.mp4) and [poster](../output/presentation/assets/experiment-flow.png) ready.
8. Open the [offline review form](../frontend/public/human-review.html) in a fresh browser profile. Show the form without entering a study judgment. [Reviewer instructions](HUMAN_REVIEW.md)

### Demo sequence, 2:00

| Time | Action |
|---|---|
| 0:00 to 0:20 | Show the ROAD timeline and one alert. Name the separate normal reference. |
| 0:20 to 1:05 | Open the alert. Identify the offline rule control. Click one citation and point to its measurement. |
| 1:05 to 1:40 | Open **Evaluation > Frozen benchmarks**. Show the 70 HCRL attack alerts and seven ROAD false alarms. |
| 1:40 to 1:50 | Point to the human review page. |
| 1:50 to 2:00 | Return to slide 17. Advance to slide 18. |

If ROAD data fails to load, use the [synthetic startup](http://127.0.0.1:5173/?dataset=synthetic) and identify it as synthetic. If the browser or server stalls, switch to the saved screenshots. Use only saved hosted-model replies during the presentation.

The final file contains the verified 42-second MP4. PowerPoint opened the deck without a repair warning. Automation timeouts prevented native slideshow playback verification. Confirm playback during the preflight above.

## Claims to use in Q&A

**Did the detector improve?** The merged ROAD rerun reproduces the saved November counts. With one reference, v2 lowers false positives from 1,461 to 50 of 9,598 normal windows. Precision rises from 38.4% to 94.8%. Both recall values round to 46.6%. Masquerade detections fall from four to three of 971 windows. [Merged detector verification](../backend/out/final_2026-11-22/detection/verification.md)

**Why keep v1 as the default?** The merged HCRL run gives v1 one false positive and 8,450 attack windows detected, out of 8,616. V2 gives zero false positives and detects 8,394 attack windows. The jitter guard accounts for the change from 32 saved November v1 false positives to one in the merged run. The whitelist plus interval baseline gives the best HCRL F1 in this comparison, 0.996. [Merged verification](../backend/out/final_2026-11-22/detection/verification.md) and [full benchmark](../backend/out/final_2026-11-22/detection/results.md)

**Does the LLM beat the rules?** In October v4, GLM and rule control-v5 got the same 86 of 89 attack alerts right. Each got 69/69 HCRL and 17/20 ROAD. Qwen3-30B-A3B scored 24/69 and 14/20. In November `heldout`, historical rule control-v2 got 70/70 HCRL attacks correct. Score comparisons apply to their respective frozen sets. [Final results](FINAL_RESULTS_2026-11-22.md)

**How well does it classify ROAD attacks?** The October development set contains 20 detected ROAD attack alerts. The November `heldout` set contains zero ROAD attack alerts and seven ROAD false alarms. ROAD attack windows do appear in the separate November detection benchmark. [November alert manifest](../backend/out/alerts/heldout/manifest.json)

**What did changing the prompt do?** On 70 HCRL attack alerts, restoring the earlier DoS line moved Qwen3.6-27B from 37 to 69 correct and GLM from 59 to 70. All hosted variants classified the 17 DoS alerts correctly. The gains appeared in spoofing labels. GLM had five failed replies in the original run and one in the ablation, across the 77 targets. [November ablation scores](../backend/out/explanations/heldout/scores.md)

**Do the citations prove the explanation is faithful?** They link the explanation to evidence. The October AI-assisted audit found 13 supported claims and five unsupported inferences among 18 deliberately selected claims whose citations resolved. One model inferred all-zero bytes from zero entropy. The cited statistic supports constancy of values under the estimator. Both independent raters have completed 0 of 40 ratings. Analyst benefit remains unmeasured. [Claim audit](../backend/out/semantic_audit_2026-10-30/claims_v4_followup.csv) and [review instructions](HUMAN_REVIEW.md)

**What was held out?** The November HCRL explanation study used later time slices of the same sessions. Earlier detection work had scored those sessions in full. ROAD uses protocol-specific capture splits and shares recordings with earlier development work. Each dataset comes from one vehicle. Transfer to an unseen vehicle remains open. [Split definitions](../backend/app/datasets.py) and [provenance](FINAL_RESULTS_2026-11-22.md#provenance-and-limits)

**Why do timing and rate rules miss masquerade?** Fabrication often adds visible traffic. ROAD masquerade variants can preserve normal rates and timing while changing payload values. Detecting those cases calls for more informative evidence, such as signal relationships. Physical effect and sender identity need separate evidence. [ROAD paper](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0296879)

**Is hosted inference fast enough?** October v4 GLM median request times were 6.33 seconds for HCRL and 6.60 seconds for ROAD under the recorded settings. November medians vary by run. Measured token counts are available. Dollar costs remain unknown. Detection runs locally and does not wait on inference. [Latency and run settings](FINAL_RESULTS_2026-11-22.md)

**Have you tested other vehicles?** We downloaded and checked the archives for can-train-and-test v2 and the TU Eindhoven CAN intrusion dataset v2. Benchmarking on those datasets is pending. [Dataset receipt and parsing checks](ADDITIONAL_DATASETS.md)

## Separate final report deadline

The final report is due December 3, 2026, at 8:00 p.m. EST. Extend the midterm report in the supplied ACM LaTeX template. Keep the template unchanged. Write 6 to 8 double-column pages. Include an abstract, introduction, background, related work, methods, results and evaluation, conclusion with future work, and references. System design counts double and evaluation counts triple. Nicholas confirmed a course exception to the general no-AI rule for this work. Source: Lecture Note 01 on Canvas, slides 25 and 28.

## Primary references

- HCRL, Car-Hacking Dataset. [Dataset provider](https://ocslab.hksecurity.net/Datasets/car-hacking-dataset/)
- Verma et al., ROAD, 2024. [PLOS One](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0296879)
- Cho and Shin, CIDS, 2016. [USENIX Security](https://www.usenix.org/conference/usenixsecurity16/technical-sessions/presentation/cho)
- Marchetti and Stabili, READ, 2019. [University of Modena and Reggio Emilia](https://iris.unimore.it/handle/11380/1185929)
- Pesé et al., LibreCAN, 2019. [Authors' ACM CCS paper](https://mpese.com/publication/pese-2019-librecan/ACM_CCS_LibreCAN_Paper.pdf)
