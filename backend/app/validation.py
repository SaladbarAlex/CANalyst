"""Deterministic identifier membership checks, separate from citation validity.

Membership cannot establish semantic support. An absent identifier can be a
mistake, an unsupported assertion, or a general example requiring review.
"""
from __future__ import annotations

import re

VALIDATION_VERSION = "can-id-membership-v1"
HEX_TOKEN = re.compile(r"(?<![\w])0[xX][0-9a-fA-F]{1,8}(?![0-9a-fA-F])")
# Explicit CAN-ID labels, including comma-separated or parenthesized lists.
# A bare hex value can also be a payload byte or a mask; do not assert that it
# is a CAN identifier without this contextual cue.
ID_CONTEXT = re.compile(
    r"\b(?:CAN[\s-]*)?(?:arbitration[\s-]*)?(?:IDs?|identifiers?)\b"
    r"(?:\s+(?:of interest|involved|include|including))?\s*[:=(]?\s*"
    r"(?:0[xX][0-9a-fA-F]{1,8}\s*[,;/]?\s*(?:(?:and|or)\s+)?)*$",
    re.IGNORECASE,
)
ID_SUFFIX = re.compile(r"^\s*(?:\(\s*)?(?:CAN[\s-]+|arbitration[\s-]+)(?:ID|identifier)\b", re.IGNORECASE)


def evidence_identifiers(evidence: dict) -> set[int]:
    """Allow only IDs actually supplied to the explainer, not the whole log."""
    tokens = list(evidence.get("ids_involved", []))
    frames = list(evidence.get("sample_frames", []))
    for item in evidence.get("items", []):
        detail = item.get("detail", {})
        if detail.get("can_id") is not None:
            tokens.append(detail["can_id"])
        # Alert summaries use "frames" as a count; frame samples use a list.
        if isinstance(detail.get("frames"), list):
            frames.extend(detail["frames"])
    tokens.extend(frame.get("can_id") for frame in frames)
    allowed = set()
    for token in tokens:
        if isinstance(token, str) and HEX_TOKEN.fullmatch(token):
            allowed.add(int(token, 16))
    return allowed


def identifier_warnings(explanation: dict, evidence: dict) -> list[dict]:
    """Report absent explicit CAN IDs and ambiguous hex for review only.

Never mutate model prose, claims, predictions, raw replies, or grounded flags.
Offsets are Unicode code-point offsets into the named explanation field.
"""
    allowed = evidence_identifiers(evidence)
    fields = [(key, explanation.get(key, "")) for key in
              ("summary", "affected_function", "recommended_action")]
    fields.extend((f"claims[{i}].text", claim.get("text", ""))
                  for i, claim in enumerate(explanation.get("claims", [])))
    warnings = []
    for field, text in fields:
        if not isinstance(text, str):
            continue
        for match in HEX_TOKEN.finditer(text):
            value = int(match.group(), 16)
            if value in allowed:
                continue
            explicit = bool(ID_CONTEXT.search(text[max(0, match.start() - 512):match.start()]) or
                            ID_SUFFIX.match(text[match.end():]))
            warnings.append({
                "code": "can_id_not_in_evidence" if explicit else "ambiguous_hex_reference",
                "field": field, "token": match.group(), "canonical_id": f"0x{value:03X}",
                "start": match.start(), "end": match.end(),
                "message": ("This CAN ID is absent from the supplied evidence; verify the reference."
                            if explicit else "This hexadecimal reference is absent from the supplied CAN IDs. It may be a payload value, mask, or general example; review its meaning."),
            })
    return warnings
