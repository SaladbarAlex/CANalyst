"""Catalog of the public captures and the evaluation protocol.

Everything that decides which capture is used for what lives here, in one
place, so the protocol can be read (and criticized) without reading the
scripts. Nothing in this file looks at detector output: the assignments
are fixed by capture name before any scoring.

Protocol
--------
Three disjoint roles for every dataset:

    reference    attack-free traffic the baseline is learned from
    tuning       captures any threshold, rule or model may be fitted on
    evaluation   captures that are scored once and reported

ROAD (one vehicle, 33 attack captures, 12 ambient captures)
    reference    ambient_dyno_drive_basic_short, as in the midterm run
    ambient      the other 11 captures, sorted by name, alternate
                 tuning / evaluation
    attacks      instance 1 of every attack family is tuning; instances
                 2 and 3, and the single engine-coolant capture, are
                 evaluation. A fabrication capture and its derived
                 masquerade twin share one recording, so the pair always
                 lands in the same split.
    excluded     the four accelerator captures: the metadata gives no
                 injection interval, so windows cannot be labeled

Car-Hacking (one vehicle, 4 attack captures, 1 attack-free capture)
    reference    normal_run_data [0, 120) s, as in the midterm run
    normal       [120, 300) s tuning, [300, end) evaluation
    attacks      each capture is one session of 300 injection bursts
                 followed by an attack-free tail. It is split at its median
                 non-empty window: the first half of the session is tuning,
                 the rest and the tail are evaluation. The dataset has one
                 capture per attack, so a within-capture split is the only
                 one available; the two parts are disjoint in time.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

_ROOTS = {
    "hcrl": ["data/raw/hcrl-car-hacking", "data/9) Car-Hacking Dataset", "data/hcrl"],
    "road": ["data/raw/road/road", "data/road/road", "data/road"],
}

HCRL_REFERENCE_S = (0.0, 120.0)
HCRL_NORMAL_TUNING_S = (120.0, 300.0)
HCRL_NORMAL_EVAL_START_S = 300.0
ROAD_REFERENCE = "ambient_dyno_drive_basic_short"


@dataclass
class Capture:
    dataset: str
    name: str
    path: Path
    kind: str                       # "attack" | "ambient"
    attack_type: str | None = None  # explainer vocabulary: dos, fuzzing, spoofing, masquerade
    family: str | None = None       # e.g. "max_speedometer", "DoS"
    role: str = "evaluation"        # "reference" | "tuning" | "evaluation" | "excluded" | "split"
    meta: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.dataset}/{self.name}"


def find_root(dataset: str, backend: Path = BACKEND) -> Path:
    for rel in _ROOTS[dataset]:
        root = backend / rel
        if dataset == "hcrl" and (root / "DoS_dataset.csv").exists():
            return root
        if dataset == "road" and (root / "attacks" / "capture_metadata.json").exists():
            return root
    raise FileNotFoundError(
        f"{dataset} data not found under {backend}. Looked in: {', '.join(_ROOTS[dataset])}")


def road_family(name: str) -> tuple[str, int | None, bool]:
    """('max_speedometer', 2, True) for 'max_speedometer_attack_2_masquerade'."""
    masq = name.endswith("_masquerade")
    stem = name[:-len("_masquerade")] if masq else name
    family, _, tail = stem.partition("_attack")
    digits = tail.strip("_")
    return family, (int(digits) if digits.isdigit() else None), masq


def road_catalog(backend: Path = BACKEND) -> list[Capture]:
    root = find_root("road", backend)
    out: list[Capture] = []
    meta = json.loads((root / "attacks" / "capture_metadata.json").read_text())
    for name, entry in sorted(meta.items()):
        family, instance, masq = road_family(name)
        if not entry.get("injection_interval"):
            role = "excluded"
        else:
            role = "tuning" if instance == 1 else "evaluation"
        atype = "fuzzing" if family == "fuzzing" else ("masquerade" if masq else "spoofing")
        out.append(Capture("road", name, root / "attacks" / f"{name}.log", "attack",
                           attack_type=atype, family=family, role=role,
                           meta={"instance": instance, "masquerade": masq, **entry}))
    ambient = sorted(p.stem for p in (root / "ambient").glob("*.log"))
    rest = [n for n in ambient if n != ROAD_REFERENCE]
    for name in ambient:
        if name == ROAD_REFERENCE:
            role = "reference"
        else:
            role = "tuning" if rest.index(name) % 2 == 0 else "evaluation"
        out.append(Capture("road", name, root / "ambient" / f"{name}.log", "ambient", role=role))
    return out


def hcrl_catalog(backend: Path = BACKEND) -> list[Capture]:
    root = find_root("hcrl", backend)
    types = {"DoS": "dos", "Fuzzy": "fuzzing", "RPM": "spoofing", "gear": "spoofing"}
    out = [Capture("hcrl", f"{fam}_dataset", root / f"{fam}_dataset.csv", "attack",
                   attack_type=atype, family=fam, role="split")
           for fam, atype in types.items()]
    out.append(Capture("hcrl", "normal_run_data",
                       root / "normal_run_data" / "normal_run_data.txt", "ambient", role="split"))
    return out


def catalog(dataset: str, backend: Path = BACKEND) -> list[Capture]:
    return road_catalog(backend) if dataset == "road" else hcrl_catalog(backend)
