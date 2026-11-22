# Merged detector verification

The offline run repeats the November detection protocol on installed ROAD and HCRL data. It uses 0.50 s windows, a 0.25 s stride, and a 0.55 threshold for both profiles. Profile v1 scores six components. Profile v2 scores bus load, unknown IDs, and per-ID rate inflation.

| Evaluation | Profile | TP | FP | FN | TN | Precision | Recall | FPR |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ROAD, single reference | v1 | 911 | 1,461 | 1,043 | 8,137 | 38.41% | 46.62% | 15.22% |
| ROAD, single reference | v2 | 910 | 50 | 1,044 | 9,548 | 94.79% | 46.57% | 0.52% |
| ROAD, pooled reference | v1 | 954 | 453 | 1,000 | 9,145 | 67.80% | 48.82% | 4.72% |
| ROAD, pooled reference | v2 | 954 | 50 | 1,000 | 9,548 | 95.02% | 48.82% | 0.52% |
| HCRL, single reference | v1 | 8,450 | 1 | 166 | 13,457 | 99.99% | 98.07% | 0.0074% |
| HCRL, single reference | v2 | 8,394 | 0 | 222 | 13,458 | 100% | 97.42% | 0% |

ROAD evaluation uses 11,552 windows, including 1,954 attack windows. HCRL uses 22,074 windows, including 8,616 attack windows. [Full fresh benchmark](results.md)

| ROAD configuration | Fuzzing recall | Spoofing recall | Masquerade recall | Ambient-only FPR |
| --- | ---: | ---: | ---: | ---: |
| Single v1 | 12/12 | 895/971 | 4/971 | 1,459/7,868 |
| Single v2 | 12/12 | 895/971 | 3/971 | 50/7,868 |
| Pooled v1 | 12/12 | 939/971 | 3/971 | 453/7,868 |
| Pooled v2 | 12/12 | 939/971 | 3/971 | 50/7,868 |

## Comparison with November 17

All four ROAD confusion matrices and the HCRL v2 confusion matrix reproduce exactly. HCRL v1 retains 8,450 true positives and 166 false negatives. Its false positives fall from 32 to one. [Frozen November 17 report](../../benchmark/results.md)

An isolated check recomputed the HCRL matrices with the same raw measurement cache, reference, and split. It crossed the November 17 functions from `17aaa82` with the merged functions. The merged feature path excludes jitter floors at or below 10 microseconds from jitter collapse. Score rounding made no difference to these fixed-threshold flags.

| Feature path | November 17 scorer | Merged scorer |
| --- | ---: | ---: |
| November 17 | 32 FP | 32 FP |
| Merged | 1 FP | 1 FP |

## Default recommendation

Keep v1 as the general default. With one ROAD reference, v2 avoids 1,411 false-positive windows and misses one additional attack window. In HCRL it avoids one false positive and misses 56 additional spoofing windows. Masquerade remains the main ROAD weakness. Either profile detects at most four of 971 masquerade windows in this split.

## Protocol

- ROAD separates reference, tuning, and evaluation by capture. Each fabrication capture and its derived masquerade twin stays in the same split. Four accelerator captures lack usable injection intervals and are excluded from evaluation.
- HCRL uses disjoint time slices within the same recordings. The reference is the first 120 seconds of normal traffic. Windows that cross a split boundary are dropped.
- Precision, recall, and FPR count windows. FPR includes both ambient traffic and normal windows inside attack captures. The report also gives ambient-only FPR.
- The 95% intervals use 2,000 bootstrap draws of 20 consecutive windows. The resampling keeps the capture set fixed. The intervals describe variability within these recordings.
- October development touched all 25 November ROAD evaluation sources. It scored the 20 attack captures end to end. It used prefixes of all five ambient captures. October also scored all four HCRL attack recordings end to end. HCRL normal evaluation uses a later slice of the same normal recording. The November split separates fitting from scoring within its protocol. Prior development limits any claim of independent validation or transfer to other vehicles. [October development evidence](../../../../docs/PROGRESS_2026-10-30.md)

## Reproduction

Run from `backend/`. Choose an unused results path for each rerun.

```sh
.venv/bin/python -m scripts.build_cache --dataset all --force --workers 1
.venv/bin/python -m scripts.benchmark --dataset all --out out/detection-rerun
.venv/bin/python -m pytest tests/test_controls.py tests/test_windowstats.py -q
```

The installed HCRL normal capture ends with an unterminated timestamp on line 988872. The parser initially rejected it. The cache builder now explicitly excludes that incomplete line for HCRL normal data and records its line number. Live ingestion still requires complete records. Both installed archives contain the same truncated capture. The raw file was preserved. The resumed build reused completed caches and rebuilt the failed HCRL normal cache with the narrow repair.

The full benchmark ran in 34.7 s after caching. The host ran macOS on ARM64 with Python 3.12.14, NumPy 2.5.4, pandas 3.0.6, SciPy 1.18.1, and scikit-learn 1.9.1. The run used local data and made zero hosted model calls.

## Verification checks

- All 50 cache entries matched their raw source SHA-256 hashes. The manifest includes the ROAD label metadata hash, source code hashes, and frozen and fresh result hashes. [Verification manifest](verification.json)
- Fresh single-reference v1 flags matched the October live scorer on 5,395 ROAD windows and 42,496 HCRL windows from attack captures. Window boundaries, labels, and attack types matched. ROAD score differences were below 0.00005.
- Both profiles matched live feature extraction and scoring on 155 fresh windows from a ROAD fabrication capture, its masquerade twin, and a fuzzing capture.
