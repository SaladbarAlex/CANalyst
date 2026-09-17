"""Synthetic CAN bus traffic generator with labeled attacks.

Produces traffic that behaves like a real in-vehicle CAN bus:
periodic messages per arbitration ID, payloads built from counters,
physical signals and checksums, plus injected attacks with ground truth.

Output columns match the HCRL Car-Hacking layout so the same loader
reads both synthetic and real logs.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

ATTACK_TYPES = ["dos", "fuzzing", "spoofing", "replay", "masquerade"]


@dataclass
class SignalSpec:
    """One field inside a payload."""

    kind: str  # "counter" | "physical" | "constant" | "checksum"
    start_byte: int
    n_bytes: int = 1
    source: str | None = None  # physical: name of the vehicle state channel
    scale: float = 1.0
    const: int = 0


@dataclass
class MessageSpec:
    can_id: int
    period_ms: float
    dlc: int
    name: str
    function: str
    signals: list[SignalSpec] = field(default_factory=list)
    jitter_frac: float = 0.02  # timing jitter as a fraction of the period


# A small but realistic bus: 12 periodic IDs across powertrain, chassis and body.
BUS: list[MessageSpec] = [
    MessageSpec(0x0A0, 10, 8, "Wheel speeds", "Chassis / ABS", [
        SignalSpec("physical", 0, 2, "speed", 100.0),
        SignalSpec("physical", 2, 2, "speed", 100.0),
        SignalSpec("counter", 6),
        SignalSpec("checksum", 7),
    ]),
    MessageSpec(0x0B4, 10, 8, "Engine RPM / torque", "Powertrain", [
        SignalSpec("physical", 0, 2, "rpm", 4.0),
        SignalSpec("physical", 2, 1, "throttle", 2.55),
        SignalSpec("constant", 3, 1, const=0x10),
        SignalSpec("counter", 6),
        SignalSpec("checksum", 7),
    ]),
    MessageSpec(0x0C8, 20, 8, "Steering angle", "Chassis / steering", [
        SignalSpec("physical", 0, 2, "steering", 10.0),
        SignalSpec("physical", 2, 1, "steering_rate", 5.0),
        SignalSpec("counter", 6),
    ]),
    MessageSpec(0x130, 20, 8, "Brake pressure", "Chassis / brakes", [
        SignalSpec("physical", 0, 2, "brake", 300.0),
        SignalSpec("counter", 6),
        SignalSpec("checksum", 7),
    ]),
    MessageSpec(0x140, 20, 8, "Transmission / gear", "Powertrain", [
        SignalSpec("physical", 0, 1, "gear", 1.0),
        SignalSpec("physical", 1, 2, "rpm", 4.0),
        SignalSpec("counter", 6),
    ]),
    MessageSpec(0x1F1, 50, 8, "Accelerator pedal", "Powertrain", [
        SignalSpec("physical", 0, 1, "throttle", 2.55),
        SignalSpec("counter", 7),
    ]),
    MessageSpec(0x2C0, 50, 8, "Instrument cluster", "Body / cluster", [
        SignalSpec("physical", 0, 2, "speed", 100.0),
        SignalSpec("physical", 2, 2, "rpm", 4.0),
        SignalSpec("counter", 6),
        SignalSpec("checksum", 7),
    ]),
    MessageSpec(0x316, 100, 8, "Coolant temp", "Powertrain", [
        SignalSpec("physical", 0, 1, "coolant", 1.0),
        SignalSpec("constant", 1, 2, const=0x40),
        SignalSpec("counter", 7),
    ]),
    MessageSpec(0x329, 100, 8, "Door / lock status", "Body / doors", [
        SignalSpec("physical", 0, 1, "doors", 1.0),
        SignalSpec("counter", 7),
    ]),
    MessageSpec(0x350, 100, 8, "Lighting status", "Body / lighting", [
        SignalSpec("physical", 0, 1, "lights", 1.0),
        SignalSpec("constant", 1, 1, const=0x01),
        SignalSpec("counter", 7),
    ]),
    MessageSpec(0x430, 200, 8, "HVAC", "Body / climate", [
        SignalSpec("physical", 0, 1, "cabin_temp", 1.0),
        SignalSpec("counter", 7),
    ]),
    MessageSpec(0x545, 200, 8, "Diagnostics heartbeat", "Diagnostics", [
        SignalSpec("constant", 0, 4, const=0x00),
        SignalSpec("counter", 7),
    ]),
]

ID_INFO = {m.can_id: {"name": m.name, "function": m.function, "period_ms": m.period_ms}
           for m in BUS}


def _vehicle_state(t: float, rng: np.random.Generator) -> dict[str, float]:
    """Smoothly varying 'physical' channels for one instant of driving."""
    speed = 45 + 25 * math.sin(t / 17.0) + 5 * math.sin(t / 3.1)
    speed = max(0.0, speed)
    rpm = 800 + speed * 45 + 200 * math.sin(t / 5.0)
    throttle = max(0.0, min(100.0, 25 + 20 * math.sin(t / 4.3)))
    brake = max(0.0, -30 * math.sin(t / 4.3))
    return {
        "speed": speed,
        "rpm": rpm,
        "throttle": throttle,
        "brake": brake,
        "steering": 15 * math.sin(t / 9.0),
        "steering_rate": 5 * math.cos(t / 9.0),
        "gear": float(min(6, max(1, int(speed // 15) + 1))),
        "coolant": 88 + 2 * math.sin(t / 60.0),
        "doors": 0.0,
        "lights": 1.0 if (t % 120) < 60 else 5.0,
        "cabin_temp": 21.0,
    }


def _pack(spec: MessageSpec, t: float, counter: int, state: dict[str, float]) -> list[int]:
    data = [0] * spec.dlc
    for sig in spec.signals:
        if sig.kind == "counter":
            data[sig.start_byte] = counter & 0xFF
        elif sig.kind == "constant":
            for i in range(sig.n_bytes):
                if sig.start_byte + i < spec.dlc:
                    data[sig.start_byte + i] = sig.const
        elif sig.kind == "physical":
            raw = int(abs(state.get(sig.source, 0.0)) * sig.scale)
            raw = min(raw, 256 ** sig.n_bytes - 1)
            for i in range(sig.n_bytes):
                shift = 8 * (sig.n_bytes - 1 - i)
                data[sig.start_byte + i] = (raw >> shift) & 0xFF
    for sig in spec.signals:
        if sig.kind == "checksum":
            data[sig.start_byte] = sum(data[: sig.start_byte]) & 0xFF
    return data


def generate(
    duration_s: float = 120.0,
    seed: int = 7,
    attacks: list[str] | None = None,
    benign_prefix_s: float = 30.0,
) -> pd.DataFrame:
    """Generate a labeled synthetic CAN log.

    The first `benign_prefix_s` seconds are always attack free so the
    detector has a clean stretch to learn a baseline from.
    """
    attacks = attacks if attacks is not None else ["dos", "fuzzing", "spoofing", "masquerade"]
    rng = np.random.default_rng(seed)
    rows: list[tuple[float, int, int, list[int], int, str]] = []

    # 1. Benign periodic traffic.
    for spec in BUS:
        period = spec.period_ms / 1000.0
        counter = 0
        t = rng.uniform(0, period)  # random phase per ECU
        skew = rng.normal(1.0, 0.0005)  # each ECU's clock runs slightly fast or slow
        while t < duration_s:
            state = _vehicle_state(t, rng)
            data = _pack(spec, t, counter, state)
            rows.append((t, spec.can_id, spec.dlc, data, 0, "normal"))
            counter += 1
            jitter = rng.normal(0, period * spec.jitter_frac)
            t += period * skew + jitter

    # 2. Attack intervals, spaced through the post-baseline stretch.
    usable = duration_s - benign_prefix_s
    n = max(1, len(attacks))
    slot = usable / n
    intervals: list[dict] = []
    for i, kind in enumerate(attacks):
        slot_start = benign_prefix_s + i * slot
        length = min(5.0, slot * 0.35)
        start = slot_start + rng.uniform(1.0, max(1.1, slot - length - 1.0))
        intervals.append({"type": kind, "start": round(start, 3), "end": round(start + length, 3)})

    drop_mask_ranges: list[tuple[int, float, float]] = []
    for iv in intervals:
        kind, t0, t1 = iv["type"], iv["start"], iv["end"]
        if kind == "dos":
            t = t0
            while t < t1:
                rows.append((t, 0x000, 8, [0x00] * 8, 1, "dos"))
                t += 0.0003
        elif kind == "fuzzing":
            t = t0
            while t < t1:
                cid = int(rng.integers(0, 0x800))
                dlc = int(rng.integers(1, 9))
                rows.append((t, cid, dlc, [int(b) for b in rng.integers(0, 256, dlc)], 1, "fuzzing"))
                t += float(rng.exponential(0.002))
        elif kind == "spoofing":
            spec = next(m for m in BUS if m.can_id == 0x2C0)  # cluster: fake speed and RPM
            period = spec.period_ms / 1000.0
            t, counter = t0, 0
            while t < t1:
                state = _vehicle_state(t, rng)
                state["speed"], state["rpm"] = 255.0, 8000.0
                rows.append((t, spec.can_id, spec.dlc, _pack(spec, t, counter, state), 1, "spoofing"))
                counter += 1
                t += period
        elif kind == "replay":
            window = [r for r in rows if t0 - 12.0 <= r[0] < t0 - 12.0 + (t1 - t0) and r[4] == 0]
            base = t0 - 12.0
            for ts, cid, dlc, data, _, _ in window:
                rows.append((ts - base + t0, cid, dlc, list(data), 1, "replay"))
        elif kind == "masquerade":
            spec = next(m for m in BUS if m.can_id == 0x0B4)  # silence the engine ECU
            drop_mask_ranges.append((spec.can_id, t0, t1))
            period = spec.period_ms / 1000.0
            t, counter = t0, 0
            while t < t1:
                state = _vehicle_state(t, rng)
                state["rpm"] = 1200.0  # frozen value
                rows.append((t, spec.can_id, spec.dlc, _pack(spec, t, counter, state), 1, "masquerade"))
                counter += 1
                # A different ECU means different clock behavior: near zero jitter.
                t += period + float(rng.normal(0, period * 0.0005))

    # 3. Remove the frames a masquerading attacker suppressed.
    if drop_mask_ranges:
        kept = []
        for r in rows:
            drop = any(r[1] == cid and t0 <= r[0] < t1 and r[5] == "normal"
                       for cid, t0, t1 in drop_mask_ranges)
            if not drop:
                kept.append(r)
        rows = kept

    rows.sort(key=lambda r: r[0])
    df = pd.DataFrame({
        "timestamp": [r[0] for r in rows],
        "can_id": [r[1] for r in rows],
        "dlc": [r[2] for r in rows],
        "data": [r[3] for r in rows],
        "label": [r[4] for r in rows],
        "attack_type": [r[5] for r in rows],
    })
    df.attrs["attack_intervals"] = intervals
    df.attrs["benign_prefix_s"] = benign_prefix_s
    df.attrs["source"] = "synthetic"
    return df


def to_carhacking_csv(df: pd.DataFrame, path: str) -> None:
    """Write the log in the HCRL Car-Hacking column layout."""
    out = pd.DataFrame({
        "Timestamp": df["timestamp"].round(6),
        "CAN ID": [f"{c:04x}" for c in df["can_id"]],
        "DLC": df["dlc"],
    })
    for i in range(8):
        out[f"DATA[{i}]"] = [f"{d[i]:02x}" if i < len(d) else "" for d in df["data"]]
    out["Flag"] = ["T" if lab else "R" for lab in df["label"]]
    out.to_csv(path, index=False)
