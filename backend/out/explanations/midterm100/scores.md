# Explainer scores: midterm100

Label accuracy on attack alerts, with Wilson 95% intervals.

| run | hcrl | road | all | false alarms called benign | claims with valid citations | median latency |
|---|---|---|---|---|---|---|
| control-v1_alert | 77% (53/69; 66 to 85) | 85% (17/20; 64 to 95) | 79% (70/89; 69 to 86) | 0% (0/11; 0 to 26) | 100% (176/176; 98 to 100) | 0.0s |
| control-v1_window | 77% (53/69; 66 to 85) | 85% (17/20; 64 to 95) | 79% (70/89; 69 to 86) | 0% (0/11; 0 to 26) | 100% (179/179; 98 to 100) | 0.0s |
| control-v2_alert | 100% (69/69; 95 to 100) | 80% (16/20; 58 to 92) | 96% (85/89; 89 to 98) | 45% (5/11; 21 to 72) | 100% (198/198; 98 to 100) | 0.0s |

## By true attack type

| run | hcrl/dos | hcrl/fuzzing | hcrl/spoofing | road/fuzzing | road/masquerade | road/spoofing |
|---|---|---|---|---|---|---|
| control-v1_alert | 0% (0/16; 0 to 19) | 100% (15/15; 80 to 100) | 100% (38/38; 91 to 100) | 100% (3/3; 44 to 100) | 25% (1/4; 5 to 70) | 100% (13/13; 77 to 100) |
| control-v1_window | 0% (0/16; 0 to 19) | 100% (15/15; 80 to 100) | 100% (38/38; 91 to 100) | 100% (3/3; 44 to 100) | 25% (1/4; 5 to 70) | 100% (13/13; 77 to 100) |
| control-v2_alert | 100% (16/16; 81 to 100) | 100% (15/15; 80 to 100) | 100% (38/38; 91 to 100) | 100% (3/3; 44 to 100) | 0% (0/4; 0 to 49) | 100% (13/13; 77 to 100) |

## Paired comparisons (exact McNemar)

| pair | group | n | first correct | second correct | only first | only second | p |
|---|---|---|---|---|---|---|---|
| control-v1_alert vs control-v1_window | all | 89 | 70 | 70 | 0 | 0 | 1.0000 |
| control-v1_alert vs control-v1_window | hcrl | 69 | 53 | 53 | 0 | 0 | 1.0000 |
| control-v1_alert vs control-v1_window | road | 20 | 17 | 17 | 0 | 0 | 1.0000 |
| control-v1_alert vs control-v2_alert | all | 89 | 70 | 85 | 1 | 16 | 0.0003 |
| control-v1_alert vs control-v2_alert | hcrl | 69 | 53 | 69 | 0 | 16 | 0.0000 |
| control-v1_alert vs control-v2_alert | road | 20 | 17 | 16 | 1 | 0 | 1.0000 |
| control-v1_window vs control-v2_alert | all | 89 | 70 | 85 | 1 | 16 | 0.0003 |
| control-v1_window vs control-v2_alert | hcrl | 69 | 53 | 69 | 0 | 16 | 0.0000 |
| control-v1_window vs control-v2_alert | road | 20 | 17 | 16 | 1 | 0 | 1.0000 |
