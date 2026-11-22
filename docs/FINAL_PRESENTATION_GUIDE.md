# CANalyst final presentation guide

**Rehearse to 14:30 for the 15-minute talk.** Keep 30 seconds for the handoff or demo. The course guide allows 20 minutes plus 3 minutes for questions. Presentation dates are November 24, December 1, and December 3, 2026. Check the assigned group slot. The rubric covers timing, structure, presentation quality, and content quality. [Course guide, slides 25 and 28](../../lectures/Lecture_Note01.pdf)

Presenters are Nicholas DiGennaro and Alexander Salazar, Clemson University. Open the [15-minute PowerPoint deck](../output/presentation/CANalyst_Final_Presentation_15min.pptx) in Presenter View to see the speaker notes.

## Rehearsal schedule

Nicholas presents slides 1 through 7. Alexander starts slide 8 at 6:45. Keep slides 16 through 28 available for questions.

| Slide | Elapsed time | Speaking cue |
|---|---:|---|
| 1. CANalyst | 0:25 | Can an analyst trace an explanation back to measured evidence? |
| 2. The analyst problem | 1:15 | Explain what an anomaly alert tells an analyst. Describe what still needs investigation. |
| 3. Datasets and attack labels | 2:15 | Define HCRL and ROAD ground truth. Explain that ROAD masquerade variants are postprocessed. |
| 4. System architecture | 3:15 | Trace the five stages. Point out where the explanation model enters. |
| 5. The evidence contract | 4:15 | Point to alert context, per-ID measurements, and sample frames. Explain why missing values stay unknown. |
| 6. Three evaluation questions | 5:15 | Use the correct denominator for detection, classification, and claim review. |
| 7. ROAD: fewer false alarms, limited recall | 6:45 | Give the false-positive rates and masquerade counts. Hand off to Alexander. |
| 8. October: GLM matches control on attack labels | 7:50 | Give matched GLM and rule results. Label this a development corpus. |
| 9. November: explain the coverage before the score | 8:35 | Explain why the 77-alert set cannot measure ROAD attack classification. |
| 10. One prompt line changes many labels | 9:30 | Explain the one-line change and where the gains appeared. |
| 11. Valid citations can accompany unsupported claims | 10:25 | Use one cited observation and one unsupported inference. State that independent ratings remain pending. |
| 12. Dashboard demonstration | 12:10 | Follow one alert to its evidence and open frozen benchmarks. |
| 13. Limits of the current evidence | 13:20 | Discuss detection coverage, shared recordings, and the human evaluation gap. |
| 14. What the project demonstrates | 14:10 | Explain how the workflow makes claims inspectable. Bound the classification and faithfulness findings. |
| 15. Questions | 14:30 | Pause and open Q&A. |

At 6:45, Nicholas hands off to Alexander. “The profile cuts false alarms, while most masquerade windows still go undetected. Alexander will show how we evaluated the alerts that reached the explanation stage.”

### Thirteen backup slides

16. Where CANalyst fits
17. Window features and detector profiles
18. Evaluation protocol and data reuse
19. HCRL: a simpler baseline remains competitive
20. Deployment and latency
21. Appendix: split and provenance ledger
22. Appendix: ROAD detector comparison
23. Appendix: HCRL detector comparison
24. Appendix: version names describe different layers
25. Appendix: failures and false-alarm denominators
26. Appendix: claim-review protocol
27. Appendix: saved benchmark screen
28. Appendix: sources and reproducibility

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
6. Open **Evaluation > Frozen benchmarks** and confirm the saved results load. Prepare the appendix screenshots before projecting the deck.

### Demo sequence, 1:45

| Time | Action |
|---|---|
| 0:00 to 0:20 | Show the ROAD timeline and one alert. Name the separate normal reference. |
| 0:20 to 1:00 | Open the alert. Identify the offline rule control. Click one citation and point to its measurement. |
| 1:00 to 1:30 | Open **Evaluation > Frozen benchmarks**. Show the 70 HCRL attack alerts and seven ROAD false alarms. |
| 1:30 to 1:45 | Return to the deck. Explain that an analyst can inspect the evidence behind each cited claim. Advance to slide 13. |

