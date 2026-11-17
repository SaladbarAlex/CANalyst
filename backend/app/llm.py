"""The explanation layer.

Explainer is the seam between the detector and whatever produces the
analyst-facing text. Three implementations:

  MockExplainer   - deterministic, offline, no API key. Classifies from the
                    evidence with explicit rules and writes the explanation
                    from templates. Use it for development, for tests, and as
                    the "no LLM" control condition in the evaluation.
  ClaudeExplainer - Anthropic API.
  OpenAIExplainer - OpenAI API.
  ChatExplainer   - any OpenAI-compatible chat endpoint (a university
                    research-computing service, a local server), over plain
                    HTTP with no SDK.

The hosted backends send the same evidence packet and the same prompt and
require citations. In the dashboard they fall back to the mock on any
error, so the panel is never empty. An evaluation must not do that: a
silent fallback would score the control under the model's name. Pass
strict=True (the experiment runner does) and errors are raised instead.

Prompts are versioned. v1 is the prompt used through the October 21 run,
kept verbatim so that run stays reproducible. v2 states that a packet
describes a whole alert, separates fabrication from replay by how many IDs
are affected instead of by a doubled rate (which the two share), and
describes a flood by what it does on a real bus (it displaces traffic; the
total rate need not rise) instead of by what the synthetic generator did.

The control's rules are versioned the same way and for the same reason.
Rules v1 are the rules of the October 21 run. Rules v2 change two things,
both decided on the development alerts and the tuning captures and
documented in docs/evaluation-protocol.md: a flood is recognized by one
unseen ID carrying a large share of the alert's frames, and an alert raised
only by components that marked no attack window on the tuning captures is
called benign. Prompt v2 states both facts too, so the model and the
control are given the same information.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any

from .features import JITTER_COLLAPSE
from .synth import ID_INFO

ATTACK_LABELS = ["dos", "fuzzing", "spoofing", "replay", "masquerade", "benign", "unknown"]

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

SYSTEM_PROMPTS = {"v1": SYSTEM_PROMPT_V1, "v2": SYSTEM_PROMPT_V2}
DEFAULT_PROMPT = "v2"
SYSTEM_PROMPT = SYSTEM_PROMPTS[DEFAULT_PROMPT]


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


CONTROL_RULES = ("v1", "v2")
DEFAULT_CONTROL_RULES = "v2"
FLOOD_SHARE = 0.20          # rules v2: one unseen ID carrying this share of an alert's frames
ALERT_LEVEL = 0.55          # a detector component at or above this raised the alert
ATTACK_COMPONENTS = ("bus_load", "unknown_ids", "rate_inflation")


class MockExplainer(Explainer):
    """Rule-based stand-in. No network, no key, deterministic output."""

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
    """Turn a model's reply into an Explanation and check its citations."""
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

    prompt_version = DEFAULT_PROMPT
    strict = False

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPTS[self.prompt_version]

    def _user_prompt(self, evidence: dict) -> str:
        return user_prompt(evidence)

    def _parse(self, text: str, evidence: dict, model: str) -> Explanation:
        return parse_reply(text, evidence, model)

    def complete(self, evidence: dict) -> str:  # pragma: no cover - network
        """Send one packet and return the model's raw reply text."""
        raise NotImplementedError

    def explain(self, evidence: dict) -> Explanation:
        try:
            return self._parse(self.complete(evidence), evidence, self.model)
        except Exception as exc:  # network, key, or malformed JSON
            if self.strict:
                raise
            exp = self._fallback.explain(evidence)
            exp.model = f"mock (fallback: {type(exc).__name__})"
            return exp


class ClaudeExplainer(_APIExplainer):
    name = "claude"

    def __init__(self, model: str = "claude-sonnet-4-5", prompt_version: str = DEFAULT_PROMPT,
                 strict: bool = False):
        self.model = model
        self.prompt_version = prompt_version
        self.strict = strict
        self._fallback = MockExplainer()

    def complete(self, evidence: dict) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        msg = client.messages.create(
            model=self.model, max_tokens=1200, temperature=0, system=self.system_prompt,
            messages=[{"role": "user", "content": self._user_prompt(evidence)}],
        )
        return msg.content[0].text

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

    def __init__(self, model: str = "gpt-4o-mini", prompt_version: str = DEFAULT_PROMPT,
                 strict: bool = False):
        self.model = model
        self.prompt_version = prompt_version
        self.strict = strict
        self._fallback = MockExplainer()

    def complete(self, evidence: dict) -> str:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        resp = client.chat.completions.create(
            model=self.model, temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": self.system_prompt},
                      {"role": "user", "content": self._user_prompt(evidence)}],
        )
        return resp.choices[0].message.content

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
        self.last_meta = {"finish_reason": choice.get("finish_reason"),
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


def get_explainer(kind: str | None = None, **kwargs) -> Explainer:
    kind = (kind or os.environ.get("EXPLAINER", "mock")).lower()
    kwargs.setdefault("prompt_version", os.environ.get("PROMPT_VERSION", DEFAULT_PROMPT))
    if kind in ("claude", "anthropic"):
        return ClaudeExplainer(os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5"), **kwargs)
    if kind in ("openai", "gpt"):
        return OpenAIExplainer(os.environ.get("OPENAI_MODEL", "gpt-4o-mini"), **kwargs)
    if kind in ("chat", "rcd", "compatible"):
        return ChatExplainer(**kwargs)
    return MockExplainer()
