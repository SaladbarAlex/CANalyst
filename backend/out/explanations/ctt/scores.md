# Explainer scores: ctt

Label accuracy on attack alerts, with Wilson 95% intervals. A failed or empty reply counts as wrong.

| run | ctt | all | no answer | false alarms called benign | claims with valid citations | median latency |
|---|---|---|---|---|---|---|
| control-v1_alert | 67% (28/42; 52 to 79) | 67% (28/42; 52 to 79) | 0 | 0% (0/59; 0 to 6) | 100% (141/141; 97 to 100) | 0.0s |
| control-v2_alert | 69% (29/42; 54 to 81) | 69% (29/42; 54 to 81) | 0 | 95% (56/59; 86 to 98) | 100% (198/198; 98 to 100) | 0.0s |
| gemma-4-31b_v2-dosv1_alert | 57% (24/42; 42 to 71) | 57% (24/42; 42 to 71) | 0 | 100% (59/59; 94 to 100) | 99% (543/547; 98 to 100) | 25.0s |
| gemma-4-31b_v2_alert | 55% (23/42; 40 to 69) | 55% (23/42; 40 to 69) | 0 | 100% (59/59; 94 to 100) | 99% (537/542; 98 to 100) | 24.6s |
| glm-5.3_v2-dosv1_alert | 74% (31/42; 59 to 85) | 74% (31/42; 59 to 85) | 1 | 95% (56/59; 86 to 98) | 100% (901/901; 100 to 100) | 63.6s |
| glm-5.3_v2_alert | 74% (31/42; 59 to 85) | 74% (31/42; 59 to 85) | 3 | 95% (56/59; 86 to 98) | 100% (890/890; 100 to 100) | 69.2s |
| qwen3.6-27b-fp8_v2-dosv1_alert | 76% (32/42; 61 to 87) | 76% (32/42; 61 to 87) | 0 | 100% (59/59; 94 to 100) | 97% (596/612; 96 to 98) | 77.6s |
| qwen3.6-27b-fp8_v2_alert | 81% (34/42; 67 to 90) | 81% (34/42; 67 to 90) | 0 | 100% (59/59; 94 to 100) | 98% (561/571; 97 to 99) | 84.8s |

## By true attack type

| run | ctt/dos | ctt/fuzzing | ctt/spoofing |
|---|---|---|---|
| control-v1_alert | 0% (0/14; 0 to 22) | 100% (15/15; 80 to 100) | 100% (13/13; 77 to 100) |
| control-v2_alert | 7% (1/14; 1 to 31) | 100% (15/15; 80 to 100) | 100% (13/13; 77 to 100) |
| gemma-4-31b_v2-dosv1_alert | 21% (3/14; 8 to 48) | 53% (8/15; 30 to 75) | 100% (13/13; 77 to 100) |
| gemma-4-31b_v2_alert | 14% (2/14; 4 to 40) | 53% (8/15; 30 to 75) | 100% (13/13; 77 to 100) |
| glm-5.3_v2-dosv1_alert | 21% (3/14; 8 to 48) | 100% (15/15; 80 to 100) | 100% (13/13; 77 to 100) |
| glm-5.3_v2_alert | 21% (3/14; 8 to 48) | 100% (15/15; 80 to 100) | 100% (13/13; 77 to 100) |
| qwen3.6-27b-fp8_v2-dosv1_alert | 57% (8/14; 33 to 79) | 73% (11/15; 48 to 89) | 100% (13/13; 77 to 100) |
| qwen3.6-27b-fp8_v2_alert | 71% (10/14; 45 to 88) | 80% (12/15; 55 to 93) | 92% (12/13; 67 to 99) |

## Paired comparisons (exact McNemar)

