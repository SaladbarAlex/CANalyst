# Controls and detection audit — October 30, 2026

The control bugs below are fixed and covered by regression tests. The new experiments do **not** establish a generally better detector. The normal-only calibrated forest improves the original ROAD development comparison, but performs poorly on Car-Hacking's attack-recording normal windows. Broader baseline and state-profile experiments expose serious sensitivity/false-alarm tradeoffs and remain experimental.

## Implemented fixes

| Defect | Fix and evidence |
|---|---|
| IsolationForest silently fit evaluation data when an external baseline set `fit_until=0`, or fewer than 11 fitting rows existed | Explicit normal-only `fit` API, normal temporal fitting/calibration separation, minimum sample checks, attack-label contamination rejection. Missing training now raises a useful error. Pipeline integration is in `app/pipeline.py`. |
| Forest scores depended on the min/max of each evaluated capture | Fixed sigmoid map anchored to a held-out normal-score quantile and scale. Regression verifies the same window keeps its score when unrelated extreme evaluation rows are added. Scores are anomaly indices, not probabilities. |
| Forest ignored the dashboard threshold | Both detectors now honor the requested threshold; invalid detector names and thresholds raise errors. |
| Forest omitted jitter collapse used by the rule control | Added `n_jitter_collapses` to the learned detector feature vector. This improves feature parity; it does not isolate every difference between the models. |
| Perfectly periodic benign IDs could be flagged as collapsed jitter because zero normal jitter was replaced with epsilon | No collapse inference when the baseline has no measurable jitter above the existing precision floor. |
| Empty CAN payloads produced nonfinite bit-flip features | Zero-width payload sequences now yield a finite zero change rate. |
| Baseline concatenation measured artificial inter-arrival and bit-flip transitions between recordings | Preserve `_capture_id`; compute inter-arrival and bit-flip statistics within recordings; exclude windows spanning recording joins; exclude joining gaps from rate duration. |
| Unsorted traffic could corrupt search-based window extraction | Stable timestamp sorting plus finite/positive window/stride checks. Attack-contaminated and degenerate baselines fail explicitly. |
| Header-based Car-Hacking payloads could include padding beyond DLC | Respect DLC; validate payload length, byte range, classic-CAN DLC, arbitration ID, and finite timestamps. |
| Malformed candump rows and odd-nibble ROAD payloads could silently disappear/truncate | Reject malformed/unsupported records with line context; strict hex parsing. This loader supports classic CAN, not silently truncated CAN FD/RTR. |
| Unknown/missing label values could silently become normal ground truth | Validate label vocabularies. Car-Hacking accepts `T` injection, `R` received/normal, and the existing `F` normal variant. ROAD accepts explicit normal/attack boolean variants. |
| Threshold sweep caches could reuse scores after baseline, source, metadata, or code changes | Hash all those inputs and require a matching manifest. Reporting rejects stale/unversioned caches by default; `--allow-stale` explicitly permits historical inspection with a warning. |
| Stored rounded scores could disagree with the runtime threshold decision | Keep full precision in scored frames. A score of 0.5499565 must not be serialized as 0.5500 and then reflagged by a 0.55 sweep. Format precision only for display. |
| Scripts could evaluate the entire same recording used as baseline | Reject that direct input overlap in `evaluate.py` and `sweep.py`. `evaluate.py` also rejects empty seed lists and creates output directories. Explicit disjoint slices remain available in the benchmark scripts. |

The root work also corrects baseline-crossing evaluation-window exclusion, evidence/control-explainer semantics, model handling, and the UI. Those changes are outside this detector audit's ownership.

## Reproducing the completed development experiments

Run commands from `CANalyst/backend`. Outputs are under `out/detectors_2026-10-30`. The scripts refuse to overwrite an existing `results.json`; use a new `--out` directory to reproduce with current code.

```bash
.venv/bin/python -u -m scripts.evaluate_detectors --dataset hcrl
.venv/bin/python -u -m scripts.evaluate_detectors --dataset road --baseline-profile midterm
.venv/bin/python -u -m scripts.evaluate_detectors --dataset road --baseline-profile broad
.venv/bin/python -u -m scripts.evaluate_detectors --dataset road --baseline-profile broad --forest-split per_capture
.venv/bin/python -u -m scripts.evaluate_state_detector --baseline-profile midterm
.venv/bin/python -u -m scripts.evaluate_state_detector --baseline-profile broad
```

The state-detector script verifies its evaluation-window starts, ends, labels, and attack types exactly match the saved paired reference in `out/detectors_2026-10-30/road_<profile>`. It intentionally fails if a reference is missing or the pairing differs.

HCRL uses the first 120 seconds of each of four attacks, normal baseline `[0,120)`, and normal holdout `[121,241)` of the separate normal recording: 998,323 evaluation frames and 2,395 windows. These are **not** the full-file HCRL results in the midterm paper.

