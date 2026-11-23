# Additional CAN datasets

Downloaded and extracted on November 22, 2026. Git ignores the source files under `backend/data/raw/`. Validation covered archive integrity and sample parsing. Benchmark scores are pending.

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

Add a CSV adapter that maps `arbitration_id` and `data_field` to the internal ID and payload fields. Preserve `attack` as the frame label and infer the payload length from the decoded bytes. Keep each set's published splits together. The archive contains 62 groups of CSV entries with matching size and CRC across sets.

## TU Eindhoven CAN v2

The archive includes raw captures from an Opel Astra, a Renault Clio, and a CAN prototype. The publisher's READMEs say the car attack files are offline edits of each car's benign test capture. The prototype includes captures of attacks run on the testbed. [4TU release](https://data.4tu.nl/datasets/efb320d8-c189-4e54-98af-3a79cc14f421/2) · [Publisher file manifest](https://data.4tu.nl/v2/articles/12696950)

Local root is `backend/data/raw/tu-eindhoven-can-v2/`. The extracted `OpelAstra/`, `RenaultClio/`, and `Prototype/` folders each contain a README.

| Publisher file | Bytes | Publisher MD5, matched locally | Local SHA-256 |
| --- | ---: | --- | --- |
| [data.zip](https://data.4tu.nl/file/efb320d8-c189-4e54-98af-3a79cc14f421/71c7531a-c3b4-4af3-aa91-a33f0b88e45b) | 102,928,327 | `c4202839088b75ce60e8485b1e1413d4` | `2f4a6bafabc1a0df59173b50fd89ad24efaf0a5cd64453c59ddf9500f267e49a` |

The first 1,000 lines of each log parsed as classic candump records. CANalyst's existing candump loader also read all 115,971 frames in the Renault Clio benign test log. It returned unknown ground truth because no metadata was supplied.

Reuse the candump parser and add a catalog that records the publisher's split and ground truth. Derive labels from the documented changes or intervals where the source supports them. Keep captures derived from the same benign session in the same evaluation partition.
