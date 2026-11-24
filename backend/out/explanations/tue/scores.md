# Explainer scores: tue

Label accuracy on attack alerts, with Wilson 95% intervals. A failed or empty reply counts as wrong.

| run | tue | all | no answer | false alarms called benign | claims with valid citations | median latency |
|---|---|---|---|---|---|---|
| control-v1_alert | 5% (2/44; 1 to 15) | 5% (2/44; 1 to 15) | 0 | n/a | 100% (48/48; 93 to 100) | 0.0s |
| control-v2_alert | 5% (2/44; 1 to 15) | 5% (2/44; 1 to 15) | 0 | n/a | 100% (48/48; 93 to 100) | 0.0s |
| gemma-4-31b_v2-dosv1_alert | 5% (2/44; 1 to 15) | 5% (2/44; 1 to 15) | 0 | n/a | 100% (222/223; 98 to 100) | 23.5s |
| gemma-4-31b_v2_alert | 5% (2/44; 1 to 15) | 5% (2/44; 1 to 15) | 0 | n/a | 100% (232/232; 98 to 100) | 24.6s |
| glm-5.3_v2-dosv1_alert | 5% (2/43; 1 to 15) | 5% (2/43; 1 to 15) | 0 | n/a | 100% (399/399; 99 to 100) | 110.7s |
| glm-5.3_v2_alert | 5% (2/44; 1 to 15) | 5% (2/44; 1 to 15) | 1 | n/a | 100% (399/399; 99 to 100) | 87.4s |
| qwen3.6-27b-fp8_v2-dosv1_alert | 5% (2/44; 1 to 15) | 5% (2/44; 1 to 15) | 1 | n/a | 99% (254/256; 97 to 100) | 70.8s |
| qwen3.6-27b-fp8_v2_alert | 5% (2/44; 1 to 15) | 5% (2/44; 1 to 15) | 1 | n/a | 99% (235/237; 97 to 100) | 73.0s |

## By true attack type

| run | tue/dos | tue/fuzzing | tue/replay |
|---|---|---|---|
| control-v1_alert | 100% (2/2; 34 to 100) | 0% (0/40; 0 to 9) | 0% (0/2; 0 to 66) |
| control-v2_alert | 100% (2/2; 34 to 100) | 0% (0/40; 0 to 9) | 0% (0/2; 0 to 66) |
| gemma-4-31b_v2-dosv1_alert | 100% (2/2; 34 to 100) | 0% (0/40; 0 to 9) | 0% (0/2; 0 to 66) |
| gemma-4-31b_v2_alert | 100% (2/2; 34 to 100) | 0% (0/40; 0 to 9) | 0% (0/2; 0 to 66) |
| glm-5.3_v2-dosv1_alert | 100% (2/2; 34 to 100) | 0% (0/39; 0 to 9) | 0% (0/2; 0 to 66) |
| glm-5.3_v2_alert | 100% (2/2; 34 to 100) | 0% (0/40; 0 to 9) | 0% (0/2; 0 to 66) |
| qwen3.6-27b-fp8_v2-dosv1_alert | 100% (2/2; 34 to 100) | 0% (0/40; 0 to 9) | 0% (0/2; 0 to 66) |
| qwen3.6-27b-fp8_v2_alert | 100% (2/2; 34 to 100) | 0% (0/40; 0 to 9) | 0% (0/2; 0 to 66) |

## Paired comparisons (exact McNemar)

