# Held-out detection benchmark

Generated 2026-11-22T22:55:10+00:00. Evaluation split only; 95% block-bootstrap intervals (2000 draws, blocks of 20 windows). Thresholds marked "tuned" were chosen on attack-free tuning windows at a 1% false-positive rate.

## ROAD

- reference: 1 capture(s), 1,779 windows, 0 attack windows
- tuning: 15 capture(s), 34,607 windows, 607 attack windows
- evaluation: 25 capture(s), 11,552 windows, 1,954 attack windows

### Reference: single (1 capture(s), 445 s)

| detector | threshold | precision | recall | F1 | FPR | AUROC | AUPRC |
|---|---|---|---|---|---|---|---|
| Rule detector v1 (six components), fixed 0.55 | 0.55 | 0.384 [0.327, 0.440] | 0.466 [0.404, 0.522] | 0.421 [0.366, 0.468] | 0.152 [0.126, 0.177] | 0.565 | 0.274 |
| Rule detector v2 (three components), fixed 0.55 | 0.55 | 0.948 [0.915, 0.976] | 0.466 [0.403, 0.521] | 0.625 [0.563, 0.675] | 0.005 [0.002, 0.009] | 0.746 | 0.557 |
| Rule detector v1, tuned threshold | 1 | nan [nan, nan] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.565 | 0.274 |
| ID whitelist | 1 | 1.000 [1.000, 1.000] | 0.006 [0.001, 0.015] | 0.012 [0.002, 0.029] | 0.000 [0.000, 0.000] | 0.503 | 0.174 |
| Message interval | 1.4 | 0.879 [0.824, 0.926] | 0.495 [0.429, 0.554] | 0.634 [0.571, 0.685] | 0.014 [0.008, 0.020] | 0.764 | 0.587 |
| ID whitelist + message interval | 1.4 | 0.881 [0.827, 0.926] | 0.502 [0.436, 0.561] | 0.639 [0.578, 0.690] | 0.014 [0.008, 0.020] | 0.766 | 0.592 |
| ID entropy | 3.84 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.008 [0.003, 0.014] | 0.246 | 0.108 |
| IsolationForest | 0.664 | 0.019 [0.000, 0.047] | 0.002 [0.000, 0.004] | 0.003 [0.000, 0.006] | 0.016 [0.010, 0.023] | 0.671 | 0.309 |
| One-class SVM | -1.92 | 0.460 [0.348, 0.571] | 0.082 [0.058, 0.107] | 0.140 [0.099, 0.177] | 0.020 [0.014, 0.026] | 0.655 | 0.311 |

Recall by attack type (attack windows detected / total):

| detector | fuzzing | masquerade | spoofing | FPR on ambient captures |
|---|---|---|---|---|
| Rule detector v1 (six components), fixed 0.55 | 1.000 (12/12) | 0.004 (4/971) | 0.922 (895/971) | 0.185 (1459/7868) |
| Rule detector v2 (three components), fixed 0.55 | 1.000 (12/12) | 0.003 (3/971) | 0.922 (895/971) | 0.006 (50/7868) |
| Rule detector v1, tuned threshold | 0.000 (0/12) | 0.000 (0/971) | 0.000 (0/971) | 0.000 (0/7868) |
| ID whitelist | 1.000 (12/12) | 0.000 (0/971) | 0.000 (0/971) | 0.000 (0/7868) |
| Message interval | 0.000 (0/12) | 0.010 (10/971) | 0.987 (958/971) | 0.016 (129/7868) |
| ID whitelist + message interval | 1.000 (12/12) | 0.010 (10/971) | 0.987 (958/971) | 0.016 (129/7868) |
| ID entropy | 0.000 (0/12) | 0.000 (0/971) | 0.000 (0/971) | 0.009 (72/7868) |
| IsolationForest | 0.167 (2/12) | 0.000 (0/971) | 0.001 (1/971) | 0.019 (152/7868) |
| One-class SVM | 1.000 (12/12) | 0.002 (2/971) | 0.151 (147/971) | 0.024 (187/7868) |

### Reference: pooled (7 capture(s), 8,733 s)

