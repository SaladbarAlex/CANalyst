# CANalyst final results, November 23, 2026

Detector profile v2 reduced ROAD false positives from 1,461 to 50 out of 9,598 normal windows. On frozen alerts, corrected GLM matched the rule control on 86 of 89 attack labels. On TU Eindhoven, every explanation arm scored 2 of 44. Two human raters agreed on 32 of 40 claims. Eight disagreements await adjudication. [Verified scores and source hashes](../backend/out/final_2026-11-23/model_results.json)

## Detector windows

The benchmark used 0.50-second windows, a 0.25-second stride, and a fixed threshold of 0.55. These counts include normal windows both inside and outside attack captures. [Saved window results](../backend/out/final_2026-11-22/detection/results.md)

| Dataset and reference | Rule profile | Attack windows detected | False positives | Precision | Recall |
| --- | --- | ---: | ---: | ---: | ---: |
| ROAD, single | v1 | 911/1,954 | 1,461/9,598 | 38.41% | 46.62% |
| ROAD, single | v2 | 910/1,954 | 50/9,598 | 94.79% | 46.57% |
| ROAD, pooled | v1 | 954/1,954 | 453/9,598 | 67.80% | 48.82% |
| ROAD, pooled | v2 | 954/1,954 | 50/9,598 | 95.02% | 48.82% |
| HCRL, single | v1 | 8,450/8,616 | 1/13,458 | 99.99% | 98.07% |
| HCRL, single | v2 | 8,394/8,616 | 0/13,458 | 100% | 97.42% |

ROAD single-reference masquerade recall was 4/971 for v1 and 3/971 for v2. In HCRL, profile v2 missed 56 more gear spoofing windows. The live default remains v1. Prior development used all four HCRL attack recordings and all 25 later ROAD evaluation sources. [Detector checks and overlap audit](../backend/out/final_2026-11-22/detection/verification.md)

## Corrected October explanations

All arms received the same evidence-v4 packets for 69 HCRL attacks, 20 ROAD attacks, and 11 ROAD false alarms. Hosted runs used prompt `can-evidence-v3`, temperature 0, and a 1,800-token limit. Both models returned 100 replies without fallback. [Settings and scores](../backend/out/final_2026-11-23/model_results.json)

| Arm | HCRL attack labels | ROAD attack labels | ROAD false alarms called benign |
| --- | ---: | ---: | ---: |
| Rule control-v5 | 69/69 | 17/20 | 0/11 |
| GLM-5.3 | 69/69 | 17/20 | 1/11 |
| Qwen3-30B-A3B-Instruct-FP8 | 24/69 | 14/20 | 0/11 |

The control and GLM missed the same three ROAD masquerade labels. Evidence, rules, and inference settings all changed after the midterm. The rerun cannot isolate any single correction. October v4 and November `midterm100` share all 100 target tuples. [Original midterm](midterm/paper/midterm.pdf) · [October evidence packets](../backend/out/frozen_2026-10-30_v4/) · [November manifest](../backend/out/alerts/midterm100/manifest.json)

## November prompt comparisons

The comparison changes one DoS instruction in prompt `v2`. Hosted runs use alert packets, temperature 0, a 16,000-token limit, and no fallback. The table uses full target denominators. Recorded failures and missing replies count as incorrect. [Verified run settings and scores](../backend/out/final_2026-11-23/model_results.json)

| Arm | `heldout` HCRL attacks | `midterm100` HCRL attacks | `midterm100` ROAD attacks | `midterm100` ROAD false alarms called benign |
| --- | ---: | ---: | ---: | ---: |
| Rule control-v1 | 53/70 | 53/69 | 17/20 | 0/11 |
| Rule control-v2 | 70/70 | 69/69 | 16/20 | 5/11 |
| Gemma 4-31B, v2 to DoS-line | 69/70 to 70/70 | 66/69 to 69/69 | 16/20 to 16/20 | 7/11 to 7/11 |
| GLM-5.3, v2 to DoS-line | 59/70 to 70/70 | 61/69 to 68/69 | 16/20 to 16/20 | 7/11 to 6/11 |
| Qwen3.6-27B-FP8, v2 to DoS-line | 37/70 to 69/70 | 36/69 to 65/69 | 14/20 to 15/20 | 10/11 to 8/11 |

