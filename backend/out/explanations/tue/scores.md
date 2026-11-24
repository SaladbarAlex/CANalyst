# Explainer scores: tue

Label accuracy on attack alerts, with Wilson 95% intervals. A failed or empty reply counts as wrong.

| run | tue | all | no answer | false alarms called benign | claims with valid citations | median latency |
|---|---|---|---|---|---|---|
| control-v1_alert | 5% (2/44; 1 to 15) | 5% (2/44; 1 to 15) | 0 | n/a | 100% (48/48; 93 to 100) | 0.0s |
| control-v2_alert | 5% (2/44; 1 to 15) | 5% (2/44; 1 to 15) | 0 | n/a | 100% (48/48; 93 to 100) | 0.0s |

## By true attack type

| run | tue/dos | tue/fuzzing | tue/replay |
|---|---|---|---|
| control-v1_alert | 100% (2/2; 34 to 100) | 0% (0/40; 0 to 9) | 0% (0/2; 0 to 66) |
| control-v2_alert | 100% (2/2; 34 to 100) | 0% (0/40; 0 to 9) | 0% (0/2; 0 to 66) |

## Paired comparisons (exact McNemar)

| pair | group | n | first correct | second correct | only first | only second | p |
|---|---|---|---|---|---|---|---|
| control-v1_alert vs control-v2_alert | all | 44 | 2 | 2 | 0 | 0 | 1.0000 |
| control-v1_alert vs control-v2_alert | tue | 44 | 2 | 2 | 0 | 0 | 1.0000 |