| detector | threshold | precision | recall | F1 | FPR | AUROC | AUPRC |
|---|---|---|---|---|---|---|---|
| Rule detector v1 (six components), fixed 0.55 | 0.55 | 0.678 [0.595, 0.766] | 0.488 [0.424, 0.546] | 0.568 [0.504, 0.623] | 0.047 [0.031, 0.064] | 0.682 | 0.458 |
| Rule detector v2 (three components), fixed 0.55 | 0.55 | 0.950 [0.919, 0.977] | 0.488 [0.424, 0.546] | 0.645 [0.583, 0.695] | 0.005 [0.002, 0.009] | 0.747 | 0.574 |
| Rule detector v1, tuned threshold | 0.85 | 0.469 [0.118, 0.727] | 0.008 [0.001, 0.016] | 0.015 [0.002, 0.031] | 0.002 [0.001, 0.003] | 0.682 | 0.458 |
| ID whitelist | 1 | 1.000 [1.000, 1.000] | 0.006 [0.001, 0.015] | 0.012 [0.002, 0.029] | 0.000 [0.000, 0.000] | 0.503 | 0.174 |
| Message interval | 1.42 | 0.880 [0.825, 0.926] | 0.497 [0.430, 0.555] | 0.635 [0.573, 0.686] | 0.014 [0.008, 0.020] | 0.770 | 0.613 |
| ID whitelist + message interval | 1.42 | 0.881 [0.827, 0.926] | 0.503 [0.438, 0.562] | 0.640 [0.580, 0.691] | 0.014 [0.008, 0.020] | 0.772 | 0.617 |
| ID entropy | 3.84 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.008 [0.003, 0.014] | 0.246 | 0.108 |
| IsolationForest | 0.66 | 0.130 [0.018, 0.282] | 0.004 [0.000, 0.007] | 0.007 [0.001, 0.015] | 0.005 [0.003, 0.008] | 0.658 | 0.321 |
| One-class SVM | -2.47 | 0.832 [0.787, 0.869] | 0.483 [0.420, 0.540] | 0.611 [0.552, 0.660] | 0.020 [0.015, 0.025] | 0.774 | 0.634 |

Recall by attack type (attack windows detected / total):

| detector | fuzzing | masquerade | spoofing | FPR on ambient captures |
|---|---|---|---|---|
| Rule detector v1 (six components), fixed 0.55 | 1.000 (12/12) | 0.003 (3/971) | 0.967 (939/971) | 0.058 (453/7868) |
| Rule detector v2 (three components), fixed 0.55 | 1.000 (12/12) | 0.003 (3/971) | 0.967 (939/971) | 0.006 (50/7868) |
| Rule detector v1, tuned threshold | 1.000 (12/12) | 0.000 (0/971) | 0.003 (3/971) | 0.002 (17/7868) |
| ID whitelist | 1.000 (12/12) | 0.000 (0/971) | 0.000 (0/971) | 0.000 (0/7868) |
| Message interval | 0.000 (0/12) | 0.010 (10/971) | 0.990 (961/971) | 0.016 (129/7868) |
| ID whitelist + message interval | 1.000 (12/12) | 0.010 (10/971) | 0.990 (961/971) | 0.016 (129/7868) |
| ID entropy | 0.000 (0/12) | 0.000 (0/971) | 0.000 (0/971) | 0.009 (72/7868) |
| IsolationForest | 0.000 (0/12) | 0.000 (0/971) | 0.007 (7/971) | 0.006 (47/7868) |
| One-class SVM | 1.000 (12/12) | 0.011 (11/971) | 0.949 (921/971) | 0.021 (169/7868) |

### Reference coverage (rule detector, fixed 0.55)

| reference captures | seconds | added | FPR, held-out ambient | dyno_drive_benign_anomaly | dyno_drive_extended_short | dyno_drive_winter | dyno_idle_radio_infotainment | highway_street_driving_diagnostics | attack recall |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 445 | reference only | 0.185 (1459/7868) | 0.497 | 0.404 | 0.000 | 0.007 | 0.001 | 0.466 |
| 2 | 496 | dyno_reverse | 0.185 (1459/7868) | 0.497 | 0.405 | 0.000 | 0.006 | 0.002 | 0.466 |
| 3 | 887 | dyno_drive_radio_infotainment | 0.187 (1475/7868) | 0.497 | 0.407 | 0.000 | 0.006 | 0.009 | 0.467 |
| 4 | 1,544 | dyno_drive_extended_long | 0.073 (576/7868) | 0.144 | 0.143 | 0.000 | 0.006 | 0.056 | 0.489 |
| 5 | 2,796 | dyno_drive_basic_long | 0.062 (488/7868) | 0.144 | 0.149 | 0.000 | 0.006 | 0.006 | 0.488 |
| 6 | 4,968 | dyno_exercise_all_bits | 0.091 (718/7868) | 0.144 | 0.311 | 0.000 | 0.006 | 0.004 | 0.491 |
| 7 | 8,733 | highway_street_driving_long | 0.058 (453/7868) | 0.144 | 0.132 | 0.000 | 0.006 | 0.000 | 0.488 |

