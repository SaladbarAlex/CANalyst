# Additional CAN datasets

Both datasets have capture adapters and saved explanation benchmarks. The verifier matched the archive files for all 42 selected DTU capture inputs and all 14 TU Eindhoven inputs. Git ignores raw files under `backend/data/raw/`. [Verified results](FINAL_RESULTS_2026-11-23.md#additional-vehicles)

| Dataset | Version | License | Extracted CAN files |
| --- | --- | --- | --- |
| [can-train-and-test](https://doi.org/10.11583/DTU.24805533.v2) | 2, November 19, 2026 | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | 236 CSV files in four sets |
| [Automotive Controller Area Network (CAN) Bus Intrusion Dataset v2](https://doi.org/10.4121/uuid:b74b4928-c377-4585-9432-2004dfa20a5d) | 2, November 14, 2019 | [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) | 29 candump logs across two cars and a prototype |

## can-train-and-test

The four vehicles are a Subaru Forester, Chevrolet Silverado, Chevrolet Traverse, and Chevrolet Impala. Each set has one training split and four test splits. The test splits vary whether the vehicle and attack type appeared in training. [DTU release](https://data.dtu.dk/articles/dataset/can-train-and-test/24805533/2) · [Publisher file manifest](https://api.figshare.com/v2/articles/24805533/versions/2)

Local root is `backend/data/raw/can-train-and-test-v2/`. Extracted captures are in `extracted/cantrainandtest/can-train-and-test/set_*/`. The archive also contains a README identical to the separately published copy.

| Publisher file | Bytes | Publisher MD5, matched locally | Local SHA-256 |
| --- | ---: | --- | --- |
| [cantrainandtest (1).zip](https://ndownloader.figshare.com/files/71631709) | 1,508,575,081 | `e58f2a52c7f6e5ae09c95d894ca33a64` | `b747adb0eb925f446d2ab56fec29cd15f57365152a5bc39d9aefa61a9e5be559` |
| [README.md](https://ndownloader.figshare.com/files/71631724) | 2,312 | `6272d3e46925461395a9a7d6c71cb28f` | `469cf47dccd910268e75a02afc2b304a1f6e8eb539d097d0d3dfb268a4de4000` |

The first 1,000 rows of each CSV parsed as `timestamp,arbitration_id,data_field,attack`. Across the 236,000 sampled rows, 9 had label `1`. A separate check found a positive label in a training capture from each set.

The CSV adapter reads hexadecimal IDs and payload bytes. It preserves binary frame labels and derives payload length from the decoded bytes. The selected captures use a clean reference and up to 240 seconds of another benign capture per vehicle. The scored attack captures come from the publisher's known-vehicle test splits. [Capture catalog](../backend/app/datasets.py) · [Parser](../backend/app/loader.py)

The selected files have distinct SHA-256 hashes. The full archive contains 62 groups of CSV entries with matching size and CRC across sets. File hashes establish unique files within the selected manifest. They do not establish separate recording sessions. [Frozen DTU manifest](../backend/out/alerts/ctt/manifest.json)

The saved detector run produced 196 alerts, including 42 attacks and 154 false alarms. The explainer benchmark kept all 42 attacks and sampled 59 false alarms with a cap of three per capture. A fresh freeze reproduced the alert targets and the cap selection. It matched 90/101 alert packets and 75/101 window packets. The archived freeze-script hash has no matching reachable committed version. Use the saved packets for exact historical comparisons. [DTU scores](../backend/out/explanations/ctt/scores.md) · [Fresh adapter verification](../backend/out/final_2026-11-23/adapter_verification.md)

## TU Eindhoven CAN v2

The archive includes raw captures from an Opel Astra, a Renault Clio, and a CAN prototype. The publisher's READMEs say the car attack files are offline edits of each car's benign test capture. The prototype includes captures of attacks run on the testbed. [4TU release](https://data.4tu.nl/datasets/efb320d8-c189-4e54-98af-3a79cc14f421/2) · [Publisher file manifest](https://data.4tu.nl/v2/articles/12696950)

Local root is `backend/data/raw/tu-eindhoven-can-v2/`. Extract the archive into `extracted/` under that root. The extracted `OpelAstra/`, `RenaultClio/`, and `Prototype/` folders each contain a README.

| Publisher file | Bytes | Publisher MD5, matched locally | Local SHA-256 |
| --- | ---: | --- | --- |
| [data.zip](https://data.4tu.nl/file/efb320d8-c189-4e54-98af-3a79cc14f421/71c7531a-c3b4-4af3-aa91-a33f0b88e45b) | 102,928,327 | `c4202839088b75ce60e8485b1e1413d4` | `2f4a6bafabc1a0df59173b50fd89ad24efaf0a5cd64453c59ddf9500f267e49a` |

The first 1,000 lines of each log parsed as classic candump records. The TU Eindhoven adapter compares each attack log against the same car's benign `testing.log`. It labels added or changed lines by exact candump line counts. It repairs and counts one stray trailing backslash in the Opel Astra CAN-ID fuzzing log. [Parser](../backend/app/loader.py)

Each car uses `training.log` for reference and `testing.log` for evaluation. These are separate sections of the same original drive. Attack files are offline edits of the testing section. The benchmark excludes the prototype, deletion-only suspension files, and the combined full-drive logs. [Capture catalog](../backend/app/datasets.py) · [Frozen TU Eindhoven manifest](../backend/out/alerts/tue/manifest.json)

The detector produced 44 attack alerts and zero false alarms. Diagnostics and CAN-ID changes account for 40 alerts labeled fuzzing. The remaining four targets comprise two DoS and two replay alerts. Neither payload-fuzzing file produced any alerts. A fresh freeze reproduced all 44 alerts and both packet scopes as parsed JSON. [TU Eindhoven scores](../backend/out/explanations/tue/scores.md) · [Fresh adapter verification](../backend/out/final_2026-11-23/adapter_verification.md)

## Verify the saved experiments

Run from `backend` after installing the archives and project dependencies. The verifier checks saved replies and source hashes without hosted inference.

```sh
result_dir=$(mktemp -d /tmp/canalyst-dataset-verify.XXXXXX)
.venv/bin/python -m scripts.summarize_final_models --verify-raw \
  --out "$result_dir/model_results.json"
```

To freeze a new corpus with the current detector, use a fresh output directory. These commands preserve the saved corpora.

```sh
freeze_dir=$(mktemp -d /tmp/canalyst-alert-freeze.XXXXXX)
.venv/bin/python -m scripts.freeze_alerts --set ctt --out "$freeze_dir"
.venv/bin/python -m scripts.freeze_alerts --set tue --out "$freeze_dir"
```
