# Explainer scores: midterm100

Label accuracy on attack alerts, with Wilson 95% intervals. A failed or empty reply counts as wrong.

| run | hcrl | road | all | no answer | false alarms called benign | claims with valid citations | median latency |
|---|---|---|---|---|---|---|---|
| control-v1_alert | 77% (53/69; 66 to 85) | 85% (17/20; 64 to 95) | 79% (70/89; 69 to 86) | 0 | 0% (0/11; 0 to 26) | 100% (176/176; 98 to 100) | 0.0s |
| control-v1_window | 77% (53/69; 66 to 85) | 85% (17/20; 64 to 95) | 79% (70/89; 69 to 86) | 0 | 0% (0/11; 0 to 26) | 100% (179/179; 98 to 100) | 0.0s |
| control-v2_alert | 100% (69/69; 95 to 100) | 80% (16/20; 58 to 92) | 96% (85/89; 89 to 98) | 0 | 45% (5/11; 21 to 72) | 100% (198/198; 98 to 100) | 0.0s |
| gemma-4-31b_v2-dosv1_alert | n/a | 80% (16/20; 58 to 92) | 80% (16/20; 58 to 92) | 0 | 64% (7/11; 35 to 85) | 100% (172/172; 98 to 100) | 20.2s |
| gemma-4-31b_v2_alert | 96% (66/69; 88 to 99) | 80% (16/20; 58 to 92) | 92% (82/89; 85 to 96) | 0 | 64% (7/11; 35 to 85) | 100% (538/539; 99 to 100) | 15.4s |
| glm-5.3_v2-dosv1_alert | n/a | 80% (16/20; 58 to 92) | 80% (16/20; 58 to 92) | 0 | 60% (6/10; 31 to 83) | 100% (270/270; 99 to 100) | 39.3s |
| glm-5.3_v2_alert | 88% (61/69; 79 to 94) | 80% (16/20; 58 to 92) | 87% (77/89; 78 to 92) | 5 | 64% (7/11; 35 to 85) | 100% (888/888; 100 to 100) | 38.6s |
| qwen3.6-27b-fp8_v2-dosv1_alert | n/a | 75% (15/20; 53 to 89) | 75% (15/20; 53 to 89) | 0 | 73% (8/11; 43 to 90) | 99% (192/193; 97 to 100) | 67.9s |
| qwen3.6-27b-fp8_v2_alert | 52% (36/69; 41 to 64) | 70% (14/20; 48 to 85) | 56% (50/89; 46 to 66) | 0 | 91% (10/11; 62 to 98) | 99% (588/594; 98 to 100) | 55.3s |

## By true attack type

| run | hcrl/dos | hcrl/fuzzing | hcrl/spoofing | road/fuzzing | road/masquerade | road/spoofing |
|---|---|---|---|---|---|---|
| control-v1_alert | 0% (0/16; 0 to 19) | 100% (15/15; 80 to 100) | 100% (38/38; 91 to 100) | 100% (3/3; 44 to 100) | 25% (1/4; 5 to 70) | 100% (13/13; 77 to 100) |
| control-v1_window | 0% (0/16; 0 to 19) | 100% (15/15; 80 to 100) | 100% (38/38; 91 to 100) | 100% (3/3; 44 to 100) | 25% (1/4; 5 to 70) | 100% (13/13; 77 to 100) |
| control-v2_alert | 100% (16/16; 81 to 100) | 100% (15/15; 80 to 100) | 100% (38/38; 91 to 100) | 100% (3/3; 44 to 100) | 0% (0/4; 0 to 49) | 100% (13/13; 77 to 100) |
| gemma-4-31b_v2-dosv1_alert | n/a | n/a | n/a | 100% (3/3; 44 to 100) | 0% (0/4; 0 to 49) | 100% (13/13; 77 to 100) |
| gemma-4-31b_v2_alert | 100% (16/16; 81 to 100) | 100% (15/15; 80 to 100) | 92% (35/38; 79 to 97) | 100% (3/3; 44 to 100) | 0% (0/4; 0 to 49) | 100% (13/13; 77 to 100) |
| glm-5.3_v2-dosv1_alert | n/a | n/a | n/a | 100% (3/3; 44 to 100) | 0% (0/4; 0 to 49) | 100% (13/13; 77 to 100) |
| glm-5.3_v2_alert | 100% (16/16; 81 to 100) | 100% (15/15; 80 to 100) | 79% (30/38; 64 to 89) | 100% (3/3; 44 to 100) | 0% (0/4; 0 to 49) | 100% (13/13; 77 to 100) |
| qwen3.6-27b-fp8_v2-dosv1_alert | n/a | n/a | n/a | 67% (2/3; 21 to 94) | 0% (0/4; 0 to 49) | 100% (13/13; 77 to 100) |
| qwen3.6-27b-fp8_v2_alert | 100% (16/16; 81 to 100) | 100% (15/15; 80 to 100) | 13% (5/38; 6 to 27) | 33% (1/3; 6 to 79) | 0% (0/4; 0 to 49) | 100% (13/13; 77 to 100) |