ROAD's original scope retains all 29 labeled attacks and up to 120 seconds of two held-out ambient recordings: 3,808,639 frames and 6,353 windows. Its baseline is the complete `basic_short` ambient recording. The broader profile uses up to 120 seconds each of `basic_short`, `extended_long`, `reverse`, `idle_radio_infotainment`, and `drive_radio_infotainment`; all seven other ambient recordings are held out. Shorter recordings contribute their full available duration. Broad evaluation has 4,666,983 frames and 8,357 windows. All 12 ambient recordings already existed locally; no additional download was needed for this experiment.

The original forest split holds out the final 20% of the concatenated normal timeline. That leaves some final operating states largely calibration-only. The optional per-capture split instead trains on early and calibrates on later windows of **every** normal recording. Training/calibration windows cannot share frame intervals. All thresholds, quantiles, and feature scales were fixed before each recorded evaluation; none were selected by optimizing its labels.

## Measured results

These are pooled window metrics, not independent-sample estimates. Broader profiles contain five additional normal holdouts, so their pooled metrics must not be treated as an equal-scope improvement over the original scope.

| Evaluation scope / detector | Precision | Recall | F1 | Pooled FPR | Normal-holdout FPR |
|---|---:|---:|---:|---:|---:|
| HCRL prefixes / rule | 1.0000 | 0.9825 | 0.9912 | 0.0000 | 0.0000 |
| HCRL prefixes / calibrated forest | 0.6526 | 1.0000 | 0.7898 | 0.5860 | 0.0146 |
| ROAD original / rule | 0.7702 | 0.5092 | 0.6131 | 0.1026 | 0.3956 |
| ROAD original / calibrated forest | 0.8737 | 0.5377 | 0.6657 | 0.0525 | 0.1618 |
| ROAD broad / rule | 0.4782 | 0.8383 | 0.6090 | 0.4042 | 0.4673 |
| ROAD broad / forest, concatenated split | 0.6720 | 0.5392 | 0.5984 | 0.1163 | 0.2022 |
| ROAD broad / forest, per-capture split | 0.8977 | 0.0925 | 0.1678 | 0.0047 | 0.0091 |
| ROAD original / state-window experiment | 0.6772 | 0.5717 | 0.6199 | 0.1841 | 0.2724 |
| ROAD broad / state-window experiment | 0.6797 | 0.4947 | 0.5727 | 0.1030 | 0.1681 |

The HCRL forest flagged every benign window inside the four attack recordings, despite only 1.46% FPR on the independent time slice of the normal recording. Its perfect attack recall therefore is not a satisfactory result.

The broad rule baseline's FPR on the *same* `basic_long` normal holdout rises from 0.21% to 73.90%. Component inspection shows payload entropy triggered all 354 broad-baseline false alarms there; rate inflation triggered only one. On `extended_short`, entropy triggered 269 of 290 false alarms and rate inflation triggered 28. The evidence supports a mismatch between pooled payload-byte entropy and normal within-window entropy. Adding more normal traffic to an averaged scalar reference is not sufficient. Inspection samples and counts are in `road_broad/false_positive_diagnosis.json`.

## State-window experiment and limitations

The new `app/state_detector.py` learns each normal recording's per-ID window distributions for rate, byte entropy, bit-flip rate, and timing jitter. It measures distance to the closest normal operating-state profile, previously unseen payload-byte values, and unknown-ID frame rate. Each recording's first 80% fits the reference; later disjoint complete windows calibrate component cutoffs. The fixed calibration quantile is `1 - 0.01/3`, with fixed finite-sample/physical scale floors saved in the report. This empirical target is not a guarantee under correlated windows or new operating states.

The global payload-novelty cutoff reaches 1.0 in both normal calibration sets, correctly disabling that component: benign calibration can itself contain wholly unseen values for at least one byte/ID. The state-window original-scope recalls are 98.74% spoofing, 14.68% masquerade, and 100% fuzzing. Broader-profile recalls are 97.47%, **0.39%**, and 100%. These outcomes do not justify promotion to the default detector or an analyst-quality success claim.

A subsequent predeclared experiment could calibrate novelty **per ID and byte position**, so one legitimate variable byte does not disable violations of otherwise static bytes. Candidate split: early 80% normal reference, next 10% per-field calibration, final 10% window-level calibration. That is a future experiment, not an implemented or validated fix. Because the current development outcomes have now been inspected, further detector selection needs a newly declared tuning/evaluation partition, grouping related ROAD fabrication/masquerade recordings and keeping final evaluation data out of tuning. Additional independently recorded normal/attack data may be needed for a credible final test; later slices of a known recording are not independent drives.

## Artifacts and verification

Each experiment folder contains `results.json`, input/source hashes, window score CSVs, counts, calibration information, and timings. The per-capture forest and both state-window experiments additionally retain `source_snapshot/` and matching hashes. Earlier paired results retain their historical loaded-code hashes. Subsequent parser validation and full-precision-score fixes do not retroactively alter those artifacts. All six selected HCRL inputs were reloaded after parser validation; frame and attack-frame counts exactly match the earlier reports.

