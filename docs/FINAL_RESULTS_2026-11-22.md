# CANalyst final results, November 22, 2026

The November detector benchmark shows a large reduction in ROAD false positives with rule profile v2. ROAD masquerade recall remains low. On selected detected alerts, prompt wording changed some model classifications. The project has no independent human ratings of explanation quality.

## Detector results

Detector metrics count overlapping 0.5-second windows at a 0.25-second stride. ROAD ground truth uses labeled injection intervals and IDs. Detected windows can merge into one alert.

The October full HCRL rerun scored 42,975 windows. Corrected rules reduced false positives from 65 to 28 and kept 21,986 true positives and 438 misses. Precision was 99.87%, recall was 98.05%, and F1 was 98.95%. [October paired rerun](../backend/out/detectors_full_hcrl_2026-10-30/hcrl_full_midterm/results.json)

The merged rerun used the November split and a fixed threshold of 0.55. The table shows results with one reference capture per dataset.

| Dataset and profile | Precision | Attack windows detected | Recall | F1 | False positives | False-positive rate |
|---|---:|---:|---:|---:|---:|---:|
| ROAD v1 | 38.4% | 911/1,954 | 46.62% | 42.12% | 1,461/9,598 | 15.22% |
| ROAD v2 | 94.8% | 910/1,954 | 46.57% | 62.46% | 50/9,598 | 0.52% |
| HCRL v1 | 99.99% | 8,450/8,616 | 98.07% | 99.02% | 1/13,458 | 0.007% |
| HCRL v2 | 100.00% | 8,394/8,616 | 97.42% | 98.69% | 0/13,458 | 0.00% |

ROAD masquerade recall fell from 4/971 to 3/971. With a reference pooled from seven captures, both profiles detected 954/1,954 attack windows. ROAD false positives fell from 453 to 50 across 9,598 normal windows. Both reference setups reproduce the saved November counts. [Fresh detector results](../backend/out/final_2026-11-22/detection/results.md)

The merged HCRL v1 run produced one false positive. The saved November run produced 32. An isolated replay traced the change to the jitter guard. Baseline jitter floors at or below 10 microseconds no longer signal timing collapse. The benchmark skipped one truncated final line in the HCRL normal capture and preserved the original input. Profile v2 detected 56 fewer gear spoofing windows than v1. [Saved November detection results](../backend/out/benchmark/results.md) · [Merged detector verification](../backend/out/final_2026-11-22/detection/verification.md)

Keep profile v1 as the shared demo default. Present profile v2 as a candidate for reducing false alarms on ROAD. A default change needs independent validation and an explicit decision about acceptable misses.

## October v4 explanation benchmark

Each arm received identical frozen evidence for 100 development alerts. The benchmark scores attack labels on detected alerts only. Both hosted models used `can-evidence-v3`, temperature zero, a 1,800-token cap, and a 90-second timeout. GLM used low reasoning effort. Both ran two workers per dataset.

| Arm | HCRL attacks | ROAD attacks | ROAD false alarms called benign | Failures / attempts | Median seconds HCRL / ROAD | P95 seconds HCRL / ROAD |
|---|---:|---:|---:|---:|---:|---:|
| Rule control-v5 | 69/69 | 17/20 | 0/11 | 0/100 | 0.000019 / 0.000020 | 0.000029 / 0.000048 |
| GLM-5.3 | 69/69 | 17/20 | 1/11 | 0/100 | 6.331 / 6.599 | 8.916 / 9.250 |
| Qwen3-30B-A3B-Instruct-FP8 | 24/69 | 14/20 | 0/11 | 0/100 | 4.272 / 4.192 | 5.414 / 5.314 |

The control and GLM got the same 86 of 89 attack alerts right. Qwen got 38 of 89 right, and the control got all 38 of those right. Gemma-4-12b and GPTOSS-120B each have one ROAD smoke reply. Hosted costs are unknown. [GLM comparisons](../backend/out/comparisons_v4_2026-10-30_control_v5/) · [Qwen HCRL comparison](../backend/out/final_2026-11-22/qwen_v4_hcrl.json) · [Qwen ROAD comparison](../backend/out/final_2026-11-22/qwen_v4_road.json)

## November frozen explanation benchmarks

The saved `heldout` set contains **70 HCRL attack alerts and seven ROAD false alarms**. HCRL includes 17 DoS, 15 fuzzing, and 38 spoofing alerts. This set contains zero ROAD attack alerts. [Held-out corpus manifest](../backend/out/alerts/heldout/manifest.json)

The prompt ablation replaces only the DoS description in v2 with the earlier wording. Each hosted arm uses whole-alert evidence, temperature zero, a 16,000-token cap, and strict replies. Recorded errors count as wrong. Median latency covers successful replies and includes service conditions. Each arm has one run.

| Arm | HCRL attacks v2 → ablation | HCRL spoofing v2 → ablation | ROAD false alarms called benign | Errors v2 → ablation | Median seconds v2 → ablation |
|---|---:|---:|---:|---:|---:|
| Gemma-4-31B | 69/70 → 70/70 | 37/38 → 38/38 | 5/7 → 5/7 | 0/77 → 0/77 | 16.0 → 19.3 |
| GLM-5.3 | 59/70 → 70/70 | 27/38 → 38/38 | 4/7 → 4/7 | 5/77 → 1/77 | 36.3 → 90.2 |
| Qwen3.6-27B-FP8 | 37/70 → 69/70 | 5/38 → 38/38 | 5/7 → 5/7 | 0/77 → 0/77 | 55.4 → 64.5 |