| pair | group | n | first correct | second correct | only first | only second | p |
|---|---|---|---|---|---|---|---|
| control-v1_alert vs control-v2_alert | all | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| control-v1_alert vs control-v2_alert | tue | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| control-v1_alert vs gemma-4-31b_v2-dosv1_alert | all | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| control-v1_alert vs gemma-4-31b_v2-dosv1_alert | tue | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| control-v1_alert vs gemma-4-31b_v2_alert | all | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| control-v1_alert vs gemma-4-31b_v2_alert | tue | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| control-v1_alert vs glm-5.3_v2-dosv1_alert | all | 43 | 2 | 2 | 0 | 0 | 1.0000 |
| control-v1_alert vs glm-5.3_v2-dosv1_alert | tue | 43 | 2 | 2 | 0 | 0 | 1.0000 |
| control-v1_alert vs glm-5.3_v2_alert | all | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| control-v1_alert vs glm-5.3_v2_alert | tue | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| control-v1_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | all | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| control-v1_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | tue | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| control-v1_alert vs qwen3.6-27b-fp8_v2_alert | all | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| control-v1_alert vs qwen3.6-27b-fp8_v2_alert | tue | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| control-v2_alert vs gemma-4-31b_v2-dosv1_alert | all | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| control-v2_alert vs gemma-4-31b_v2-dosv1_alert | tue | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| control-v2_alert vs gemma-4-31b_v2_alert | all | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| control-v2_alert vs gemma-4-31b_v2_alert | tue | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| control-v2_alert vs glm-5.3_v2-dosv1_alert | all | 43 | 2 | 2 | 0 | 0 | 1.0000 |
| control-v2_alert vs glm-5.3_v2-dosv1_alert | tue | 43 | 2 | 2 | 0 | 0 | 1.0000 |
| control-v2_alert vs glm-5.3_v2_alert | all | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| control-v2_alert vs glm-5.3_v2_alert | tue | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| control-v2_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | all | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| control-v2_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | tue | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| control-v2_alert vs qwen3.6-27b-fp8_v2_alert | all | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| control-v2_alert vs qwen3.6-27b-fp8_v2_alert | tue | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| gemma-4-31b_v2-dosv1_alert vs gemma-4-31b_v2_alert | all | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| gemma-4-31b_v2-dosv1_alert vs gemma-4-31b_v2_alert | tue | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| gemma-4-31b_v2-dosv1_alert vs glm-5.3_v2-dosv1_alert | all | 43 | 2 | 2 | 0 | 0 | 1.0000 |
| gemma-4-31b_v2-dosv1_alert vs glm-5.3_v2-dosv1_alert | tue | 43 | 2 | 2 | 0 | 0 | 1.0000 |
| gemma-4-31b_v2-dosv1_alert vs glm-5.3_v2_alert | all | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| gemma-4-31b_v2-dosv1_alert vs glm-5.3_v2_alert | tue | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| gemma-4-31b_v2-dosv1_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | all | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| gemma-4-31b_v2-dosv1_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | tue | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| gemma-4-31b_v2-dosv1_alert vs qwen3.6-27b-fp8_v2_alert | all | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| gemma-4-31b_v2-dosv1_alert vs qwen3.6-27b-fp8_v2_alert | tue | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| gemma-4-31b_v2_alert vs glm-5.3_v2-dosv1_alert | all | 43 | 2 | 2 | 0 | 0 | 1.0000 |
| gemma-4-31b_v2_alert vs glm-5.3_v2-dosv1_alert | tue | 43 | 2 | 2 | 0 | 0 | 1.0000 |
| gemma-4-31b_v2_alert vs glm-5.3_v2_alert | all | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| gemma-4-31b_v2_alert vs glm-5.3_v2_alert | tue | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| gemma-4-31b_v2_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | all | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| gemma-4-31b_v2_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | tue | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| gemma-4-31b_v2_alert vs qwen3.6-27b-fp8_v2_alert | all | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| gemma-4-31b_v2_alert vs qwen3.6-27b-fp8_v2_alert | tue | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| glm-5.3_v2-dosv1_alert vs glm-5.3_v2_alert | all | 43 | 2 | 2 | 0 | 0 | 1.0000 |
| glm-5.3_v2-dosv1_alert vs glm-5.3_v2_alert | tue | 43 | 2 | 2 | 0 | 0 | 1.0000 |
| glm-5.3_v2-dosv1_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | all | 43 | 2 | 2 | 0 | 0 | 1.0000 |
| glm-5.3_v2-dosv1_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | tue | 43 | 2 | 2 | 0 | 0 | 1.0000 |
| glm-5.3_v2-dosv1_alert vs qwen3.6-27b-fp8_v2_alert | all | 43 | 2 | 2 | 0 | 0 | 1.0000 |
| glm-5.3_v2-dosv1_alert vs qwen3.6-27b-fp8_v2_alert | tue | 43 | 2 | 2 | 0 | 0 | 1.0000 |
| glm-5.3_v2_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | all | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| glm-5.3_v2_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | tue | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| glm-5.3_v2_alert vs qwen3.6-27b-fp8_v2_alert | all | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| glm-5.3_v2_alert vs qwen3.6-27b-fp8_v2_alert | tue | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| qwen3.6-27b-fp8_v2-dosv1_alert vs qwen3.6-27b-fp8_v2_alert | all | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| qwen3.6-27b-fp8_v2-dosv1_alert vs qwen3.6-27b-fp8_v2_alert | tue | 44 | 2 | 2 | 0 | 0 | 1.0000 |