The initial paired detector's `score_s` measures scoring and alert assembly, while ingest timings include reproducibility hashing/slicing. The state experiment's end-to-end timings also include artifact work. Some jobs ran concurrently. These timing records support preliminary engineering inspection; they are not a controlled dashboard latency study.

```bash
.venv/bin/python -m pytest -q tests/test_controls.py tests/test_pipeline.py tests/test_state_detector.py
```

Regression coverage includes normal-only fitting, nonoverlapping calibration, score invariance, threshold consistency, periodic benign timing, empty payloads, recording boundaries, attack-contaminated baseline rejection, parsing errors, stale caches, per-state fitting representation, and label-independent experimental predictions. Frozen midterm reports/results remain preserved.

## Full Car-Hacking scope verification

A subsequent scope-completion run evaluates **all records** of all four attack files, preserving the original normal baseline `[0,120)` and normal holdout `[121,241)`. No detector settings or algorithms changed for this run. Captures were processed sequentially to bound memory.

```bash
.venv/bin/python -u -m scripts.evaluate_detectors --dataset hcrl --full-hcrl \
  --out out/detectors_full_hcrl_2026-10-30
```

Artifacts: `out/detectors_full_hcrl_2026-10-30/hcrl_full_midterm/`. The directory contains `results.json`, ten per-capture/per-detector score files, immutable source snapshots, and `verification.json`. The verification confirms **16,803,792 frames and 42,975 windows**, exact source and selected-input hashes against the original full midterm evaluation, the same normal baseline input, and exact per-window start/end/label/attack-type alignment for both detectors. Score-file hashes, threshold decisions, and recomputed metrics also match. The full run completed successfully in 230.34 seconds on this host; this is benchmark processing time, not dashboard/model response latency.

| Full HCRL detector | TP | FP | FN | TN | Precision | Recall | F1 | FPR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Archived midterm rule | 21,986 | 65 | 438 | 20,486 | 0.9971 | 0.9805 | 0.9887 | 0.00316 |
| Revised rule | 21,986 | 28 | 438 | 20,523 | 0.9987 | 0.9805 | 0.9895 | 0.00136 |
| Normal-calibrated forest | 22,423 | 20,079 | 1 | 472 | 0.5276 | 1.0000* | 0.6907 | 0.97703 |

*Forest recall is 0.999955 before rounding. It flags every normal window inside the four attack recordings; its separate normal-holdout FPR is 7/479 (1.46%). The revised rule's normal holdout has zero false positives. The reduction from 65 to 28 rule false positives preserves the same 21,986 true positives and 438 misses. This supports the corrected rule control on the original development scope, while decisively rejecting this forest configuration as a replacement on Car-Hacking. It still does not establish generalization to an untouched final test set.

## Late integration fixes and final scope conclusion

The bounded final review identified and confirmed the following additional fixes. These are input, slicing, and demo correctness fixes; no detector was tuned in response to the final review.

| Late issue | Confirmed behavior after correction |
|---|---|
| An evaluation upload and baseline could contain identical traffic yet evade the equality guard because only the evaluation copy had ROAD labels | Both the upload route and direct pipeline compare timestamp, CAN ID, DLC, and payload, independent of label differences, and reject identical training/evaluation traffic. HTTP and direct-pipeline regressions cover both paths. |
| Valid form fields could combine into an impossible short-demo baseline or insufficient Forest calibration and cause HTTP 500 | The synthetic route returns an actionable HTTP 422 for those combinations. Both previously failing requests were independently replayed successfully as validation errors. |
| A 20-second demo retained a 30-second clean prefix, so selected attacks vanished and declared intervals could be reversed/outside the capture | Short demos cap the clean prefix at half their duration. Replay lookback is bounded; attack choices are validated and deduplicated. Independent verification confirms all five selected attacks are present in a 20-second capture with correctly ordered, bounded intervals. Standard 150-second generation retains its 30-second prefix. |
| `capture(start > 0, stop=None)` ignored the requested start while recording it in provenance | Open-ended slices now select only the requested tail and rebase timestamps/ROAD metadata to the actual first selected frame. A four-frame source with start 2 now returns exactly the last two frames and records origin 2. |

Relevant regressions are in `tests/test_api_workflow.py` and `tests/test_capture_slices.py`. The final bounded review found no additional material blocker in these corrections. The original full real-data input/window alignment remains verified: the completed benchmark uses full attacks beginning at zero and finite normal intervals, so the open-tail fix does not change its selected data. The guards likewise do not change its separate normal baseline. Preserve the benchmark snapshots as the authoritative implementation for each recorded run.

The verified detection conclusion remains narrow: the revised rule control reduces full Car-Hacking false positives while retaining its prior sensitivity; the configured Forest and broader/state-window alternatives do not establish a generally superior detector. The preserved negative results and source/window verification are part of the deliverable. They do not support an untouched-test generalization claim or justify promoting the unsuccessful experimental detectors.