All six hosted arms got the 17 DoS labels correct. The HCRL gains came from spoofing predictions. The newer rule control scored 70/70 attacks and labeled 4/7 false alarms benign. The older rule control scored 53/70 and 0/7. Both returned 77/77 replies. [November heldout scores](../backend/out/explanations/heldout/scores.md)

The November `midterm100` rebuild includes the same alert targets used in October v4. The baseline v2 hosted arms scored:

| Arm | HCRL attacks | ROAD attacks | ROAD false alarms called benign | Errors / targets | Median seconds |
|---|---:|---:|---:|---:|---:|
| Rule control-v1 | 53/69 | 17/20 | 0/11 | 0/100 | 0.0 |
| Rule control-v2 | 69/69 | 16/20 | 5/11 | 0/100 | 0.0 |
| Gemma-4-31B | 66/69 | 16/20 | 7/11 | 0/100 | 15.4 |
| GLM-5.3 | 61/69 | 16/20 | 7/11 | 5/100 | 38.6 |
| Qwen3.6-27B-FP8 | 36/69 | 14/20 | 10/11 | 0/100 | 55.3 |

Only the ROAD targets were scheduled for the November `midterm100` ablation. Every recorded ROAD reply succeeded. Each matched pair covered all 20 ROAD attack alerts. [November midterm100 scores](../backend/out/explanations/midterm100/scores.md)

| Arm | ROAD attacks v2 → ablation | Benign calls on shared false alarms | Error or missing v2 → ablation / ROAD targets | Median seconds on shared alerts v2 → ablation |
|---|---:|---:|---:|---:|
| Gemma-4-31B | 16/20 → 16/20 | 7/11 → 7/11 | 0/31 → 0/31 | 14.4 → 20.2 |
| GLM-5.3 | 16/20 → 16/20 | 6/10 → 6/10 | 0/31 → 1/31 | 44.1 → 39.3 |
| Qwen3.6-27B-FP8 | 14/20 → 15/20 | 10/11 → 8/11 | 0/31 → 0/31 | 54.7 → 67.9 |

GLM's missing ablation reply is `A0093`, a false alarm in `ambient_dyno_drive_extended_short` from 0 to 23 seconds. V2 called it benign. The full-set ablation benign count ranges from 6/11 to 7/11. V2 scored 7/11. The case has no bearing on the attack-label comparison. [Incomplete run manifest](../backend/out/explanations/midterm100/glm-5.3_v2-dosv1_alert/run.json)

## Provenance and limits

- October v4 and November `midterm100` share all 100 capture, alert ID, interval and label tuples. Their evidence and prompt protocols differ. Keep model scores within each protocol. [October frozen corpora](../backend/out/frozen_2026-10-30_v4/) · [November midterm manifest](../backend/out/alerts/midterm100/manifest.json)
- The November HCRL explainer set takes later slices from the same four attack sessions. Those slices are separate from October's first 120-second explainer slices. October detection scored all four full attack sessions. The normal reference remains the first 120 seconds of the same normal recording. [October method](../backend/out/midterm_2026-10-20/methodology.txt) · [November held-out manifest](../backend/out/alerts/heldout/manifest.json)
- November ROAD detection assigns all 20 evaluation attack captures to different roles from its tuning captures. October detection had already scored all 20 in full. October broader profiles scored prefixes of four of the five November evaluation ambient captures. The fifth, `ambient_dyno_idle_radio_infotainment`, contributed baseline measurements. The November explainer uses a later slice of `ambient_dyno_drive_extended_short` than the October explainer. The November partitions measure performance within their protocol on previously used recordings. [Split code](../backend/app/datasets.py) · [October broad ROAD run](../backend/out/detectors_2026-10-30/road_broad/results.json)
- October v4 packets passed 7,056 numeric and schema checks. Every GLM and Qwen reply passed the citation check. Identifier validation flagged two absent explicit IDs in GLM replies and zero in Qwen replies. Three ambiguous hexadecimal references in Qwen replies still need context. A separate AI-assisted audit reviewed 18 selected v4 claims with valid citation IDs. It found 13 supported claims and five unsupported inferences. [Packet checks](../backend/out/semantic_audit_2026-10-30/numeric_validation_v4.json) · [Identifier checks](../backend/out/validation_2026-10-30_v4/) · [Semantic audit](../backend/out/semantic_audit_2026-10-30/claims_v4_followup.json)
- Both blinded human rating sheets have 0/40 labels. Human support rates, inter-rater agreement, and analyst benefit remain unmeasured. These datasets also leave new-vehicle transfer unmeasured. [Human review rubric and sheets](../backend/out/claim_review/heldout/)

The machine-readable summary records exact corpus hashes, source file hashes, per-run settings and recalculated scores. The verifier recomputes the comparisons offline from saved replies. This review made zero new hosted model calls. [Model results and provenance](../backend/out/final_2026-11-22/model_results.json) · [Verification script](../backend/scripts/summarize_final_models.py)