## HCRL

- reference: 1 capture(s), 479 windows, 0 attack windows
- tuning: 5 capture(s), 21,962 windows, 13,806 attack windows
- evaluation: 5 capture(s), 22,074 windows, 8,616 attack windows

### Reference: single (1 capture(s), 120 s)

| detector | threshold | precision | recall | F1 | FPR | AUROC | AUPRC |
|---|---|---|---|---|---|---|---|
| Rule detector v1 (six components), fixed 0.55 | 0.55 | 1.000 [1.000, 1.000] | 0.981 [0.978, 0.984] | 0.990 [0.989, 0.992] | 0.000 [0.000, 0.000] | 0.996 | 0.995 |
| Rule detector v2 (three components), fixed 0.55 | 0.55 | 1.000 [1.000, 1.000] | 0.974 [0.968, 0.980] | 0.987 [0.984, 0.990] | 0.000 [0.000, 0.000] | 0.997 | 0.996 |
| Rule detector v1, tuned threshold | 0.45 | 1.000 [1.000, 1.000] | 0.984 [0.980, 0.986] | 0.992 [0.990, 0.993] | 0.000 [0.000, 0.000] | 0.996 | 0.995 |
| ID whitelist | 1 | 1.000 [1.000, 1.000] | 0.588 [0.563, 0.612] | 0.740 [0.721, 0.760] | 0.000 [0.000, 0.000] | 0.794 | 0.749 |
| Message interval | 1.2 | 0.992 [0.989, 0.995] | 0.409 [0.385, 0.433] | 0.580 [0.555, 0.604] | 0.002 [0.001, 0.003] | 0.617 | 0.644 |
| ID whitelist + message interval | 1.2 | 0.997 [0.996, 0.998] | 0.996 [0.994, 0.997] | 0.996 [0.995, 0.997] | 0.002 [0.001, 0.003] | 0.999 | 0.999 |
| ID entropy | 2.04 | 0.999 [0.998, 1.000] | 0.964 [0.960, 0.967] | 0.981 [0.979, 0.983] | 0.001 [0.000, 0.001] | 0.992 | 0.993 |
| IsolationForest | 0.659 | 0.995 [0.993, 0.996] | 0.893 [0.886, 0.900] | 0.941 [0.937, 0.945] | 0.003 [0.002, 0.004] | 0.992 | 0.990 |
| One-class SVM | -2.29 | 0.988 [0.985, 0.991] | 0.992 [0.990, 0.994] | 0.990 [0.988, 0.992] | 0.008 [0.006, 0.010] | 0.999 | 0.999 |

Recall by attack type (attack windows detected / total):

| detector | dos | fuzzing | spoofing | FPR on ambient captures |
|---|---|---|---|---|
| Rule detector v1 (six components), fixed 0.55 | 1.000 (2337/2337) | 1.000 (2728/2728) | 0.953 (3385/3551) | 0.000 (0/825) |
| Rule detector v2 (three components), fixed 0.55 | 1.000 (2337/2337) | 1.000 (2728/2728) | 0.937 (3329/3551) | 0.000 (0/825) |
| Rule detector v1, tuned threshold | 1.000 (2337/2337) | 1.000 (2728/2728) | 0.960 (3409/3551) | 0.000 (0/825) |
| ID whitelist | 1.000 (2337/2337) | 1.000 (2728/2728) | 0.000 (0/3551) | 0.000 (0/825) |
| Message interval | 0.001 (3/2337) | 0.003 (8/2728) | 0.990 (3516/3551) | 0.000 (0/825) |
| ID whitelist + message interval | 1.000 (2337/2337) | 1.000 (2728/2728) | 0.990 (3516/3551) | 0.000 (0/825) |
| ID entropy | 0.942 (2201/2337) | 0.988 (2695/2728) | 0.960 (3408/3551) | 0.005 (4/825) |
| IsolationForest | 0.858 (2005/2337) | 0.892 (2433/2728) | 0.916 (3254/3551) | 0.006 (5/825) |
| One-class SVM | 0.977 (2284/2337) | 1.000 (2727/2728) | 0.997 (3539/3551) | 0.030 (25/825) |

