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

All real backends send the same evidence packet and the same prompt,
require citations, and fall back to the mock on any error, so the
dashboard never shows an empty panel. They run at a fixed temperature
(LLM_TEMPERATURE, default 0) and keep the raw reply and latency of every
call so evaluation runs can be audited without calling the model again.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from .features import JITTER_COLLAPSE

ATTACK_LABELS = ["dos", "fuzzing", "spoofing", "replay", "masquerade", "benign", "unknown"]

PROMPT_VERSION = "can-evidence-v2"
CONTROL_VERSION = "control-v2"

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
- All rates, counts and entropy have scopes: peak-window statistics are not full-alert measurements. A citation resolving does not prove the claim follows from it.
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
                            and i["detail"].get("jitter_ratio") is not None
                            and i["detail"]["jitter_ratio"] < JITTER_COLLAPSE
                            and 0.8 <= (i["detail"].get("rate_ratio") or 1) <= 1.25]

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


class _APIExplainer(Explainer):
    """Shared prompt building and response handling for the hosted backends."""

    def _user_prompt(self, evidence: dict) -> str:
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

    def __init__(self, model: str = "claude-sonnet-4-5", temperature: float = 0.0):
        self.model = model
        self.temperature = temperature
        self._fallback = MockExplainer()
        self.timeout_s = float(os.environ.get("LLM_TIMEOUT_S", "90"))
        self.max_tokens = int(os.environ.get("LLM_MAX_TOKENS", "1800"))

    def explain(self, evidence: dict) -> Explanation:
        started, text = time.perf_counter(), ""
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=self.timeout_s, max_retries=0)
            msg = client.messages.create(
                model=self.model, max_tokens=self.max_tokens, system=SYSTEM_PROMPT,
                temperature=self.temperature,
                messages=[{"role": "user", "content": self._user_prompt(evidence)}],
            )
            text = "\n".join(b.text for b in msg.content if getattr(b, "type", "text") == "text")
            exp = self._parse(text, evidence, self.model)
        except Exception as exc:  # network, key, or malformed JSON
            exp = self._fallback.explain(evidence)
            exp.model = f"mock (fallback: {type(exc).__name__})"
            exp.fallback = True
            exp.error_type = type(exc).__name__
        response = locals().get("resp", locals().get("msg"))
        usage = getattr(response, "usage", None)
        if usage is not None:
            exp.usage = {"input_tokens": int(getattr(usage, "prompt_tokens", getattr(usage, "input_tokens", 0)) or 0),
                         "output_tokens": int(getattr(usage, "completion_tokens", getattr(usage, "output_tokens", 0)) or 0)}
            details = getattr(usage, "completion_tokens_details", None)
            if getattr(details, "reasoning_tokens", None) is not None:
                exp.usage["reasoning_tokens"] = details.reasoning_tokens
        choices = getattr(response, "choices", [])
        exp.finish_reason = getattr(choices[0], "finish_reason", None) if choices else getattr(response, "stop_reason", None)
        exp.response_model = getattr(response, "model", None)
        exp.reasoning_effort = getattr(self, "reasoning_effort", None)
        exp.requested_model = self.model
        exp.raw_response = text
        exp.latency_s = round(time.perf_counter() - started, 3)
        return exp

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

    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.0):
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

    def explain(self, evidence: dict) -> Explanation:
        started, text = time.perf_counter(), ""
        try:
            extra = {"response_format": {"type": "json_object"}} if self.json_mode else {}
            if self.reasoning_effort:
                extra["reasoning_effort"] = self.reasoning_effort
            resp = self._client().chat.completions.create(
                model=self.model, temperature=self.temperature, max_tokens=self.max_tokens,
                messages=[{"role": "system", "content": SYSTEM_PROMPT},
                          {"role": "user", "content": self._user_prompt(evidence)}],
                **extra,
            )
            text = resp.choices[0].message.content or ""
            exp = self._parse(text, evidence, self.model)
        except Exception as exc:
            exp = self._fallback.explain(evidence)
            exp.model = f"mock (fallback: {type(exc).__name__})"
            exp.fallback = True
            exp.error_type = type(exc).__name__
        response = locals().get("resp", locals().get("msg"))
        usage = getattr(response, "usage", None)
        if usage is not None:
            exp.usage = {"input_tokens": int(getattr(usage, "prompt_tokens", getattr(usage, "input_tokens", 0)) or 0),
                         "output_tokens": int(getattr(usage, "completion_tokens", getattr(usage, "output_tokens", 0)) or 0)}
            details = getattr(usage, "completion_tokens_details", None)
            if getattr(details, "reasoning_tokens", None) is not None:
                exp.usage["reasoning_tokens"] = details.reasoning_tokens
        choices = getattr(response, "choices", [])
        exp.finish_reason = getattr(choices[0], "finish_reason", None) if choices else getattr(response, "stop_reason", None)
        exp.response_model = getattr(response, "model", None)
        exp.reasoning_effort = getattr(self, "reasoning_effort", None)
        exp.requested_model = self.model
        exp.raw_response = text
        exp.latency_s = round(time.perf_counter() - started, 3)
        return exp

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
                 base_url: str = "https://llm.rcd.clemson.edu/v1", temperature: float = 0.0):
        super().__init__(model, temperature)
        self.base_url = base_url


def explainer_key(explainer: Explainer) -> str:
    """Include every request setting that can change the cached response."""
    settings = {"model": getattr(explainer, "model", None),
                "base_url": getattr(explainer, "base_url", None),
                "temperature": getattr(explainer, "temperature", None),
                "max_tokens": getattr(explainer, "max_tokens", None),
                "reasoning_effort": getattr(explainer, "reasoning_effort", None),
                "version": CONTROL_VERSION if explainer.name == "mock" else PROMPT_VERSION}
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


def get_explainer(kind: str | None = None) -> Explainer:
    selector = kind or os.environ.get("EXPLAINER", "mock")
    provider, _, model = selector.partition(":")
    provider = provider.lower()
    temperature = float(os.environ.get("LLM_TEMPERATURE", "0"))
    if provider in ("claude", "anthropic"):
        return ClaudeExplainer(model or os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5"), temperature)
    if provider in ("openai", "gpt"):
        return OpenAIExplainer(model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini"), temperature)
    if provider in ("rcd", "clemson"):
        return RCDExplainer(model or os.environ.get("RCD_LLM_MODEL", "glm-5.3"),
                            os.environ.get("RCD_LLM_BASE_URL", "https://llm.rcd.clemson.edu/v1"), temperature)
    if provider != "mock" or model:
        raise ValueError(f"Unknown explainer: {selector}")
    return MockExplainer()
