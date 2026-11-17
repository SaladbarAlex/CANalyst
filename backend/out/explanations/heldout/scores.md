# Explainer scores: heldout

Label accuracy on attack alerts, with Wilson 95% intervals.

| run | hcrl | road | all | false alarms called benign | claims with valid citations | median latency |
|---|---|---|---|---|---|---|
| control-v1_alert | 76% (53/70; 65 to 84) | n/a | 76% (53/70; 65 to 84) | 0% (0/7; 0 to 35) | 100% (132/132; 97 to 100) | 0.0s |
| control-v2_alert | 100% (70/70; 95 to 100) | n/a | 100% (70/70; 95 to 100) | 57% (4/7; 25 to 84) | 100% (153/153; 98 to 100) | 0.0s |

## By true attack type

| run | hcrl/dos | hcrl/fuzzing | hcrl/spoofing |
|---|---|---|---|
| control-v1_alert | 0% (0/17; 0 to 18) | 100% (15/15; 80 to 100) | 100% (38/38; 91 to 100) |
| control-v2_alert | 100% (17/17; 82 to 100) | 100% (15/15; 80 to 100) | 100% (38/38; 91 to 100) |

## Paired comparisons (exact McNemar)

| pair | group | n | first correct | second correct | only first | only second | p |
|---|---|---|---|---|---|---|---|
| control-v1_alert vs control-v2_alert | all | 70 | 53 | 70 | 0 | 17 | 0.0000 |
| control-v1_alert vs control-v2_alert | hcrl | 70 | 53 | 70 | 0 | 17 | 0.0000 |
