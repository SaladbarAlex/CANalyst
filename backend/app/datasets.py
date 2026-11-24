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

can-train-and-test (four vehicles; Lampe and Meng, 2023)
    Added on Nov 20, after every prompt, control rule and detector setting
    had been fixed. Nothing is tuned on it. Each vehicle is used only
    through the curated set in which it is the known vehicle, so its
    baseline and its attacks come from the same car:
        Impala     set_01  reference train_01/attack-free-1, false alarms
                           from train_01/attack-free-2; attacks from test_01
                           (DoS, rpm, force-neutral, standstill) and test_03
                           (fuzzing, speed)
        Traverse   set_02  reference attack-free-1, false alarms attack-free-2;
                           test_03 (DoS, rpm, standstill), test_01 (fuzzing, speed)
        Silverado  set_03  reference attack-free-3, false alarms attack-free-4;
                           test_01 (DoS, force-neutral, fuzzing)
        Forester   set_04  reference attack-free-3, false alarms attack-free-4;
                           test_03 (DoS, force-neutral, fuzzing)
    The other captures (double, triple, interval, systematic, accessory,
    and the train_01 attack captures) are not used.

TU Eindhoven automotive CAN v2 (Opel Astra, Renault Clio): see tue_catalog.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

_ROOTS = {
    "hcrl": ["data/raw/hcrl-car-hacking", "data/9) Car-Hacking Dataset", "data/hcrl"],
    "road": ["data/raw/road/road", "data/road/road", "data/road"],
    "ctt": ["data/ctt/can-train-and-test", "data/ctt/cantrainandtest/can-train-and-test"],
    "tue": ["data/raw/tu-eindhoven-can-v2", "data/tu-eindhoven-can-v2"],
}
CTT_VEHICLES = {
    "impala": ("set_01", "attack-free-1", "attack-free-2",
               {"test_01_known_vehicle_known_attack": ["DoS", "rpm", "force-neutral", "standstill"],
                "test_03_known_vehicle_unknown_attack": ["fuzzing", "speed"]}),
    "traverse": ("set_02", "attack-free-1", "attack-free-2",
                 {"test_03_known_vehicle_unknown_attack": ["DoS", "rpm", "standstill"],
                  "test_01_known_vehicle_known_attack": ["fuzzing", "speed"]}),
    "silverado": ("set_03", "attack-free-3", "attack-free-4",
                  {"test_01_known_vehicle_known_attack": ["DoS", "force-neutral", "fuzzing"]}),
    "forester": ("set_04", "attack-free-3", "attack-free-4",
                 {"test_03_known_vehicle_unknown_attack": ["DoS", "force-neutral", "fuzzing"]}),
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
        if dataset == "tue" and (root / "OpelAstra" / "training.log").exists():
            return root
        if dataset == "ctt" and (root / "set_01" / "train_01" / "attack-free-1.csv").exists():
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


def ctt_catalog(backend: Path = BACKEND) -> list[Capture]:
    """Captures are named '<vehicle>/<file stem>', e.g. 'impala/DoS-3'."""
    from .loader import CTT_ATTACK_TYPES, ctt_family
    root = find_root("ctt", backend)
    out: list[Capture] = []
    for vehicle, (set_name, ref, ambient, subsets) in CTT_VEHICLES.items():
        base = root / set_name
        if not (base / "train_01" / f"{ref}.csv").exists():
            continue
        out.append(Capture("ctt", f"{vehicle}/{ref}", base / "train_01" / f"{ref}.csv", "ambient",
                           role="reference", meta={"vehicle": vehicle}))
        out.append(Capture("ctt", f"{vehicle}/{ambient}", base / "train_01" / f"{ambient}.csv",
                           "ambient", role="evaluation", meta={"vehicle": vehicle}))
        for sub, families in subsets.items():
            for path in sorted((base / sub).glob("*.csv")):
                fam = ctt_family(path.stem)
                if fam in families:
                    out.append(Capture("ctt", f"{vehicle}/{path.stem}", path, "attack",
                                       attack_type=CTT_ATTACK_TYPES[fam], family=fam,
                                       role="evaluation",
                                       meta={"vehicle": vehicle, "subset": sub}))
    return out


def ctt_capture_name(path: Path) -> str:
    """'impala/DoS-3' for .../set_01/test_01_.../DoS-3.csv."""
    set_name = path.parent.parent.name
    vehicle = next(v for v, spec in CTT_VEHICLES.items() if spec[0] == set_name)
    return f"{vehicle}/{path.stem}"


TUE_CARS = {"astra": "OpelAstra", "clio": "RenaultClio"}


def tue_catalog(backend: Path = BACKEND) -> list[Capture]:
    """TU Eindhoven automotive CAN v2, the two cars. Captures are named
    '<car>/<file stem>'. Added on Nov 23, after every prompt, rule and
    detector setting was fixed; nothing is tuned on it.

        reference    training.log (the first 70% of the benign drive)
        evaluation   testing.log (the remaining 30%, false alarms) and the
                     attack files, which are edited copies of testing.log
        unused       full_data_capture.log (training + testing), suspension
                     (deletions only), and the Prototype testbed
    """
    from .loader import TUE_ATTACK_TYPES
    root = find_root("tue", backend)
    out: list[Capture] = []
    for car, folder in TUE_CARS.items():
        base = root / folder
        out.append(Capture("tue", f"{car}/training", base / "training.log", "ambient",
                           role="reference", meta={"vehicle": car}))
        out.append(Capture("tue", f"{car}/testing", base / "testing.log", "ambient",
                           role="evaluation", meta={"vehicle": car}))
        for stem, atype in sorted(TUE_ATTACK_TYPES.items()):
            if (base / f"{stem}.log").exists():
                out.append(Capture("tue", f"{car}/{stem}", base / f"{stem}.log", "attack",
                                   attack_type=atype, family=stem, role="evaluation",
                                   meta={"vehicle": car}))
    return out


def catalog(dataset: str, backend: Path = BACKEND) -> list[Capture]:
    if dataset == "tue":
        return tue_catalog(backend)
    if dataset == "ctt":
        return ctt_catalog(backend)
    return road_catalog(backend) if dataset == "road" else hcrl_catalog(backend)