If ROAD data fails to load, use the [synthetic startup](http://127.0.0.1:5173/?dataset=synthetic) and identify it as synthetic. If the browser or server stalls, switch immediately to the screenshots on slides 12 and 27. Use the [saved ROAD dashboard image](images/dashboard-real-data.png) as a second local backup. Use only saved hosted-model replies during the presentation.

## Claims to use in Q&A

**Did the detector improve?** The merged ROAD rerun reproduces the saved November counts. With one reference, v2 lowers false positives from 1,461 to 50 of 9,598 normal windows. Precision rises from 38.4% to 94.8%. Both recall values round to 46.6%. Masquerade detections fall from four to three of 971 windows. [Merged detector verification](../backend/out/final_2026-11-22/detection/verification.md)

**Why keep v1 as the default?** The merged HCRL run gives v1 one false positive and 8,450 attack windows detected, out of 8,616. V2 gives zero false positives and detects 8,394 attack windows. The jitter guard accounts for the change from 32 saved November v1 false positives to one in the merged run. The whitelist plus interval baseline gives the best HCRL F1 in this comparison, 0.996. [Merged verification](../backend/out/final_2026-11-22/detection/verification.md) and [full benchmark](../backend/out/final_2026-11-22/detection/results.md)

**Does the LLM beat the rules?** In October v4, GLM and rule control-v5 got the same 86 of 89 attack alerts right. Each got 69/69 HCRL and 17/20 ROAD. Qwen3-30B-A3B scored 24/69 and 14/20. In November `heldout`, historical rule control-v2 got 70/70 HCRL attacks correct. Score comparisons apply to their respective frozen sets. [Final results](FINAL_RESULTS_2026-11-22.md)

**How well does it classify ROAD attacks?** The October development set contains 20 detected ROAD attack alerts. The November `heldout` set contains zero ROAD attack alerts and seven ROAD false alarms. ROAD attack windows do appear in the separate November detection benchmark. [November alert manifest](../backend/out/alerts/heldout/manifest.json)

**What did changing the prompt do?** On 70 HCRL attack alerts, restoring the earlier DoS line moved Qwen3.6-27B from 37 to 69 correct and GLM from 59 to 70. All hosted variants classified the 17 DoS alerts correctly. The gains appeared in spoofing labels. GLM had five failed replies in the original run and one in the ablation, across the 77 targets. [November ablation scores](../backend/out/explanations/heldout/scores.md)

**Do the citations prove the explanation is faithful?** They link the explanation to evidence. The October AI-assisted audit found 13 supported claims and five unsupported inferences among 18 deliberately selected claims whose citations resolved. One model inferred all-zero bytes from zero entropy. The cited statistic supports constancy of values under the estimator. Both independent raters have completed 0 of 40 ratings. Analyst benefit remains unmeasured. [Claim audit](../backend/out/semantic_audit_2026-10-30/claims_v4_followup.csv) and [review materials](../backend/out/claim_review/heldout/)

**What was held out?** The November HCRL explanation study used later time slices of the same sessions. Earlier detection work had scored those sessions in full. ROAD uses protocol-specific capture splits and shares recordings with earlier development work. Each dataset comes from one vehicle. Transfer to an unseen vehicle remains open. [Split definitions](../backend/app/datasets.py) and [provenance](FINAL_RESULTS_2026-11-22.md#provenance-and-limits)

**Why do timing and rate rules miss masquerade?** Fabrication often adds visible traffic. ROAD masquerade variants can preserve normal rates and timing while changing payload values. Detecting those cases calls for more informative evidence, such as signal relationships. Physical effect and sender identity need separate evidence. [ROAD paper](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0296879)

**Is hosted inference fast enough?** October v4 GLM median request times were 6.33 seconds for HCRL and 6.60 seconds for ROAD under the recorded settings. November medians vary by run. Measured token counts are available. Dollar costs remain unknown. Detection runs locally and does not wait on inference. [Latency and run settings](FINAL_RESULTS_2026-11-22.md)

## Separate final report deadline

The final report is due December 3, 2026, at 8:00 p.m. EST. Use the provided ACM LaTeX template without modifications. Write 6 to 8 double-column pages with an abstract, introduction, background, related work, methods, evaluation, conclusion, and references. [Course guide, slide 25](../../lectures/Lecture_Note01.pdf)

## Primary references

- HCRL, Car-Hacking Dataset. [Dataset provider](https://ocslab.hksecurity.net/Datasets/car-hacking-dataset/)
- Verma et al., ROAD, 2024. [PLOS One](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0296879)
- Cho and Shin, CIDS, 2016. [USENIX Security](https://www.usenix.org/conference/usenixsecurity16/technical-sessions/presentation/cho)
- Marchetti and Stabili, READ, 2019. [University of Modena and Reggio Emilia](https://iris.unimore.it/handle/11380/1185929)
- Pesé et al., LibreCAN, 2019. [Authors' ACM CCS paper](https://mpese.com/publication/pese-2019-librecan/ACM_CCS_LibreCAN_Paper.pdf)
