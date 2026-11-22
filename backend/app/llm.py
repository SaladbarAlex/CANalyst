"""The explanation layer.

Explainer is the seam between the detector and whatever produces the
analyst-facing text. Three implementations:

  MockExplainer   - deterministic, offline, no API key. Classifies from the
                    evidence with explicit rules and writes the explanation
                    from templates. Use it for development, for tests, and as
                    the "no LLM" control condition in the evaluation.
  ClaudeExplainer - Anthropic API.
  OpenAIExplainer - OpenAI API.
  RCDExplainer    - Clemson RCD LLM Service: open-weight models hosted on
                    campus behind an OpenAI-compatible API. Needs the Clemson
                    network (on campus or CUVPN) and an RCD_LLM_API_KEY.

The dashboard uses the corrected prompt and control. Explicit historical
versions retain the frozen benchmark contracts. Hosted backends require
citations and record raw replies and latency. Strict experiment requests
raise errors instead of returning control predictions.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any

from .features import JITTER_COLLAPSE
from .validation import VALIDATION_VERSION, identifier_warnings

ATTACK_LABELS = ["dos", "fuzzing", "spoofing", "replay", "masquerade", "benign", "unknown"]

PROMPT_VERSION = "can-evidence-v3"
CONTROL_VERSION = "control-v5"

SYSTEM_PROMPT = """You are a vehicle network security analyst assistant. You are \
given a structured evidence packet describing one time window of CAN bus traffic \
that an anomaly detector flagged. Classify the window and explain it.

Rules:
1. Use ONLY the evidence provided. Never invent frames, IDs or statistics.
2. Cite the evidence id (for example E2) after every factual claim.
3. If the evidence does not identify the affected vehicle function, say so \
rather than guessing.
4. attack_type must be one of: dos, fuzzing, spoofing, replay, masquerade, benign, unknown.
5. Reply with JSON only, matching this schema:
{"attack_type": str, "confidence": float 0-1, "severity": "low"|"medium"|"high",
 "affected_function": str, "summary": str, "claims": [{"text": str, "cites": [str]}],
 "recommended_action": str}

Reference on CAN attack signatures:
- dos: sustained high-rate injection on a very high priority ID (often 0x000) suggests flooding. Total bus load need not double. Frame counts alone do not prove arbitration starvation or missed deadlines.
- fuzzing: arbitration IDs absent from the baseline appear; payload entropy jumps.
- spoofing (fabrication): a known ID transmits well above its baseline rate, consistent with added frames. Implausible values require signal decoding that may not be available.
- replay: requires evidence of an earlier payload sequence being repeated out of context. Doubled rates, normal-looking payloads, or unchanged entropy alone cannot distinguish replay from fabrication. Without sequence evidence, use spoofing for added frames or unknown when ambiguous.
- masquerade: normal rate with collapsed timing jitter can suggest a replacement sender, but does not prove physical identity or suppression.
- benign: deviations explained by supported normal behavior. If a baseline may omit normal vehicle states, use unknown unless evidence supports benign.
- A pair of identical payloads on a periodic CAN ID is not sequence-replay evidence. These sample frames are all from the alert, with no earlier reference sequence or semantic freshness check.
- raw rate_ratio is observed/baseline. detector_rate_ratio divides by a minimum expected rate to suppress sparse-ID false alarms; never describe it as the raw rate change. IAT unavailable means unmeasured, not zero. Assess jitter collapse only when jitter_eligible is true (at least eight frames).
- All rates, counts and entropy have scopes: peak-window statistics are not full-alert measurements. A citation resolving does not prove the claim follows from it.
"""


SYSTEM_PROMPT_V1 = """You are a vehicle network security analyst assistant. You are \
given a structured evidence packet describing one time window of CAN bus traffic \
that an anomaly detector flagged. Classify the window and explain it.

Rules:
1. Use ONLY the evidence provided. Never invent frames, IDs or statistics.
2. Cite the evidence id (for example E2) after every factual claim.
3. If the evidence does not identify the affected vehicle function, say so \
rather than guessing.
4. attack_type must be one of: dos, fuzzing, spoofing, replay, masquerade, benign, unknown.
5. Reply with JSON only, matching this schema:
{"attack_type": str, "confidence": float 0-1, "severity": "low"|"medium"|"high",
 "affected_function": str, "summary": str, "claims": [{"text": str, "cites": [str]}],
 "recommended_action": str}

Reference on CAN attack signatures:
- dos: a very high priority ID (often 0x000) floods the bus; total load spikes; other IDs are delayed.
- fuzzing: arbitration IDs absent from the baseline appear; payload entropy jumps.
- spoofing (fabrication): a known ID transmits well above its baseline rate; payload values are implausible.
- replay: valid-looking payloads arrive at the wrong time; rate roughly doubles with normal-looking values.
- masquerade: the real sender is suppressed, so the rate looks normal but timing jitter collapses or shifts.
"""

SYSTEM_PROMPT_V2 = """You are a vehicle network security analyst assistant. You are \
given a structured evidence packet describing one alert on a CAN bus: one or more \
consecutive time windows that an anomaly detector flagged, merged into a single span. \
Classify the alert and explain it.

Rules:
1. Use ONLY the evidence provided. Never invent frames, IDs or statistics.
2. Cite the evidence id (for example E2) after every factual claim. Facts about the \
alert as a whole (its span, frame count, detector score) are item E0.
3. Counts and rates describe the whole alert unless an item says "peak window".
4. If the evidence does not identify the affected vehicle function, say so \
rather than guessing.
5. attack_type must be one of: dos, fuzzing, spoofing, replay, masquerade, benign, unknown.
6. Reply with JSON only, matching this schema:
{"attack_type": str, "confidence": float 0-1, "severity": "low"|"medium"|"high",
 "affected_function": str, "summary": str, "claims": [{"text": str, "cites": [str]}],
 "recommended_action": str}

