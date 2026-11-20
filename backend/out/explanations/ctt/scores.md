# Explainer scores: ctt

Label accuracy on attack alerts, with Wilson 95% intervals. A failed or empty reply counts as wrong.

| run | ctt | all | no answer | false alarms called benign | claims with valid citations | median latency |
|---|---|---|---|---|---|---|
| control-v1_alert | 67% (28/42; 52 to 79) | 67% (28/42; 52 to 79) | 0 | 0% (0/59; 0 to 6) | 100% (141/141; 97 to 100) | 0.0s |
| control-v2_alert | 69% (29/42; 54 to 81) | 69% (29/42; 54 to 81) | 0 | 95% (56/59; 86 to 98) | 100% (198/198; 98 to 100) | 0.0s |

## By true attack type

| run | ctt/dos | ctt/fuzzing | ctt/spoofing |
|---|---|---|---|
| control-v1_alert | 0% (0/14; 0 to 22) | 100% (15/15; 80 to 100) | 100% (13/13; 77 to 100) |
| control-v2_alert | 7% (1/14; 1 to 31) | 100% (15/15; 80 to 100) | 100% (13/13; 77 to 100) |

## Paired comparisons (exact McNemar)

| pair | group | n | first correct | second correct | only first | only second | p |
|---|---|---|---|---|---|---|---|
| control-v1_alert vs control-v2_alert | all | 42 | 28 | 29 | 0 | 1 | 1.0000 |
| control-v1_alert vs control-v2_alert | ctt | 42 | 28 | 29 | 0 | 1 | 1.0000 |