## Paired comparisons (exact McNemar)

| pair | group | n | first correct | second correct | only first | only second | p |
|---|---|---|---|---|---|---|---|
| control-v1_alert vs control-v1_window | all | 89 | 70 | 70 | 0 | 0 | 1.0000 |
| control-v1_alert vs control-v1_window | hcrl | 69 | 53 | 53 | 0 | 0 | 1.0000 |
| control-v1_alert vs control-v1_window | road | 20 | 17 | 17 | 0 | 0 | 1.0000 |
| control-v1_alert vs control-v2_alert | all | 89 | 70 | 85 | 1 | 16 | 0.0003 |
| control-v1_alert vs control-v2_alert | hcrl | 69 | 53 | 69 | 0 | 16 | 0.0000 |
| control-v1_alert vs control-v2_alert | road | 20 | 17 | 16 | 1 | 0 | 1.0000 |
| control-v1_alert vs gemma-4-31b_v2-dosv1_alert | all | 20 | 17 | 16 | 1 | 0 | 1.0000 |
| control-v1_alert vs gemma-4-31b_v2-dosv1_alert | road | 20 | 17 | 16 | 1 | 0 | 1.0000 |
| control-v1_alert vs gemma-4-31b_v2_alert | all | 89 | 70 | 82 | 4 | 16 | 0.0118 |
| control-v1_alert vs gemma-4-31b_v2_alert | hcrl | 69 | 53 | 66 | 3 | 16 | 0.0044 |
| control-v1_alert vs gemma-4-31b_v2_alert | road | 20 | 17 | 16 | 1 | 0 | 1.0000 |
| control-v1_alert vs glm-5.3_v2-dosv1_alert | all | 20 | 17 | 16 | 1 | 0 | 1.0000 |
| control-v1_alert vs glm-5.3_v2-dosv1_alert | road | 20 | 17 | 16 | 1 | 0 | 1.0000 |
| control-v1_alert vs glm-5.3_v2_alert | all | 89 | 70 | 77 | 9 | 16 | 0.2295 |
| control-v1_alert vs glm-5.3_v2_alert | hcrl | 69 | 53 | 61 | 8 | 16 | 0.1516 |
| control-v1_alert vs glm-5.3_v2_alert | road | 20 | 17 | 16 | 1 | 0 | 1.0000 |
| control-v1_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | all | 20 | 17 | 15 | 2 | 0 | 0.5000 |
| control-v1_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | road | 20 | 17 | 15 | 2 | 0 | 0.5000 |
| control-v1_alert vs qwen3.6-27b-fp8_v2_alert | all | 89 | 70 | 50 | 36 | 16 | 0.0078 |
| control-v1_alert vs qwen3.6-27b-fp8_v2_alert | hcrl | 69 | 53 | 36 | 33 | 16 | 0.0213 |
| control-v1_alert vs qwen3.6-27b-fp8_v2_alert | road | 20 | 17 | 14 | 3 | 0 | 0.2500 |
| control-v1_window vs control-v2_alert | all | 89 | 70 | 85 | 1 | 16 | 0.0003 |
| control-v1_window vs control-v2_alert | hcrl | 69 | 53 | 69 | 0 | 16 | 0.0000 |
| control-v1_window vs control-v2_alert | road | 20 | 17 | 16 | 1 | 0 | 1.0000 |
| control-v1_window vs gemma-4-31b_v2-dosv1_alert | all | 20 | 17 | 16 | 1 | 0 | 1.0000 |
| control-v1_window vs gemma-4-31b_v2-dosv1_alert | road | 20 | 17 | 16 | 1 | 0 | 1.0000 |
| control-v1_window vs gemma-4-31b_v2_alert | all | 89 | 70 | 82 | 4 | 16 | 0.0118 |
| control-v1_window vs gemma-4-31b_v2_alert | hcrl | 69 | 53 | 66 | 3 | 16 | 0.0044 |
| control-v1_window vs gemma-4-31b_v2_alert | road | 20 | 17 | 16 | 1 | 0 | 1.0000 |
| control-v1_window vs glm-5.3_v2-dosv1_alert | all | 20 | 17 | 16 | 1 | 0 | 1.0000 |
| control-v1_window vs glm-5.3_v2-dosv1_alert | road | 20 | 17 | 16 | 1 | 0 | 1.0000 |
| control-v1_window vs glm-5.3_v2_alert | all | 89 | 70 | 77 | 9 | 16 | 0.2295 |
| control-v1_window vs glm-5.3_v2_alert | hcrl | 69 | 53 | 61 | 8 | 16 | 0.1516 |
| control-v1_window vs glm-5.3_v2_alert | road | 20 | 17 | 16 | 1 | 0 | 1.0000 |
| control-v1_window vs qwen3.6-27b-fp8_v2-dosv1_alert | all | 20 | 17 | 15 | 2 | 0 | 0.5000 |
| control-v1_window vs qwen3.6-27b-fp8_v2-dosv1_alert | road | 20 | 17 | 15 | 2 | 0 | 0.5000 |
| control-v1_window vs qwen3.6-27b-fp8_v2_alert | all | 89 | 70 | 50 | 36 | 16 | 0.0078 |
| control-v1_window vs qwen3.6-27b-fp8_v2_alert | hcrl | 69 | 53 | 36 | 33 | 16 | 0.0213 |
| control-v1_window vs qwen3.6-27b-fp8_v2_alert | road | 20 | 17 | 14 | 3 | 0 | 0.2500 |
| control-v2_alert vs gemma-4-31b_v2-dosv1_alert | all | 20 | 16 | 16 | 0 | 0 | 1.0000 |
| control-v2_alert vs gemma-4-31b_v2-dosv1_alert | road | 20 | 16 | 16 | 0 | 0 | 1.0000 |
| control-v2_alert vs gemma-4-31b_v2_alert | all | 89 | 85 | 82 | 3 | 0 | 0.2500 |
| control-v2_alert vs gemma-4-31b_v2_alert | hcrl | 69 | 69 | 66 | 3 | 0 | 0.2500 |
| control-v2_alert vs gemma-4-31b_v2_alert | road | 20 | 16 | 16 | 0 | 0 | 1.0000 |
| control-v2_alert vs glm-5.3_v2-dosv1_alert | all | 20 | 16 | 16 | 0 | 0 | 1.0000 |
| control-v2_alert vs glm-5.3_v2-dosv1_alert | road | 20 | 16 | 16 | 0 | 0 | 1.0000 |
| control-v2_alert vs glm-5.3_v2_alert | all | 89 | 85 | 77 | 8 | 0 | 0.0078 |
| control-v2_alert vs glm-5.3_v2_alert | hcrl | 69 | 69 | 61 | 8 | 0 | 0.0078 |
| control-v2_alert vs glm-5.3_v2_alert | road | 20 | 16 | 16 | 0 | 0 | 1.0000 |
| control-v2_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | all | 20 | 16 | 15 | 1 | 0 | 1.0000 |
| control-v2_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | road | 20 | 16 | 15 | 1 | 0 | 1.0000 |
| control-v2_alert vs qwen3.6-27b-fp8_v2_alert | all | 89 | 85 | 50 | 35 | 0 | 0.0000 |
| control-v2_alert vs qwen3.6-27b-fp8_v2_alert | hcrl | 69 | 69 | 36 | 33 | 0 | 0.0000 |
| control-v2_alert vs qwen3.6-27b-fp8_v2_alert | road | 20 | 16 | 14 | 2 | 0 | 0.5000 |
| gemma-4-31b_v2-dosv1_alert vs gemma-4-31b_v2_alert | all | 20 | 16 | 16 | 0 | 0 | 1.0000 |
| gemma-4-31b_v2-dosv1_alert vs gemma-4-31b_v2_alert | road | 20 | 16 | 16 | 0 | 0 | 1.0000 |
| gemma-4-31b_v2-dosv1_alert vs glm-5.3_v2-dosv1_alert | all | 20 | 16 | 16 | 0 | 0 | 1.0000 |
| gemma-4-31b_v2-dosv1_alert vs glm-5.3_v2-dosv1_alert | road | 20 | 16 | 16 | 0 | 0 | 1.0000 |
| gemma-4-31b_v2-dosv1_alert vs glm-5.3_v2_alert | all | 20 | 16 | 16 | 0 | 0 | 1.0000 |
| gemma-4-31b_v2-dosv1_alert vs glm-5.3_v2_alert | road | 20 | 16 | 16 | 0 | 0 | 1.0000 |
| gemma-4-31b_v2-dosv1_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | all | 20 | 16 | 15 | 1 | 0 | 1.0000 |
| gemma-4-31b_v2-dosv1_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | road | 20 | 16 | 15 | 1 | 0 | 1.0000 |
| gemma-4-31b_v2-dosv1_alert vs qwen3.6-27b-fp8_v2_alert | all | 20 | 16 | 14 | 2 | 0 | 0.5000 |
| gemma-4-31b_v2-dosv1_alert vs qwen3.6-27b-fp8_v2_alert | road | 20 | 16 | 14 | 2 | 0 | 0.5000 |
| gemma-4-31b_v2_alert vs glm-5.3_v2-dosv1_alert | all | 20 | 16 | 16 | 0 | 0 | 1.0000 |
| gemma-4-31b_v2_alert vs glm-5.3_v2-dosv1_alert | road | 20 | 16 | 16 | 0 | 0 | 1.0000 |
| gemma-4-31b_v2_alert vs glm-5.3_v2_alert | all | 89 | 82 | 77 | 5 | 0 | 0.0625 |
| gemma-4-31b_v2_alert vs glm-5.3_v2_alert | hcrl | 69 | 66 | 61 | 5 | 0 | 0.0625 |
| gemma-4-31b_v2_alert vs glm-5.3_v2_alert | road | 20 | 16 | 16 | 0 | 0 | 1.0000 |
| gemma-4-31b_v2_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | all | 20 | 16 | 15 | 1 | 0 | 1.0000 |
| gemma-4-31b_v2_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | road | 20 | 16 | 15 | 1 | 0 | 1.0000 |
| gemma-4-31b_v2_alert vs qwen3.6-27b-fp8_v2_alert | all | 89 | 82 | 50 | 32 | 0 | 0.0000 |
| gemma-4-31b_v2_alert vs qwen3.6-27b-fp8_v2_alert | hcrl | 69 | 66 | 36 | 30 | 0 | 0.0000 |
| gemma-4-31b_v2_alert vs qwen3.6-27b-fp8_v2_alert | road | 20 | 16 | 14 | 2 | 0 | 0.5000 |
| glm-5.3_v2-dosv1_alert vs glm-5.3_v2_alert | all | 20 | 16 | 16 | 0 | 0 | 1.0000 |
| glm-5.3_v2-dosv1_alert vs glm-5.3_v2_alert | road | 20 | 16 | 16 | 0 | 0 | 1.0000 |
| glm-5.3_v2-dosv1_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | all | 20 | 16 | 15 | 1 | 0 | 1.0000 |
| glm-5.3_v2-dosv1_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | road | 20 | 16 | 15 | 1 | 0 | 1.0000 |
| glm-5.3_v2-dosv1_alert vs qwen3.6-27b-fp8_v2_alert | all | 20 | 16 | 14 | 2 | 0 | 0.5000 |
| glm-5.3_v2-dosv1_alert vs qwen3.6-27b-fp8_v2_alert | road | 20 | 16 | 14 | 2 | 0 | 0.5000 |
| glm-5.3_v2_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | all | 20 | 16 | 15 | 1 | 0 | 1.0000 |
| glm-5.3_v2_alert vs qwen3.6-27b-fp8_v2-dosv1_alert | road | 20 | 16 | 15 | 1 | 0 | 1.0000 |
| glm-5.3_v2_alert vs qwen3.6-27b-fp8_v2_alert | all | 89 | 77 | 50 | 27 | 0 | 0.0000 |
| glm-5.3_v2_alert vs qwen3.6-27b-fp8_v2_alert | hcrl | 69 | 61 | 36 | 25 | 0 | 0.0000 |
| glm-5.3_v2_alert vs qwen3.6-27b-fp8_v2_alert | road | 20 | 16 | 14 | 2 | 0 | 0.5000 |
| qwen3.6-27b-fp8_v2-dosv1_alert vs qwen3.6-27b-fp8_v2_alert | all | 20 | 15 | 14 | 1 | 0 | 1.0000 |
| qwen3.6-27b-fp8_v2-dosv1_alert vs qwen3.6-27b-fp8_v2_alert | road | 20 | 15 | 14 | 1 | 0 | 1.0000 |