- `heldout` contains 70 HCRL attack alerts and seven ROAD false alarms. It contains zero ROAD attack alerts and reuses earlier recordings. Every hosted arm scored 17/17 on DoS. Qwen gained 33 spoofing labels and lost one fuzzing label. GLM recorded five failures with v2 and one with the DoS-line prompt. Across both prompts, Gemma and Qwen each called 5/7 ROAD false alarms benign. GLM called 4/7 benign, as did control-v2. Control-v1 called 0/7 benign. [Heldout scores](../backend/out/explanations/heldout/scores.md)
- `midterm100` contains 89 attack alerts and 11 false alarms. The replication added 69 HCRL targets to the first ROAD-only DoS-line run. Qwen gained 32 HCRL spoofing labels and lost one DoS and two fuzzing labels. GLM's DoS-line run lacks one ROAD false alarm, `A0093`. Both GLM prompts called six of the ten paired false alarms benign. All 89 attack targets have reply records. [Midterm100 scores](../backend/out/explanations/midterm100/scores.md)

## Additional vehicles

Four DTU vehicles and two TU Eindhoven cars each use per-vehicle reference traffic. These scores cover selected detector alerts. They cannot estimate window-level detection or transfer without per-vehicle reference data. [Dataset scope](ADDITIONAL_DATASETS.md)

| Arm | DTU attack labels | DTU false alarms called benign | TU Eindhoven attack labels |
| --- | ---: | ---: | ---: |
| Rule control-v1 | 28/42 | 0/59 | 2/44 |
| Rule control-v2 | 29/42 | 56/59 | 2/44 |
| Gemma 4-31B, v2 to DoS-line | 23/42 to 24/42 | 59/59 to 59/59 | 2/44 to 2/44 |
| GLM-5.3, v2 to DoS-line | 31/42 to 31/42 | 56/59 to 56/59 | 2/44 to 2/44 |
| Qwen3.6-27B-FP8, v2 to DoS-line | 34/42 to 32/42 | 59/59 to 59/59 | 2/44 to 2/44 |

- **DTU**. The rule detector raised 196 alerts across 38 scored captures, using four clean reference captures. All 42 attack alerts entered the evaluation. These comprise 14 DoS, 15 fuzzing, and 13 spoofing alerts. The cap retained 59 of 154 false alarms with at most three per capture and seed 0. Only GLM recorded failures, with three on v2 and one on the DoS-line run. All 101 targets have reply records in every arm. [DTU targets](../backend/out/alerts/ctt/manifest.json) · [DTU saved scores](../backend/out/explanations/ctt/scores.md)
- **TU Eindhoven**. Twelve scored captures and two references produced 44 targets. Diagnostics account for 20 of 40 fuzzing alerts. Both DoS labels were correct in each arm. Every arm missed both replay labels and all fuzzing labels on the full target basis. The GLM DoS-line run has 43 replies and lacks one fuzzing alert, `A0028`. GLM v2 and both Qwen runs each recorded one error. The detector raised zero alerts on both payload-fuzzing files and both benign testing files. The car attack files are offline edits of each car's benign testing log. [TU Eindhoven targets](../backend/out/alerts/tue/manifest.json) · [TU Eindhoven saved scores](../backend/out/explanations/tue/scores.md)

The raw hashes match all 42 DTU and 14 TU Eindhoven capture inputs. The five TU Eindhoven code hashes match Git revision `c88579c`. A fresh freeze reproduced all 44 TU Eindhoven targets and both packet scopes when compared as parsed JSON. [Frozen TU Eindhoven manifest](../backend/out/alerts/tue/manifest.json)

