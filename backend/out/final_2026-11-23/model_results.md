# Verified saved experiment results

Evidence snapshot for November 23, 2026 (US Eastern time). The offline verifier rescored saved replies.
[Machine-readable results and source hashes](model_results.json)

Attack-label accuracy uses frozen attack alerts. False-alarm columns count alerts called benign.
Failures and missing replies count as incorrect on the full target denominators below.
Paired comparisons use alerts with reply records in both runs, including recorded errors.
Citation validity checks whether IDs identify packet items. Human review assesses claim support.

## Additional datasets

### DTU can-train-and-test v2

Four vehicles and per-vehicle benign references. Attack captures come from the publisher's known-vehicle test splits. Only the saved subset is evaluated.

The manifest lists 4 reference and 38 scored captures.
The detector emitted 196 alerts (42 attack alerts and 154 false alarms).
The explanation targets include 42 attack alerts (14 DoS, 15 fuzzing, 13 spoofing) and 59 false alarms.
The sampling rule keeps all attack alerts and caps false alarms at three per capture with seed 0.
[Capture manifest](../alerts/ctt/manifest.json) · [Saved scores](../explanations/ctt/scores.md)

| Run | Attack labels | False alarms called benign | Reply rows | Failed | Missing |
| --- | ---: | ---: | ---: | ---: | ---: |
| `control-v1_alert` | 28/42 | 0/59 | 101 | 0 | 0 |
| `control-v2_alert` | 29/42 | 56/59 | 101 | 0 | 0 |
| `gemma-4-31b_v2-dosv1_alert` | 24/42 | 59/59 | 101 | 0 | 0 |
| `gemma-4-31b_v2_alert` | 23/42 | 59/59 | 101 | 0 | 0 |
| `glm-5.3_v2-dosv1_alert` | 31/42 | 56/59 | 101 | 1 | 0 |
| `glm-5.3_v2_alert` | 31/42 | 56/59 | 101 | 3 | 0 |
| `qwen3.6-27b-fp8_v2-dosv1_alert` | 32/42 | 59/59 | 101 | 0 | 0 |
| `qwen3.6-27b-fp8_v2_alert` | 34/42 | 59/59 | 101 | 0 | 0 |

### TU Eindhoven CAN v2

Two cars with per-vehicle training references. The attack files are offline edits of the benign testing log. Diagnostics are mapped to fuzzing. The prototype and deletion-only suspension file are outside the scored scope.

The manifest lists 2 reference and 12 scored captures.
The detector emitted 44 alerts (44 attack alerts and 0 false alarms).
The explanation targets include 44 attack alerts (2 DoS, 40 fuzzing, 2 replay) and 0 false alarms.
The sampling rule keeps all attack alerts and caps false alarms at three per capture with seed 0.
[Capture manifest](../alerts/tue/manifest.json) · [Saved scores](../explanations/tue/scores.md)

| Run | Attack labels | False alarms called benign | Reply rows | Failed | Missing |
| --- | ---: | ---: | ---: | ---: | ---: |
| `control-v1_alert` | 2/44 | n/a | 44 | 0 | 0 |
| `control-v2_alert` | 2/44 | n/a | 44 | 0 | 0 |
| `gemma-4-31b_v2-dosv1_alert` | 2/44 | n/a | 44 | 0 | 0 |
| `gemma-4-31b_v2_alert` | 2/44 | n/a | 44 | 0 | 0 |
| `glm-5.3_v2-dosv1_alert` | 2/44 | n/a | 43 | 0 | 1 |
| `glm-5.3_v2_alert` | 2/44 | n/a | 44 | 1 | 0 |
| `qwen3.6-27b-fp8_v2-dosv1_alert` | 2/44 | n/a | 44 | 1 | 0 |
| `qwen3.6-27b-fp8_v2_alert` | 2/44 | n/a | 44 | 1 | 0 |

Both datasets used a rule detector with a 0.50 s window, 0.25 s stride, and 0.55 threshold.
All hosted arms used alert packets, temperature 0, a 16,000-token limit, and no fallback.
The experiments measure alert labeling for selected captures with per-vehicle reference traffic.
The old citation checker marked two empty-claim replies as grounded, one each in CTT and midterm100.
The JSON identifies both replies. Their attack-label scores and claim-level citation counts are unaffected.

For TU Eindhoven, the detector raised zero alerts on both payload-fuzzing files and both benign testing logs.
The 40 fuzzing targets include 20 diagnostic alerts.
All correct attack labels are DoS, with zero correct fuzzing or replay labels in any arm.
GLM's DoS-line run lacks fuzzing alert `A0028`. Its saved score is 2/43 and its full target score is 2/44.

## Midterm100 DoS-line replication

The later run added 69 HCRL targets to the earlier ROAD-only DoS-line run.
The corpus has 69 HCRL attack alerts, 20 ROAD attack alerts, and 11 ROAD false alarms.
HCRL gains came from spoofing labels. Qwen lost one DoS and two fuzzing labels.
[Saved scores](../explanations/midterm100/scores.md)

| Model | HCRL attacks, v2 to DoS-line | ROAD attacks, v2 to DoS-line |
| --- | --- | --- |
| `gemma-4-31b` | 66/69 to 69/69 | 16/20 to 16/20 |
| `glm-5.3` | 61/69 to 68/69 | 16/20 to 16/20 |
| `qwen3.6-27b-fp8` | 36/69 to 65/69 | 14/20 to 15/20 |

GLM's DoS-line run lacks ROAD false alarm `A0093`. Its paired attack denominator is still 89.
On the 10 ROAD false alarms with replies in both runs, both prompts called six benign.
Across all 11 ROAD false alarms, the full target score is 7/11 for v2 and 6/11 for the DoS-line run.
The missing alert could raise the latter to 7/11 if answered correctly.

## Human review

Each reviewer labeled 40 claims. The reviewers agreed on 32/40 (80%), with Cohen's kappa 0.520958.
Human adjudication is pending for 8 claims.
The sample covers 27 alerts and four arms, with 10 cited claims per arm.
Each arm includes three DoS, three fuzzing, two spoofing, and two ROAD false-alarm claims.
The denominator below includes only claims on which both raters agreed.
[Saved review and disagreements](../claim_review/heldout/results.md)

| Arm | Supported | Unsupported | Contradicted | Agreed claims |
| --- | ---: | ---: | ---: | ---: |
| `control-v2_alert` | 6 | 2 | 0 | 8 |
| `gemma-4-31b_v2_alert` | 9 | 0 | 0 | 9 |
| `glm-5.3_v2_alert` | 4 | 3 | 0 | 7 |
| `qwen3.6-27b-fp8_v2_alert` | 7 | 1 | 0 | 8 |

## Historical evidence and reproduction

The prior report remains frozen in Git at `11dc0abc3ff2676aece7ff2d4b7a78a00ea1936c`.
The verifier checked 65 historical source hashes.
The later midterm100 replication updated three reply files, three run manifests, and the aggregate score file.
Two completed rating files replaced the blank copies. The JSON records the old and current hashes for all nine.
[Prior report](../final_2026-11-22/model_results.json) · [Saved window-level detector verification](../final_2026-11-22/detection/verification.md)

Run from `backend` with the project environment and a checkout containing the historical revision.
Choose new output paths to preserve prior reports. Add `--verify-raw` to check the 42 DTU and 14 TU Eindhoven capture hashes.

```sh
.venv/bin/python -m scripts.summarize_final_models \
  --out out/final_verify/model_results.json --markdown out/final_verify/model_results.md
```