Reference on CAN attack signatures:
- dos: one very high priority ID (often 0x000, which is usually absent from the baseline) \
is sent at a very high rate and accounts for a large share of the frames in the alert. A \
bus has a fixed capacity, so the flood displaces legitimate traffic: the total message \
rate may not rise at all, and many known IDs run below their baseline rates.
- fuzzing: many arbitration IDs absent from the baseline appear, with random payloads.
- spoofing (fabrication): frames are injected for one or a few existing IDs alongside the \
legitimate ones. Those IDs run above their baseline rate, often about double, and carry \
values the legitimate sender is not producing. One ID above its baseline rate is \
fabrication, not replay.
- replay: previously recorded traffic is sent again, so many IDs rise above their baseline \
rates together and the extra payloads repeat values seen earlier.
- masquerade: the legitimate sender is silenced and replaced, so the message rate stays \
near baseline. The evidence is in timing regularity or in payload values, not in counts.
- benign: none of these signatures. The detector also raises false alarms. On attack-free \
tuning captures, alerts whose only elevated detector components were timing, missing_ids \
or payload_entropy were false alarms: IDs pause, change rate and carry new values as the \
vehicle changes state.
"""

_DOS_V1 = "- dos: a very high priority ID (often 0x000) floods the bus; total load spikes; other IDs are delayed.\n"
_DOS_V2 = SYSTEM_PROMPT_V2[SYSTEM_PROMPT_V2.index("- dos:"):SYSTEM_PROMPT_V2.index("- fuzzing:")]

# Ablation: v2 with only the DoS line put back to v1's wording. It tests whether
# v2's "the flood displaces legitimate traffic" sentence pulls spoofing alerts,
# whose known IDs also run off their baseline rates, toward a dos label.
SYSTEM_PROMPT_V2_DOSV1 = SYSTEM_PROMPT_V2.replace(_DOS_V2, _DOS_V1)
assert SYSTEM_PROMPT_V2_DOSV1.count("- dos:") == 1 and _DOS_V1 in SYSTEM_PROMPT_V2_DOSV1

SYSTEM_PROMPTS = {"v1": SYSTEM_PROMPT_V1, "v2": SYSTEM_PROMPT_V2, "v2-dosv1": SYSTEM_PROMPT_V2_DOSV1}
DEFAULT_PROMPT = "v2"


@dataclass
class Explanation:
    attack_type: str
    confidence: float
    severity: str
    affected_function: str
    summary: str
    claims: list[dict[str, Any]] = field(default_factory=list)
    recommended_action: str = ""
    model: str = "mock"
    grounded: bool = True  # every citation resolves to a real evidence id
    raw_response: str = ""  # model text before parsing; empty for the mock
    latency_s: float | None = None  # wall time of the API call, fallbacks included

    requested_model: str | None = None
    fallback: bool = False
    error_type: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    prompt_version: str = PROMPT_VERSION
    finish_reason: str | None = None
    response_model: str | None = None
    reasoning_effort: str | None = None
    validation_version: str = VALIDATION_VERSION
    validation_warnings: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> dict:
        return asdict(self)


def _check_citations(exp: Explanation, evidence: dict) -> Explanation:
    """Drop citations that point at nothing and mark the result ungrounded."""
    valid = {item["id"] for item in evidence.get("items", [])}
    ok = bool(exp.claims)
    for claim in exp.claims:
        cites = [c for c in claim.get("cites", []) if c in valid]
        if len(cites) != len(claim.get("cites", [])):
            ok = False
        claim["cites"] = cites
        if not cites:
            ok = False
    exp.grounded = ok
    exp.validation_version = VALIDATION_VERSION
    exp.validation_warnings = identifier_warnings(exp.to_json(), evidence)
    return exp


class Explainer:
    """Interface. Swap implementations without touching the pipeline."""

    name = "base"

    def explain(self, evidence: dict) -> Explanation:  # pragma: no cover - interface
        raise NotImplementedError

    def answer(self, question: str, context: dict) -> str:  # pragma: no cover - interface
        raise NotImplementedError


CONTROL_RULES = ("v1", "v2")
DEFAULT_CONTROL_RULES = "v2"
FLOOD_SHARE = 0.20          # rules v2: one unseen ID carrying this share of an alert's frames
ALERT_LEVEL = 0.55          # a detector component at or above this raised the alert
ATTACK_COMPONENTS = ("bus_load", "unknown_ids", "rate_inflation")


class _HistoricalMockExplainer(Explainer):
    """Preserve the explicit v1 and v2 rules used by frozen benchmarks."""

    name = "mock"

    def __init__(self, rules: str = DEFAULT_CONTROL_RULES):
        if rules not in CONTROL_RULES:
            raise ValueError(f"rules must be one of {CONTROL_RULES}")
        self.rules = rules

    def explain(self, evidence: dict) -> Explanation:
        comp = evidence.get("detector_components", {})
        items = {i["kind"]: i for i in evidence.get("items", [])}
        by_kind: dict[str, list[dict]] = {}
        for i in evidence.get("items", []):
            by_kind.setdefault(i["kind"], []).append(i)

        load_item = items.get("bus_load")
        load_ratio = 1.0
        if load_item:
            d = load_item["detail"]
            # The flood rule was written against the busiest window. Whole-alert
            # packets report the span average too; keep reading the peak so the
            # rule means the same thing for both packet scopes.
            load_ratio = d.get("observed_peak_window", d["observed"]) / max(d["baseline"], 1e-6)
        span_word = "alert" if evidence.get("scope") == "alert" else "window"

        unknown = by_kind.get("unknown_id", [])
        id_stats = by_kind.get("id_stats", [])
        missing = by_kind.get("missing_id", [])
        inflated = [i for i in id_stats if (i["detail"].get("rate_ratio") or 0) >= 1.5]
        jitter_collapsed = [i for i in id_stats
                            if (i["detail"].get("count") or 0) >= 8
                            and (i["detail"].get("jitter_ratio") or 1) < JITTER_COLLAPSE
                            and 0.8 <= (i["detail"].get("rate_ratio") or 1) <= 1.25]

        claims: list[dict] = []
        cite = lambda item: [item["id"]] if item else []

        # Rules v2 only. The share of the alert's frames carried by the busiest
        # unseen ID, and whether any component that marks attacks raised the alert.
        mix_item = items.get("traffic_mix")
        total_frames = max(int(evidence.get("frame_count") or 0), 1)
        flood = max(unknown, key=lambda i: i["detail"].get("count") or 0, default=None)
        flood_share = (flood["detail"].get("count") or 0) / total_frames if flood else 0.0
        attack_component = any((comp.get(c) or 0) >= ALERT_LEVEL for c in ATTACK_COMPONENTS)

        if self.rules == "v2" and flood is not None and flood_share >= FLOOD_SHARE:
            attack, conf, sev = "dos", 0.9, "high"
            function = "Whole bus (arbitration starvation)"
            claims.append({"text": f"{flood['detail']['can_id']} is absent from the baseline and "
                                   f"sent {flood['detail']['count']} of the {total_frames} frames "
                                   f"in this {span_word} ({flood_share:.0%}).",
                           "cites": cite(flood) + cite(items.get("alert"))})
            if mix_item and mix_item["detail"].get("suppressed_ids"):
                d = mix_item["detail"]
                claims.append({"text": f"{d['suppressed_ids']} of {d['countable_ids']} baseline "
                                       f"IDs ran below {d['suppressed_below']:.0%} of their "
                                       f"baseline rate, so the flood displaced legitimate "
                                       f"traffic.",
                               "cites": cite(mix_item)})
            elif load_item:
                claims.append({"text": f"Total bus load was {load_ratio:.2f}x baseline in the "
                                       f"busiest window.",
                               "cites": cite(load_item)})
            action = ("Treat as a denial of service. Identify the physical node injecting "
                      f"{flood['detail']['can_id']} and check which safety messages missed "
                      "their deadlines.")
        elif self.rules == "v1" and load_ratio >= 2.0 and (unknown and any(
                i["detail"]["can_id"] in ("0x000", "0x00") for i in unknown)):
            attack, conf, sev = "dos", 0.9, "high"
            function = "Whole bus (arbitration starvation)"
            flood = next(i for i in unknown if i["detail"]["can_id"] in ("0x000", "0x00"))
            claims.append({"text": f"Total bus load reached {load_ratio:.2f}x baseline.",
                           "cites": cite(load_item)})
            claims.append({"text": f"{flood['detail']['can_id']} is the highest priority ID on "
                                   f"CAN and sent {flood['detail']['count']} frames in this {span_word}, "
                                   f"so it wins arbitration against every real message.",
                           "cites": cite(flood)})
            action = ("Treat as a denial of service. Identify the physical node injecting 0x000 "
                      "and check whether safety messages missed their deadlines.")
        elif len(unknown) >= 2:
            attack, conf, sev = "fuzzing", 0.82, "medium"
            function = "Multiple, undirected"
            ids = ", ".join(i["detail"]["can_id"] for i in unknown[:4])
            claims.append({"text": f"{len(unknown)} arbitration IDs absent from the baseline "
                                   f"appeared ({ids}), which indicates undirected injection.",
                           "cites": [i["id"] for i in unknown[:4]]})
            if load_item:
                claims.append({"text": f"Bus load rose to {load_ratio:.2f}x baseline.",
                               "cites": cite(load_item)})
            action = ("Capture the full window and check whether any injected ID triggered an "
                      "ECU response. Fuzzing often precedes a targeted attack.")
        elif self.rules == "v2" and not attack_component:
            attack, conf, sev = "benign", 0.6, "low"
            function = "None identified"
            raised = sorted((c for c, v in comp.items() if (v or 0) >= ALERT_LEVEL),
                            key=lambda c: -comp[c])
            claims.append({"text": "The alert was raised by " + (", ".join(raised) or "no component")
                                   + " alone. No unseen ID, per-ID rate inflation or bus-load "
                                   "rise reached the alert level.",
                           "cites": cite(items.get("alert")) or cite(load_item)})
            if mix_item:
                d = mix_item["detail"]
                claims.append({"text": f"No frames came from unseen IDs and {d['suppressed_ids']} "
                                       f"of {d['countable_ids']} baseline IDs ran below "
                                       f"{d['suppressed_below']:.0%} of their baseline rate, "
                                       f"which a change of vehicle state also produces.",
                               "cites": cite(mix_item)})
            action = ("Likely a false alarm from a vehicle state the baseline does not cover. "
                      "Check the IDs listed and add this driving state to the reference.")
        elif jitter_collapsed and not inflated:
            attack, conf, sev = "masquerade", 0.66, "high"
            tgt = jitter_collapsed[0]
            function = tgt["detail"].get("function") or "unknown"
            claims.append({"text": f"{tgt['detail']['can_id']} keeps a normal message rate but its "
                                   f"timing jitter collapsed to {tgt['detail']['jitter_ratio']}x "
                                   f"the quietest baseline window, which is what a different "
                                   f"physical sender looks like.",
                           "cites": cite(tgt)})
            if missing:
                claims.append({"text": f"{missing[0]['detail']['can_id']} stopped transmitting, "
                                       f"consistent with the real ECU being suppressed.",
                               "cites": cite(missing[0])})
            action = ("Confirm with clock-skew fingerprinting (CIDS-style). Rate-based detection "
                      "will not catch this class of attack.")
        elif len(inflated) >= 3:
            attack, conf, sev = "replay", 0.6, "medium"
            function = "Multiple ECUs (bus-wide duplication)"
            ids = ", ".join(i["detail"]["can_id"] for i in inflated[:4])
            claims.append({"text": f"{len(inflated)} known IDs are simultaneously above their "
                                   f"baseline rate ({ids}), so whole frames are being duplicated "
                                   f"rather than one signal targeted.",
                           "cites": [i["id"] for i in inflated[:4]]})
            claims.append({"text": "Payload entropy stays near baseline, which fits previously "
                                   "valid frames being resent.",
                           "cites": cite(inflated[0])})
            action = ("Compare payloads against traffic from earlier in the capture to confirm a "
                      "replay, and check whether any ECU acted on the stale values.")
        elif inflated:
            attack, conf, sev = "spoofing", 0.84, "high"
            tgt = inflated[0]
            function = tgt["detail"].get("function") or "unknown"
            # Quote the plain ratio next to the plain rates. The detector's ratio
            # floors the expected count for slow IDs, so beside the raw rates it
            # reads as an arithmetic error (12.8 versus 1.0 msg/s is not 5.3x).
            shown = tgt["detail"].get("rate_ratio_plain") or tgt["detail"]["rate_ratio"]
            claims.append({"text": f"{tgt['detail']['can_id']} transmitted at "
                                   f"{shown}x its baseline rate "
                                   f"({tgt['detail']['rate']} versus "
                                   f"{tgt['detail']['baseline_rate']} msg/s), so frames are being "
                                   f"added alongside the legitimate ones.",
                           "cites": cite(tgt)})
            if tgt["detail"].get("entropy_delta", 0) != 0:
                claims.append({"text": f"Payload entropy for that ID moved "
                                       f"{tgt['detail']['entropy_delta']:+.2f} bits against baseline.",
                               "cites": cite(tgt)})
            action = (f"Check what {function} displays or actuates on this vehicle and whether the "
                      f"spoofed values were acted upon.")
        elif missing:
            attack, conf, sev = "unknown", 0.45, "medium"
            function = missing[0]["detail"].get("function") or "unknown"
            claims.append({"text": f"{missing[0]['detail']['can_id']} stopped transmitting while "
                                   f"the rest of the bus looked normal.",
                           "cites": cite(missing[0])})
            action = ("Could be suppression, a bus-off attack, or an ECU fault. Check for error "
                      f"frames around this {span_word}.")
        else:
            attack, conf, sev = "unknown", 0.35, "low"
            function = "Indeterminate"
            claims.append({"text": "Deviations are present but no single signature dominates.",
                           "cites": cite(load_item)})
            action = "Widen the window and compare against a longer benign baseline."

        top = ", ".join(evidence.get("ids_involved", [])[:3])
        summary = (f"{attack.upper()} on {function}. {span_word.capitalize()} "
                   f"{evidence['window_start']:.2f}s to {evidence['window_end']:.2f}s, "
                   f"{evidence['frame_count']} frames, IDs of interest {top}. "
                   f"Detector score {evidence['detector_score']:.2f} "
                   f"(strongest component: {max(comp, key=comp.get) if comp else 'n/a'}).")

        exp = Explanation(attack_type=attack, confidence=conf, severity=sev,
                          affected_function=function, summary=summary, claims=claims,
                          recommended_action=action, model=f"mock (rules {self.rules})")
        exp.prompt_version = f"control-{self.rules}"
        return _check_citations(exp, evidence)

    def answer(self, question: str, context: dict) -> str:
        alerts = context.get("alerts", [])
        lines = [f"Question: {question}", ""]
        if not alerts:
            return "No alerts in this analysis, so there is nothing to explain yet."
        lines.append(f"This analysis has {len(alerts)} alert(s):")
        for a in alerts[:6]:
            lines.append(f"- {a['start']:.2f}s to {a['end']:.2f}s, score {a['score']:.2f}, "
                         f"IDs {', '.join(a.get('ids_involved', [])[:3])}")
        lines.append("")
        lines.append("The offline explainer answers from alert metadata only. Configure an API key "
                     "and set EXPLAINER=claude or EXPLAINER=openai for free-form questions.")
        return "\n".join(lines)

class MockExplainer(_HistoricalMockExplainer):
    """Rule-based stand-in. No network, no key, deterministic output."""

    name = "mock"

    def __init__(self, rules: str = CONTROL_VERSION):
        if rules not in (*CONTROL_RULES, CONTROL_VERSION):
            raise ValueError(f"rules must be one of {(*CONTROL_RULES, CONTROL_VERSION)}")
        self.rules = rules

    def explain(self, evidence: dict) -> Explanation:
        if self.rules in CONTROL_RULES:
            return super().explain(evidence)
        comp = evidence.get("detector_components", {})
        items = {i["kind"]: i for i in evidence.get("items", [])}
        by_kind: dict[str, list[dict]] = {}
        for i in evidence.get("items", []):
            by_kind.setdefault(i["kind"], []).append(i)

        load_item = items.get("bus_load")
        load_ratio = 1.0
        if load_item:
            d = load_item["detail"]
            load_ratio = d["observed"] / max(d["baseline"], 1e-6)

        unknown = by_kind.get("unknown_id", [])
        id_stats = by_kind.get("id_stats", [])
        missing = by_kind.get("missing_id", [])
        def detector_ratio(item):
            detail = item["detail"]
            return detail.get("detector_rate_ratio", detail.get("rate_ratio"))

        inflated = [i for i in id_stats if (detector_ratio(i) or 0) >= 1.5]
        jitter_collapsed = [i for i in id_stats
                            if (i["detail"].get("count") or 0) >= 8
                            and i["detail"].get("jitter_ratio") is not None
                            and i["detail"]["jitter_ratio"] < JITTER_COLLAPSE
                            and 0.8 <= (detector_ratio(i) or 1) <= 1.25]

        claims: list[dict] = []
        cite = lambda item: [item["id"]] if item else []

        # A sustained highest-priority injection need not double aggregate
        # bus load. Use its measured per-ID rate and share, not the total alone.
        flood = next((i for i in unknown
                      if i["detail"]["can_id"] in ("0x000", "0x00")
                      and i["detail"].get("alert_mean_rate", i["detail"].get("rate", 0)) >= 100
                      and i["detail"].get("count", 0) >= 8), None)
        if flood is not None:
            attack, conf, sev = "dos", 0.9, "high"
            function = "Bus availability (starvation not measured)"
            claims.append({"text": f"Total bus load reached {load_ratio:.2f}x baseline.",
                           "cites": cite(load_item)})
            claims.append({"text": f"{flood['detail']['can_id']} is the highest priority ID on "
                                   f"CAN and sent {flood['detail']['count']} frames in this window, "
                                   f"consistent with a high-priority flooding attempt; actual deadline misses are unmeasured.",
                           "cites": cite(flood)})
            action = ("Treat as a denial of service. Identify the physical node injecting 0x000 "
                      "and check whether safety messages missed their deadlines.")
        elif len(unknown) >= 2:
            attack, conf, sev = "fuzzing", 0.82, "medium"
            function = "Multiple, undirected"
            ids = ", ".join(i["detail"]["can_id"] for i in unknown[:4])
            claims.append({"text": f"{len(unknown)} arbitration IDs absent from the baseline "
                                   f"appear in the retained evidence ({ids}), consistent with undirected injection "
                                   f"or incomplete normal calibration.",
                           "cites": [i["id"] for i in unknown]})
            if load_item:
                claims.append({"text": f"Bus load was {load_ratio:.2f}x baseline.",
                               "cites": cite(load_item)})
            action = ("Capture the full window and check whether any injected ID triggered an "
                      "ECU response. Fuzzing often precedes a targeted attack.")
        elif jitter_collapsed and not inflated:
            attack, conf, sev = "masquerade", 0.66, "high"
            tgt = jitter_collapsed[0]
            function = tgt["detail"].get("function") or "unknown"
            claims.append({"text": f"{tgt['detail']['can_id']} keeps a normal message rate but its "
                                   f"timing jitter collapsed to {tgt['detail']['jitter_ratio']}x "
                                   f"the quietest baseline window; this suggests a timing change but does not "
                                   f"identify the physical sender.",
                           "cites": cite(tgt)})
            if missing:
                claims.append({"text": f"{missing[0]['detail']['can_id']} was absent in at least one scored window.",
                               "cites": cite(missing[0])})
            action = ("Confirm with clock-skew fingerprinting (CIDS-style). Rate-based detection "
                      "will not catch this class of attack.")
        elif inflated:
            attack, conf, sev = "spoofing", 0.84, "high"
            tgt = inflated[0]
            function = tgt["detail"].get("function") or "unknown"
            claims.append({"text": f"{tgt['detail']['can_id']} transmitted at "
                                   f"{tgt['detail']['rate_ratio']}x its baseline rate "
                                   f"({tgt['detail']['rate']} versus "
                                   f"{tgt['detail']['baseline_rate']} msg/s), consistent with added frames "
                                   f"but also requiring a check for benign operating-state changes.",
                           "cites": cite(tgt)})
            if tgt["detail"].get("entropy_delta", 0) != 0:
                claims.append({"text": f"Payload entropy for that ID moved "
                                       f"{tgt['detail']['entropy_delta']:+.2f} bits against baseline.",
                               "cites": cite(tgt)})
            action = (f"Check what {function} displays or actuates on this vehicle and whether the "
                      f"spoofed values were acted upon.")
        elif missing:
            attack, conf, sev = "unknown", 0.45, "medium"
            function = missing[0]["detail"].get("function") or "unknown"
            claims.append({"text": f"{missing[0]['detail']['can_id']} was absent in at least one scored window.",
                           "cites": cite(missing[0])})
            action = ("Could be suppression, a bus-off attack, or an ECU fault. Check for error "
                      "frames around this window.")
        else:
            attack, conf, sev = "unknown", 0.35, "low"
            function = "Indeterminate"
            claims.append({"text": "Deviations are present but no single signature dominates.",
                           "cites": cite(load_item)})
            action = "Widen the window and compare against a longer benign baseline."

        top = ", ".join(evidence.get("ids_involved", [])[:3])
        summary = (f"{attack.upper()} on {function}. Window "
                   f"{evidence['window_start']:.2f}s to {evidence['window_end']:.2f}s, "
                   f"{evidence['frame_count']} frames, IDs of interest {top}. "
                   f"Detector score {evidence['detector_score']:.2f} "
                   f"(strongest component: {max(comp, key=comp.get) if comp else 'n/a'}).")

        exp = Explanation(attack_type=attack, confidence=conf, severity=sev,
                          affected_function=function, summary=summary, claims=claims,
                          recommended_action=action, model="mock")
        exp.prompt_version = CONTROL_VERSION
        return _check_citations(exp, evidence)

    def answer(self, question: str, context: dict) -> str:
        alerts = context.get("alerts", [])
        lines = [f"Question: {question}", ""]
        if not alerts:
            return "No alerts in this analysis, so there is nothing to explain yet."
        lines.append(f"This analysis has {len(alerts)} alert(s):")
        for a in alerts[:6]:
            lines.append(f"- {a['start']:.2f}s to {a['end']:.2f}s, score {a['score']:.2f}, "
                         f"IDs {', '.join(a.get('ids_involved', [])[:3])}")
        lines.append("")
        lines.append("The offline explainer answers from alert metadata only. Configure an API key "
                     "and set EXPLAINER=claude, openai or rcd for free-form questions.")
        return "\n".join(lines)


def user_prompt(evidence: dict) -> str:
    """The user message for one evidence packet.

    Only measurements go in: no capture name, no ground-truth label, no
    file path. Whole-alert packets carry their alert-level facts as item
    E0, so nothing outside the citable items is needed.
    """
    if evidence.get("scope") == "alert":
        slim = {
            "alert_span_s": [evidence["window_start"], evidence["window_end"]],
            "detector_components": evidence["detector_components"],
            "evidence": [{"id": i["id"], "kind": i["kind"], "text": i["text"]}
                         for i in evidence["items"]],
            "sample_frames": evidence["sample_frames"][:6],
        }
    else:
        slim = {
            "window": [evidence["window_start"], evidence["window_end"]],
            "frame_count": evidence["frame_count"],
            "detector_score": evidence["detector_score"],
            "detector_components": evidence["detector_components"],
            "evidence": [{"id": i["id"], "kind": i["kind"], "text": i["text"]}
                         for i in evidence["items"]],
            "sample_frames": evidence["sample_frames"][:6],
        }
    return "Evidence packet:\n" + json.dumps(slim, indent=2)


def parse_reply(text: str, evidence: dict, model: str) -> Explanation:
    """Keep the historical runner's parsing contract for saved experiments.

    Live explainers use _APIExplainer._parse for strict schema validation.
    """
    start, end = text.find("{"), text.rfind("}")
    payload = json.loads(text[start:end + 1])
    exp = Explanation(
        attack_type=str(payload.get("attack_type", "unknown")).lower().strip(),
        confidence=float(payload.get("confidence", 0.5)),
        severity=str(payload.get("severity", "medium")),
        affected_function=str(payload.get("affected_function", "unknown")),
        summary=str(payload.get("summary", "")),
        claims=[c for c in payload.get("claims", []) if isinstance(c, dict)],
        recommended_action=str(payload.get("recommended_action", "")),
        model=model,
    )
    if exp.attack_type not in ATTACK_LABELS:
        exp.attack_type = "unknown"
    return _check_citations(exp, evidence)


class _APIExplainer(Explainer):
    """Shared prompt building and response handling for the hosted backends."""

    prompt_version = PROMPT_VERSION
    strict = False

    @property
    def system_prompt(self) -> str:
        if self.prompt_version == PROMPT_VERSION:
            return SYSTEM_PROMPT
        return SYSTEM_PROMPTS[self.prompt_version]

    def complete(self, evidence: dict) -> str:
        """Send one packet and return the unparsed model reply."""
        raise NotImplementedError

    def _record_response(self, response) -> None:
        usage = getattr(response, "usage", None)
        tokens = {}
        if usage is not None:
            tokens = {"prompt_tokens": int(getattr(usage, "prompt_tokens", getattr(usage, "input_tokens", 0)) or 0),
                      "completion_tokens": int(getattr(usage, "completion_tokens", getattr(usage, "output_tokens", 0)) or 0)}
            details = getattr(usage, "completion_tokens_details", None)
            if getattr(details, "reasoning_tokens", None) is not None:
                tokens["completion_tokens_details"] = {"reasoning_tokens": details.reasoning_tokens}
        choices = getattr(response, "choices", [])
        self.last_meta = {
            "usage": tokens,
            "finish_reason": getattr(choices[0], "finish_reason", None) if choices else getattr(response, "stop_reason", None),
            "response_model": getattr(response, "model", None),
        }

    def explain(self, evidence: dict) -> Explanation:
        started, text = time.perf_counter(), ""
        self.last_meta = {}
        try:
            text = self.complete(evidence)
            exp = self._parse(text, evidence, self.model)
        except Exception as exc:
            if self.strict:
                raise
            exp = self._fallback.explain(evidence)
            exp.model = f"mock (fallback: {type(exc).__name__})"
            exp.fallback = True
            exp.error_type = type(exc).__name__
        exp.requested_model = self.model
        exp.prompt_version = self.prompt_version
        exp.raw_response = text
        exp.latency_s = round(time.perf_counter() - started, 3)
        meta = getattr(self, "last_meta", {})
        usage = meta.get("usage") or {}
        if usage:
            exp.usage = {"input_tokens": int(usage.get("prompt_tokens", 0) or 0),
                         "output_tokens": int(usage.get("completion_tokens", 0) or 0)}
            details = usage.get("completion_tokens_details") or {}
            if details.get("reasoning_tokens") is not None:
                exp.usage["reasoning_tokens"] = details["reasoning_tokens"]
        exp.finish_reason = meta.get("finish_reason")
        exp.response_model = meta.get("response_model")
        exp.reasoning_effort = getattr(self, "reasoning_effort", None)
        return exp

    def _user_prompt(self, evidence: dict) -> str:
        if self.prompt_version != PROMPT_VERSION:
            return user_prompt(evidence)
        slim = {
            "window": [evidence["window_start"], evidence["window_end"]],
            "frame_count": evidence["frame_count"],
            "detector_score": evidence["detector_score"],
            "detector_components": evidence["detector_components"],
            "evidence": [{"id": i["id"], "kind": i["kind"], "text": i["text"],
                          "detail": i.get("detail", {})} for i in evidence["items"]],
            "sample_frames": evidence["sample_frames"][:6],
        }
        return "Evidence packet:\n" + json.dumps(slim, separators=(",", ":"), allow_nan=False)

    def _parse(self, text: str, evidence: dict, model: str) -> Explanation:
        start, end = text.find("{"), text.rfind("}")
        payload = json.loads(text[start:end + 1])
        if not isinstance(payload, dict):
            raise ValueError("Response must be a JSON object")
        confidence = payload.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("confidence must be finite and between zero and one")
        if payload.get("severity") not in {"low", "medium", "high"}:
            raise ValueError("invalid severity")
        if not isinstance(payload.get("claims"), list) or not payload["claims"]:
            raise ValueError("at least one claim is required")
        for claim in payload["claims"]:
            if not isinstance(claim, dict) or not isinstance(claim.get("text"), str) or not claim["text"].strip() or not isinstance(claim.get("cites"), list) or not all(isinstance(c, str) for c in claim["cites"]):
                raise ValueError("malformed claim")
        exp = Explanation(
            attack_type=str(payload.get("attack_type", "unknown")).lower(),
            confidence=float(payload.get("confidence", 0.5)),
            severity=str(payload.get("severity", "medium")),
            affected_function=str(payload.get("affected_function", "unknown")),
            summary=str(payload.get("summary", "")),
            claims=list(payload.get("claims", [])),
            recommended_action=str(payload.get("recommended_action", "")),
            model=model,
        )
        if exp.attack_type not in ATTACK_LABELS:
            raise ValueError("invalid attack_type")
        return _check_citations(exp, evidence)


class ClaudeExplainer(_APIExplainer):
    name = "claude"

    def __init__(self, model: str = "claude-sonnet-4-5", temperature: float = 0.0,
                 prompt_version: str = PROMPT_VERSION, strict: bool = False):
        if prompt_version != PROMPT_VERSION and prompt_version not in SYSTEM_PROMPTS:
            raise ValueError(f"Unknown prompt: {prompt_version}")
        self.prompt_version = prompt_version
        self.strict = strict
        self.model = model
        self.temperature = temperature
        self._fallback = MockExplainer()
        self.timeout_s = float(os.environ.get("LLM_TIMEOUT_S", "90"))
        self.max_tokens = int(os.environ.get("LLM_MAX_TOKENS", "1800"))

    def complete(self, evidence: dict) -> str:
        self.last_meta = {}
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=self.timeout_s, max_retries=0)
        msg = client.messages.create(
            model=self.model, max_tokens=self.max_tokens, system=self.system_prompt,
            temperature=self.temperature,
            messages=[{"role": "user", "content": self._user_prompt(evidence)}],
        )
        self._record_response(msg)
        return "\n".join(b.text for b in msg.content if getattr(b, "type", "text") == "text")

    def answer(self, question: str, context: dict) -> str:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=self.timeout_s, max_retries=0)
            prompt = ("Answer the analyst's question using only this analysis context. "
                      "Cite alert ids and CAN IDs.\n\nContext:\n"
                      + json.dumps(context, indent=2)[:60000]
                      + f"\n\nQuestion: {question}")
            msg = client.messages.create(model=self.model, max_tokens=800,
                                         messages=[{"role": "user", "content": prompt}])
            return msg.content[0].text
        except Exception as exc:
            return f"[falling back to offline explainer: {type(exc).__name__}]\n" + \
                self._fallback.answer(question, context)


class OpenAIExplainer(_APIExplainer):
    name = "openai"
    base_url: str | None = None
    api_key_env = "OPENAI_API_KEY"
    json_mode = True  # request response_format=json_object

    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.0,
                 prompt_version: str = PROMPT_VERSION, strict: bool = False):
        if prompt_version != PROMPT_VERSION and prompt_version not in SYSTEM_PROMPTS:
            raise ValueError(f"Unknown prompt: {prompt_version}")
        self.prompt_version = prompt_version
        self.strict = strict
        self.model = model
        self.temperature = temperature
        self._fallback = MockExplainer()
        self.timeout_s = float(os.environ.get("LLM_TIMEOUT_S", "90"))
        self.max_tokens = int(os.environ.get("LLM_MAX_TOKENS", "1800"))
        # RCD GLM-5.3 is forced-thinking; its default effort can consume the
        # entire token budget before producing content. Low was live-tested.
        self.reasoning_effort = os.environ.get("LLM_REASONING_EFFORT") or ("low" if model.lower().startswith("glm-5.3") else None)

    def _client(self):
        from openai import OpenAI
        return OpenAI(api_key=os.environ[self.api_key_env], base_url=self.base_url,
                      timeout=self.timeout_s, max_retries=0)

    def complete(self, evidence: dict) -> str:
        self.last_meta = {}
        extra = {"response_format": {"type": "json_object"}} if self.json_mode else {}
        if self.reasoning_effort:
            extra["reasoning_effort"] = self.reasoning_effort
        resp = self._client().chat.completions.create(
            model=self.model, temperature=self.temperature, max_tokens=self.max_tokens,
            messages=[{"role": "system", "content": self.system_prompt},
                      {"role": "user", "content": self._user_prompt(evidence)}],
            **extra,
        )
        self._record_response(resp)
        return resp.choices[0].message.content or ""

    def answer(self, question: str, context: dict) -> str:
        try:
            resp = self._client().chat.completions.create(
                model=self.model, max_tokens=self.max_tokens,
                **({"reasoning_effort": self.reasoning_effort} if self.reasoning_effort else {}),
                messages=[{"role": "user", "content":
                           "Answer using only this context:\n"
                           + json.dumps(context, indent=2)[:60000]
                           + f"\n\nQuestion: {question}"}],
            )
            return resp.choices[0].message.content
        except Exception as exc:
            return f"[falling back to offline explainer: {type(exc).__name__}]\n" + \
                self._fallback.answer(question, context)


class RCDExplainer(OpenAIExplainer):
    """Clemson RCD LLM Service. Same client as OpenAI, pointed at the campus endpoint.

    Model names change over a semester; list the current ones with
    GET {base_url}/models?full=true and check the lifecycle field. glm-5.3
    is the default because RCD lists it as active (stable, at least a week's
    notice before retirement); glm-5.1-fp8 is deprecated as of October 21, 2026.
    """

    name = "rcd"
    api_key_env = "RCD_LLM_API_KEY"
    json_mode = False  # not every hosted model supports it; _parse extracts the JSON

    def __init__(self, model: str = "glm-5.3",
                 base_url: str = "https://llm.rcd.clemson.edu/v1", temperature: float = 0.0,
                 prompt_version: str = PROMPT_VERSION, strict: bool = False):
        super().__init__(model, temperature, prompt_version, strict)
        self.base_url = base_url


class ChatExplainer(_APIExplainer):
    """Any OpenAI-compatible /chat/completions endpoint, with no SDK.

    Configure with CHAT_BASE_URL (for example https://host/v1), CHAT_MODEL
    and, if the service needs one, CHAT_API_KEY. The key is read from the
    environment at call time and is never written to a result file.
    """

    name = "chat"

    def __init__(self, model: str | None = None, base_url: str | None = None,
                 prompt_version: str = DEFAULT_PROMPT, strict: bool = False,
                 timeout_s: float = 900.0, max_tokens: int = 16000):
        if prompt_version != PROMPT_VERSION and prompt_version not in SYSTEM_PROMPTS:
            raise ValueError(f"Unknown prompt: {prompt_version}")
        self.model = model or os.environ.get("CHAT_MODEL", "")
        self.base_url = (base_url or os.environ.get("CHAT_BASE_URL", "")).rstrip("/")
        self.prompt_version = prompt_version
        self.strict = strict
        self.timeout_s = timeout_s
        self.max_tokens = max_tokens
        self.last_meta: dict = {}
        self._fallback = MockExplainer()

    def request_body(self, evidence: dict) -> dict:
        return {
            "model": self.model,
            "temperature": 0,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "system", "content": self.system_prompt},
                         {"role": "user", "content": self._user_prompt(evidence)}],
        }

    def complete(self, evidence: dict) -> str:
        self.last_meta = {}
        if not self.base_url or not self.model:
            raise RuntimeError("Set CHAT_BASE_URL and CHAT_MODEL to use the chat explainer")
        headers = {"Content-Type": "application/json"}
        key = os.environ.get("CHAT_API_KEY")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        req = urllib.request.Request(f"{self.base_url}/chat/completions",
                                     data=json.dumps(self.request_body(evidence)).encode(),
                                     headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            payload = json.loads(resp.read().decode())
        choice = payload["choices"][0]
        message = choice.get("message") or {}
        reasoning = message.get("reasoning") or message.get("reasoning_content") or ""
        self.last_meta = {"response_model": payload.get("model"),
                          "finish_reason": choice.get("finish_reason"),
                          "usage": payload.get("usage"), "reasoning_chars": len(reasoning)}
        content = message.get("content")
        if not content:
            # Reasoning models can spend the whole token budget thinking and
            # return no answer at all. Report that plainly instead of failing
            # later in the parser.
            raise RuntimeError(f"empty reply (finish_reason={choice.get('finish_reason')}, "
                               f"usage={payload.get('usage')}); raise --max-tokens")
        return content

    def answer(self, question: str, context: dict) -> str:
        return self._fallback.answer(question, context)

def timed(fn, *args) -> tuple[Any, float]:
    """Call fn and return (result, seconds)."""
    t0 = time.perf_counter()
    out = fn(*args)
    return out, time.perf_counter() - t0

def explainer_key(explainer: Explainer) -> str:
    """Include every request setting that can change the cached response."""
    settings = {"model": getattr(explainer, "model", None),
                "base_url": getattr(explainer, "base_url", None),
                "temperature": getattr(explainer, "temperature", None),
                "max_tokens": getattr(explainer, "max_tokens", None),
                "reasoning_effort": getattr(explainer, "reasoning_effort", None),
                "validation_version": VALIDATION_VERSION,
                "version": getattr(explainer, "rules", CONTROL_VERSION) if explainer.name == "mock"
                else getattr(explainer, "prompt_version", PROMPT_VERSION)}
    digest = hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:12]
    return f"{explainer.name}:{settings['model'] or 'control'}:{digest}"


def explainer_options() -> dict:
    """Configured options; a key being present does not prove service readiness."""
    env = os.environ.get
    configured = env("RCD_LLM_MODELS", env("RCD_LLM_MODEL", "glm-5.3") + ",gemma-4-31b")
    models = list(dict.fromkeys(m.strip() for m in configured.split(",") if m.strip()))
    options = [{"kind": "mock", "label": "Offline control", "detail": "rule based, instant", "available": True}]
    options.extend({"kind": "rcd:" + model, "label": f"{model} (Clemson RCD)",
                    "detail": "Requires Clemson network; latency measured per request",
                    "available": bool(env("RCD_LLM_API_KEY"))} for model in models)
    options.extend([
        {"kind": "claude", "label": env("CLAUDE_MODEL", "claude-sonnet-4-5"),
         "detail": "Anthropic API", "available": bool(env("ANTHROPIC_API_KEY"))},
        {"kind": "openai", "label": env("OPENAI_MODEL", "gpt-4o-mini"),
         "detail": "OpenAI API", "available": bool(env("OPENAI_API_KEY"))},
    ])
    ex = get_explainer()
    default = f"rcd:{ex.model}" if ex.name == "rcd" else ex.name
    return {"default": default if any(o["kind"] == default and o["available"] for o in options) else "mock",
            "options": options}


def get_explainer(kind: str | None = None, **kwargs) -> Explainer:
    selector = kind or os.environ.get("EXPLAINER", "mock")
    provider, _, model = selector.partition(":")
    provider = provider.lower()
    temperature = float(os.environ.get("LLM_TEMPERATURE", "0"))
    kwargs.setdefault("prompt_version", os.environ.get("PROMPT_VERSION", PROMPT_VERSION))
    if provider in ("chat", "compatible"):
        if model:
            kwargs.setdefault("model", model)
        return ChatExplainer(**kwargs)
    if provider in ("claude", "anthropic"):
        return ClaudeExplainer(model or os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5"), temperature, **kwargs)
    if provider in ("openai", "gpt"):
        return OpenAIExplainer(model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini"), temperature, **kwargs)
    if provider in ("rcd", "clemson"):
        return RCDExplainer(model or os.environ.get("RCD_LLM_MODEL", "glm-5.3"),
                            os.environ.get("RCD_LLM_BASE_URL", "https://llm.rcd.clemson.edu/v1"), temperature, **kwargs)
    if provider != "mock" or model:
        raise ValueError(f"Unknown explainer: {selector}")
    return MockExplainer(rules=kwargs.get("rules", CONTROL_VERSION))
