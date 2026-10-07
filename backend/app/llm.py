"""The explanation layer.

Explainer is the seam between the detector and whatever produces the
analyst-facing text. Three implementations:

  MockExplainer   - deterministic, offline, no API key. Classifies from the
                    evidence with explicit rules and writes the explanation
                    from templates. Use it for development, for tests, and as
                    the "no LLM" control condition in the evaluation.
  ClaudeExplainer - Anthropic API.
  OpenAIExplainer - OpenAI API.

Both real backends send the same evidence packet and the same prompt,
require citations, and fall back to the mock on any error, so the
dashboard never shows an empty panel.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any

from .features import JITTER_COLLAPSE
from .synth import ID_INFO

ATTACK_LABELS = ["dos", "fuzzing", "spoofing", "replay", "masquerade", "benign", "unknown"]

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
- dos: a very high priority ID (often 0x000) floods the bus; total load spikes; other IDs are delayed.
- fuzzing: arbitration IDs absent from the baseline appear; payload entropy jumps.
- spoofing (fabrication): a known ID transmits well above its baseline rate; payload values are implausible.
- replay: valid-looking payloads arrive at the wrong time; rate roughly doubles with normal-looking values.
- masquerade: the real sender is suppressed, so the rate looks normal but timing jitter collapses or shifts.
"""


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

    def to_json(self) -> dict:
        return asdict(self)


def _check_citations(exp: Explanation, evidence: dict) -> Explanation:
    """Drop citations that point at nothing and mark the result ungrounded."""
    valid = {item["id"] for item in evidence.get("items", [])}
    ok = True
    for claim in exp.claims:
        cites = [c for c in claim.get("cites", []) if c in valid]
        if len(cites) != len(claim.get("cites", [])):
            ok = False
        claim["cites"] = cites
        if not cites:
            ok = False
    exp.grounded = ok
    return exp


class Explainer:
    """Interface. Swap implementations without touching the pipeline."""

    name = "base"

    def explain(self, evidence: dict) -> Explanation:  # pragma: no cover - interface
        raise NotImplementedError

    def answer(self, question: str, context: dict) -> str:  # pragma: no cover - interface
        raise NotImplementedError


class MockExplainer(Explainer):
    """Rule-based stand-in. No network, no key, deterministic output."""

    name = "mock"

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
            load_ratio = d["observed"] / max(d["baseline"], 1e-6)

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

        if load_ratio >= 2.0 and (unknown and any(
                i["detail"]["can_id"] in ("0x000", "0x00") for i in unknown)):
            attack, conf, sev = "dos", 0.9, "high"
            function = "Whole bus (arbitration starvation)"
            flood = next(i for i in unknown if i["detail"]["can_id"] in ("0x000", "0x00"))
            claims.append({"text": f"Total bus load reached {load_ratio:.2f}x baseline.",
                           "cites": cite(load_item)})
            claims.append({"text": f"{flood['detail']['can_id']} is the highest priority ID on "
                                   f"CAN and sent {flood['detail']['count']} frames in this window, "
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
            claims.append({"text": f"{tgt['detail']['can_id']} transmitted at "
                                   f"{tgt['detail']['rate_ratio']}x its baseline rate "
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


class _APIExplainer(Explainer):
    """Shared prompt building and response handling for the hosted backends."""

    def _user_prompt(self, evidence: dict) -> str:
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

    def _parse(self, text: str, evidence: dict, model: str) -> Explanation:
        start, end = text.find("{"), text.rfind("}")
        payload = json.loads(text[start:end + 1])
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
            exp.attack_type = "unknown"
        return _check_citations(exp, evidence)


class ClaudeExplainer(_APIExplainer):
    name = "claude"

    def __init__(self, model: str = "claude-sonnet-4-5"):
        self.model = model
        self._fallback = MockExplainer()

    def explain(self, evidence: dict) -> Explanation:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
            msg = client.messages.create(
                model=self.model, max_tokens=1200, system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": self._user_prompt(evidence)}],
            )
            return self._parse(msg.content[0].text, evidence, self.model)
        except Exception as exc:  # network, key, or malformed JSON
            exp = self._fallback.explain(evidence)
            exp.model = f"mock (fallback: {type(exc).__name__})"
            return exp

    def answer(self, question: str, context: dict) -> str:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
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

    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        self._fallback = MockExplainer()

    def explain(self, evidence: dict) -> Explanation:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
            resp = client.chat.completions.create(
                model=self.model,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": SYSTEM_PROMPT},
                          {"role": "user", "content": self._user_prompt(evidence)}],
            )
            return self._parse(resp.choices[0].message.content, evidence, self.model)
        except Exception as exc:
            exp = self._fallback.explain(evidence)
            exp.model = f"mock (fallback: {type(exc).__name__})"
            return exp

    def answer(self, question: str, context: dict) -> str:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
            resp = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content":
                           "Answer using only this context:\n"
                           + json.dumps(context, indent=2)[:60000]
                           + f"\n\nQuestion: {question}"}],
            )
            return resp.choices[0].message.content
        except Exception as exc:
            return f"[falling back to offline explainer: {type(exc).__name__}]\n" + \
                self._fallback.answer(question, context)


def get_explainer(kind: str | None = None) -> Explainer:
    kind = (kind or os.environ.get("EXPLAINER", "mock")).lower()
    if kind in ("claude", "anthropic"):
        return ClaudeExplainer(os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5"))
    if kind in ("openai", "gpt"):
        return OpenAIExplainer(os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    return MockExplainer()