Four DTU application hashes match `c489a66`. The archived DTU `freeze_alerts.py` hash has no matching reachable committed version. A fresh freeze reproduced the IDs, intervals, labels, and sampling of all 196 full and 101 capped alerts. Rounding fresh scores to four decimals reproduced the saved scores. Of the 101 capped packets per scope, 90 alert packets and 75 window packets matched as parsed JSON. The remaining packets differ in detector scores or evidence details. The saved packets and replies remain the basis for the reported model results. [Frozen DTU manifest](../backend/out/alerts/ctt/manifest.json) · [Fresh adapter verification](../backend/out/final_2026-11-23/adapter_verification.md)

## Human claim review

Each rater labeled 40 blinded claims from 27 alerts. The raters agreed on 32/40 (80%). Cohen's kappa was 0.520958. Among the 32 agreements, 26 claims were supported and six unsupported. No claim received two contradicted ratings. Eight disagreements remain unresolved. [Paired ratings and disagreements](../backend/out/claim_review/heldout/results.md) · [Adjudication sheet](../backend/out/claim_review/heldout/adjudication.csv)

| Arm | Supported | Unsupported | Agreed / sampled |
| --- | ---: | ---: | ---: |
| Rule control-v2 | 6 | 2 | 8/10 |
| Gemma 4-31B v2 | 9 | 0 | 9/10 |
| GLM-5.3 v2 | 4 | 3 | 7/10 |
| Qwen3.6-27B-FP8 v2 | 7 | 1 | 8/10 |

Each arm contributes three DoS, three fuzzing, two spoofing, and two ROAD false-alarm claims. The sample excludes ROAD attack alerts, uncited claims, summaries, additional datasets, and the DoS-line runs. The table uses agreed claims only. Full-sample support rates and analyst task time or accuracy remain unmeasured. Citation validity checks whether IDs resolve to packet items. An earlier AI-assisted audit found five unsupported claims among 18 selected claims despite resolving citations. [Review protocol](HUMAN_REVIEW.md) · [Earlier semantic audit](../backend/out/semantic_audit_2026-10-30/claims_v4_followup.json)

## Reproduce the checks

Run from the repository root. Use a checkout that includes the November 22 history. Add `--verify-raw` to verify installed DTU and TU Eindhoven capture hashes. [Compact verifier output](../backend/out/final_2026-11-23/model_results.md) · [Verification code](../backend/scripts/summarize_final_models.py)

```sh
cd backend
result_dir=$(mktemp -d /tmp/canalyst-final-verify.XXXXXX)
.venv/bin/python -m scripts.summarize_final_models \
  --out "$result_dir/model_results.json" \
  --markdown "$result_dir/model_results.md"
cmp "$result_dir/model_results.json" out/final_2026-11-23/model_results.json
cmp "$result_dir/model_results.md" out/final_2026-11-23/model_results.md
.venv/bin/python -m pytest tests/test_final_summary.py -q
```

The offline verifier checks 65 source hashes from the November 22 report. Git revision `11dc0ab` preserves the earlier values of nine paths. The later replication updated three reply files, three run manifests, and one score file. The two completed rater sheets replaced their blank copies. The original completed exports remain in `backend/out/claim_review/heldout/originals/`. [Historical summary](../backend/out/final_2026-11-22/model_results.json) · [Original rating exports](../backend/out/claim_review/heldout/originals/)

To rerun the window benchmark, install the HCRL and ROAD captures first. Run these commands from `backend`. [Detector setup and reproduction details](../backend/out/final_2026-11-22/detection/verification.md#reproduction)

```sh
detection_dir=$(mktemp -d /tmp/canalyst-detection-verify.XXXXXX)
.venv/bin/python -m scripts.build_cache --dataset all --force --workers 1
.venv/bin/python -m scripts.benchmark --dataset all --out "$detection_dir"
```
