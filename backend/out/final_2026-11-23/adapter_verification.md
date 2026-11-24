# CTT and TU Eindhoven adapter verification

## Reproduce the offline runs

Install the raw data at the extraction paths in the dataset notes. Run these commands from the repository root. They write new alert and evidence files to a temporary directory without calling an explainer. [Dataset notes](../../../docs/ADDITIONAL_DATASETS.md)

```sh
cd backend
audit_out=$(mktemp -d /tmp/canalyst-adapter-audit.XXXXXX)
.venv/bin/python -m scripts.freeze_alerts --set ctt --out "$audit_out"
.venv/bin/python -m scripts.freeze_alerts --set tue --out "$audit_out"
printf '%s\n' "$audit_out"
```

Compare the new `manifest.json`, `alerts_all.jsonl`, `alerts.jsonl`, and both packet files with the archived files. Parse the JSON before comparing. The temporary paths, manifest timestamps, and recorded code hashes identify the new run. [CTT archive](../alerts/ctt/) · [TU Eindhoven archive](../alerts/tue/)

## Source and split checks

- All 42 CTT and 14 TU Eindhoven source SHA-256 hashes match the archived manifests. All selected-input hashes, frame counts, label counts, distinct ID counts, durations, and per-capture alert counts also match.
- CTT selected 34,509,774 frames across four vehicles. The 42 selected source files have distinct hashes. The published ZIP has 62 groups with matching size and CRC. The selected reference and evaluation files shared isolated exact frame rows but no consecutive matching rows. CTT resets capture clocks to a common start, so this check cannot establish independent recording sessions.
- Each TU Eindhoven training and testing pair matches its full original drive line for line. The timestamps are disjoint. All five scored attack copies per vehicle derive from its testing segment. The prototype and deletion-only suspension files are outside this benchmark.
- All five TU Eindhoven generation code hashes match commit `c88579c`. The four CTT application code hashes match commit `c489a66`. The CTT freeze-script hash matches no reachable committed version of that script. Its archived SHA-256 is `ad340b919676734bcccb5632f20516cb5be211f285ebf5c8a68913ce75c4105a`.

## Output comparison

| Dataset | Alert comparison | Packet comparison |
| --- | --- | --- |
| CTT | All 196 uncapped and 101 capped alert IDs, captures, spans, and labels match. The cap retains the same 42 attack alerts and 59 false alarms. | The capped alert-scope packets match exactly for 90/101 targets. The window-scope packets match exactly for 75/101. |
| TU Eindhoven | All 44 alert rows match exactly after JSON parsing. Both benign testing files raised zero alerts. | All 44 alert-scope and all 44 window-scope packets match exactly after JSON parsing. |

The current CTT detector retains more score precision. Rounding to four decimal places reproduces every archived score. The maximum absolute difference is 0.000026087 across 30 uncapped rows, 11 of which are in the capped set. Packet differences involve detector scores, alert detail, and unknown-ID detail. The published model replies used the archived packets.

## Fixes and test results

- Dataset discovery now accepts both documented extraction paths. CTT rejects invalid labels and payloads. TU Eindhoven attack loading requires the corresponding benign testing log.
- Re-freezing publishes the new uncapped set before sampling false alarms. New manifests record the catalog and slicing code hashes, plus scored-capture line repairs.
- The scorer and benchmark API count missing replies against declared targets. The archived TU Eindhoven GLM ablation has two correct labels across 44 targets and one missing reply. Undefined bounds use JSON null. The archived scores and replies retain their original contents.
- 192 backend tests and 23 frontend tests passed. The production frontend build passed with a bundle-size advisory.
