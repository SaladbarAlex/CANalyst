# Explainer scores: heldout

Label accuracy on attack alerts, with Wilson 95% intervals.

| run | hcrl | road | all | false alarms called benign | claims with valid citations | median latency |
|---|---|---|---|---|---|---|
| control-v1_alert | 76% (53/70; 65 to 84) | n/a | 76% (53/70; 65 to 84) | 0% (0/7; 0 to 35) | 100% (132/132; 97 to 100) | 0.0s |
| control-v2_alert | 100% (70/70; 95 to 100) | n/a | 100% (70/70; 95 to 100) | 57% (4/7; 25 to 84) | 100% (153/153; 98 to 100) | 0.0s |
| gemma-4-31b_v2_alert | 99% (69/70; 92 to 100) | n/a | 99% (69/70; 92 to 100) | 71% (5/7; 36 to 92) | 100% (424/425; 99 to 100) | 16.0s |
| glm-5.3_v2_alert | 84% (59/70; 74 to 91) | n/a | 84% (59/70; 74 to 91) | 57% (4/7; 25 to 84) | 100% (692/692; 99 to 100) | 36.3s |
| qwen3.6-27b-fp8_v2_alert | 53% (37/70; 41 to 64) | n/a | 53% (37/70; 41 to 64) | 71% (5/7; 36 to 92) | 99% (480/486; 97 to 99) | 55.4s |

## By true attack type

| run | hcrl/dos | hcrl/fuzzing | hcrl/spoofing |
|---|---|---|---|
| control-v1_alert | 0% (0/17; 0 to 18) | 100% (15/15; 80 to 100) | 100% (38/38; 91 to 100) |
| control-v2_alert | 100% (17/17; 82 to 100) | 100% (15/15; 80 to 100) | 100% (38/38; 91 to 100) |
| gemma-4-31b_v2_alert | 100% (17/17; 82 to 100) | 100% (15/15; 80 to 100) | 97% (37/38; 87 to 100) |
| glm-5.3_v2_alert | 100% (17/17; 82 to 100) | 100% (15/15; 80 to 100) | 71% (27/38; 55 to 83) |
| qwen3.6-27b-fp8_v2_alert | 100% (17/17; 82 to 100) | 100% (15/15; 80 to 100) | 13% (5/38; 6 to 27) |

## Paired comparisons (exact McNemar)

| pair | group | n | first correct | second correct | only first | only second | p |
|---|---|---|---|---|---|---|---|
| control-v1_alert vs control-v2_alert | all | 70 | 53 | 70 | 0 | 17 | 0.0000 |
| control-v1_alert vs control-v2_alert | hcrl | 70 | 53 | 70 | 0 | 17 | 0.0000 |
| control-v1_alert vs gemma-4-31b_v2_alert | all | 70 | 53 | 69 | 1 | 17 | 0.0001 |
| control-v1_alert vs gemma-4-31b_v2_alert | hcrl | 70 | 53 | 69 | 1 | 17 | 0.0001 |
| control-v1_alert vs glm-5.3_v2_alert | all | 70 | 53 | 59 | 11 | 17 | 0.3449 |
| control-v1_alert vs glm-5.3_v2_alert | hcrl | 70 | 53 | 59 | 11 | 17 | 0.3449 |
| control-v1_alert vs qwen3.6-27b-fp8_v2_alert | all | 70 | 53 | 37 | 33 | 17 | 0.0328 |
| control-v1_alert vs qwen3.6-27b-fp8_v2_alert | hcrl | 70 | 53 | 37 | 33 | 17 | 0.0328 |
| control-v2_alert vs gemma-4-31b_v2_alert | all | 70 | 70 | 69 | 1 | 0 | 1.0000 |
| control-v2_alert vs gemma-4-31b_v2_alert | hcrl | 70 | 70 | 69 | 1 | 0 | 1.0000 |
| control-v2_alert vs glm-5.3_v2_alert | all | 70 | 70 | 59 | 11 | 0 | 0.0010 |
| control-v2_alert vs glm-5.3_v2_alert | hcrl | 70 | 70 | 59 | 11 | 0 | 0.0010 |
| control-v2_alert vs qwen3.6-27b-fp8_v2_alert | all | 70 | 70 | 37 | 33 | 0 | 0.0000 |
| control-v2_alert vs qwen3.6-27b-fp8_v2_alert | hcrl | 70 | 70 | 37 | 33 | 0 | 0.0000 |
| gemma-4-31b_v2_alert vs glm-5.3_v2_alert | all | 70 | 69 | 59 | 10 | 0 | 0.0020 |
| gemma-4-31b_v2_alert vs glm-5.3_v2_alert | hcrl | 70 | 69 | 59 | 10 | 0 | 0.0020 |
| gemma-4-31b_v2_alert vs qwen3.6-27b-fp8_v2_alert | all | 70 | 69 | 37 | 32 | 0 | 0.0000 |
| gemma-4-31b_v2_alert vs qwen3.6-27b-fp8_v2_alert | hcrl | 70 | 69 | 37 | 32 | 0 | 0.0000 |
| glm-5.3_v2_alert vs qwen3.6-27b-fp8_v2_alert | all | 70 | 59 | 37 | 22 | 0 | 0.0000 |
| glm-5.3_v2_alert vs qwen3.6-27b-fp8_v2_alert | hcrl | 70 | 59 | 37 | 22 | 0 | 0.0000 |