| pair | group | n | first correct | second correct | only first | only second | p |
|---|---|---|---|---|---|---|---|
| control-v1_alert vs control-v2_alert | all | 42 | 28 | 29 | 0 | 1 | 1.0000 |
| control-v1_alert vs control-v2_alert | ctt | 42 | 28 | 29 | 0 | 1 | 1.0000 |
| control-v1_alert vs gemma-4-31b_v2-dosv1_alert | all | 42 | 28 | 24 | 7 | 3 | 0.3438 |
| control-v1_alert vs gemma-4-31b_v2-dosv1_alert | ctt | 42 | 28 | 24 | 7 | 3 | 0.3438 |
| control-v1_alert vs gemma-4-31b_v2_alert | all | 42 | 28 | 23 | 7 | 2 | 0.1797 |
| control-v1_alert vs gemma-4-31b_v2_alert | ctt | 42 | 28 | 23 | 7 | 2 | 0.1797 |
| control-v1_alert vs glm-5.3_v2-dosv1_alert | all | 42 | 28 | 31 | 0 | 3 | 0.2500 |
| control-v1_alert vs glm-5.3_v2-dosv1_alert | ctt | 42 | 28 | 31 | 0 | 3 | 0.2500 |
| control-v1_alert vs glm-5.3_v2_alert | all | 42 | 28 | 31 | 0 | 3 | 0.2500 |
| control-v1_alert vs glm-5.3_v2_alert | ctt | 42 | 28 | 31 | 0 | 3 | 0.2500 |
| control-v1_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | all | 42 | 28 | 32 | 4 | 8 | 0.3877 |
| control-v1_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | ctt | 42 | 28 | 32 | 4 | 8 | 0.3877 |
| control-v1_alert vs qwen3.6-27b-fp8_v2_alert | all | 42 | 28 | 34 | 4 | 10 | 0.1796 |
| control-v1_alert vs qwen3.6-27b-fp8_v2_alert | ctt | 42 | 28 | 34 | 4 | 10 | 0.1796 |
| control-v2_alert vs gemma-4-31b_v2-dosv1_alert | all | 42 | 29 | 24 | 7 | 2 | 0.1797 |
| control-v2_alert vs gemma-4-31b_v2-dosv1_alert | ctt | 42 | 29 | 24 | 7 | 2 | 0.1797 |
| control-v2_alert vs gemma-4-31b_v2_alert | all | 42 | 29 | 23 | 7 | 1 | 0.0703 |
| control-v2_alert vs gemma-4-31b_v2_alert | ctt | 42 | 29 | 23 | 7 | 1 | 0.0703 |
| control-v2_alert vs glm-5.3_v2-dosv1_alert | all | 42 | 29 | 31 | 0 | 2 | 0.5000 |
| control-v2_alert vs glm-5.3_v2-dosv1_alert | ctt | 42 | 29 | 31 | 0 | 2 | 0.5000 |
| control-v2_alert vs glm-5.3_v2_alert | all | 42 | 29 | 31 | 0 | 2 | 0.5000 |
| control-v2_alert vs glm-5.3_v2_alert | ctt | 42 | 29 | 31 | 0 | 2 | 0.5000 |
| control-v2_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | all | 42 | 29 | 32 | 4 | 7 | 0.5488 |
| control-v2_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | ctt | 42 | 29 | 32 | 4 | 7 | 0.5488 |
| control-v2_alert vs qwen3.6-27b-fp8_v2_alert | all | 42 | 29 | 34 | 4 | 9 | 0.2668 |
| control-v2_alert vs qwen3.6-27b-fp8_v2_alert | ctt | 42 | 29 | 34 | 4 | 9 | 0.2668 |
| gemma-4-31b_v2-dosv1_alert vs gemma-4-31b_v2_alert | all | 42 | 24 | 23 | 1 | 0 | 1.0000 |
| gemma-4-31b_v2-dosv1_alert vs gemma-4-31b_v2_alert | ctt | 42 | 24 | 23 | 1 | 0 | 1.0000 |
| gemma-4-31b_v2-dosv1_alert vs glm-5.3_v2-dosv1_alert | all | 42 | 24 | 31 | 1 | 8 | 0.0391 |
| gemma-4-31b_v2-dosv1_alert vs glm-5.3_v2-dosv1_alert | ctt | 42 | 24 | 31 | 1 | 8 | 0.0391 |
| gemma-4-31b_v2-dosv1_alert vs glm-5.3_v2_alert | all | 42 | 24 | 31 | 1 | 8 | 0.0391 |
| gemma-4-31b_v2-dosv1_alert vs glm-5.3_v2_alert | ctt | 42 | 24 | 31 | 1 | 8 | 0.0391 |
| gemma-4-31b_v2-dosv1_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | all | 42 | 24 | 32 | 0 | 8 | 0.0078 |
| gemma-4-31b_v2-dosv1_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | ctt | 42 | 24 | 32 | 0 | 8 | 0.0078 |
| gemma-4-31b_v2-dosv1_alert vs qwen3.6-27b-fp8_v2_alert | all | 42 | 24 | 34 | 1 | 11 | 0.0063 |
| gemma-4-31b_v2-dosv1_alert vs qwen3.6-27b-fp8_v2_alert | ctt | 42 | 24 | 34 | 1 | 11 | 0.0063 |
| gemma-4-31b_v2_alert vs glm-5.3_v2-dosv1_alert | all | 42 | 23 | 31 | 0 | 8 | 0.0078 |
| gemma-4-31b_v2_alert vs glm-5.3_v2-dosv1_alert | ctt | 42 | 23 | 31 | 0 | 8 | 0.0078 |
| gemma-4-31b_v2_alert vs glm-5.3_v2_alert | all | 42 | 23 | 31 | 0 | 8 | 0.0078 |
| gemma-4-31b_v2_alert vs glm-5.3_v2_alert | ctt | 42 | 23 | 31 | 0 | 8 | 0.0078 |
| gemma-4-31b_v2_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | all | 42 | 23 | 32 | 0 | 9 | 0.0039 |
| gemma-4-31b_v2_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | ctt | 42 | 23 | 32 | 0 | 9 | 0.0039 |
| gemma-4-31b_v2_alert vs qwen3.6-27b-fp8_v2_alert | all | 42 | 23 | 34 | 1 | 12 | 0.0034 |
| gemma-4-31b_v2_alert vs qwen3.6-27b-fp8_v2_alert | ctt | 42 | 23 | 34 | 1 | 12 | 0.0034 |
| glm-5.3_v2-dosv1_alert vs glm-5.3_v2_alert | all | 42 | 31 | 31 | 1 | 1 | 1.0000 |
| glm-5.3_v2-dosv1_alert vs glm-5.3_v2_alert | ctt | 42 | 31 | 31 | 1 | 1 | 1.0000 |
| glm-5.3_v2-dosv1_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | all | 42 | 31 | 32 | 4 | 5 | 1.0000 |
| glm-5.3_v2-dosv1_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | ctt | 42 | 31 | 32 | 4 | 5 | 1.0000 |
| glm-5.3_v2-dosv1_alert vs qwen3.6-27b-fp8_v2_alert | all | 42 | 31 | 34 | 4 | 7 | 0.5488 |
| glm-5.3_v2-dosv1_alert vs qwen3.6-27b-fp8_v2_alert | ctt | 42 | 31 | 34 | 4 | 7 | 0.5488 |
| glm-5.3_v2_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | all | 42 | 31 | 32 | 4 | 5 | 1.0000 |
| glm-5.3_v2_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | ctt | 42 | 31 | 32 | 4 | 5 | 1.0000 |
| glm-5.3_v2_alert vs qwen3.6-27b-fp8_v2_alert | all | 42 | 31 | 34 | 4 | 7 | 0.5488 |
| glm-5.3_v2_alert vs qwen3.6-27b-fp8_v2_alert | ctt | 42 | 31 | 34 | 4 | 7 | 0.5488 |
| qwen3.6-27b-fp8_v2-dosv1_alert vs qwen3.6-27b-fp8_v2_alert | all | 42 | 32 | 34 | 2 | 4 | 0.6875 |
| qwen3.6-27b-fp8_v2-dosv1_alert vs qwen3.6-27b-fp8_v2_alert | ctt | 42 | 32 | 34 | 2 | 4 | 0.6875 |
