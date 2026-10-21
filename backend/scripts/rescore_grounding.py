"""Rescore grounding of saved explanations without calling a model again.

Run from backend, after evaluate_midterm.py --explainer has finished:
    .venv/bin/python -u -m scripts.rescore_grounding out/explanations_2026-10-21_glm-5.3/road

Explanations made before evidence packets had an E0 item (alert window,
frame count, detector score) were marked ungrounded whenever a model
restated those numbers, because nothing with an id carried them. This
rebuilds every alert's packet with the frozen detector, checks the alerts
match the saved run, re-parses each saved raw reply against the new packet,
and then credits E0 in two cases only: a citation that names one of the
packet's top-level metadata fields ("window", "frame_count",
"detector_score", "detector_components", or a dotted sub-field such as
"detector_components.timing"), which models used because those
facts had no id, and an uncited claim whose every number matches an E0
value. Every other invalid citation still makes the explanation
ungrounded, and claims with no numbers, or with any number E0 does not
hold, stay uncited. The original file is left as it was; results go to
explanations_<name>_rescored.json beside it.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from app import features, loader
from app.detector import RuleDetector
from app.evidence import build_evidence
from app.llm import Explanation, MockExplainer, _APIExplainer, _check_citations
from scripts.evaluate_midterm import BACKEND, STRIDE_S, THRESHOLD, WINDOW_S, sha256
from scripts.evaluate_midterm import explanation_summary

NUMBER = re.compile(r"-?\d+(?:,\d{3})*(?:\.\d+)?")
NOT_A_VALUE = re.compile(r"0x[0-9A-Fa-f]+|\bE\d+\b")  # CAN ids and citation ids
METADATA_FIELDS = {"window", "frame_count", "detector_score", "detector_components"}


def map_metadata_cites(exp: Explanation) -> int:
    """Replace citations of packet metadata field names with E0. Returns how many claims."""
    mapped = 0
    for claim in exp.claims:
        cites = [str(c) for c in claim.get("cites", [])]
        is_meta = [c.split(".", 1)[0] in METADATA_FIELDS for c in cites]
        if any(is_meta):
            claim["cites"] = list(dict.fromkeys("E0" if m else c for c, m in zip(cites, is_meta)))
            claim["metadata_cite_mapped"] = True
            mapped += 1
    return mapped


def window_values(item: dict) -> list[float]:
    d = item["detail"]
    return [d["window_start"], d["window_end"], d["duration_s"], d["frame_count"],
            d["detector_score"], *d["components"].values()]


def matches(x: float, values: list[float]) -> bool:
    return any(abs(x - v) <= max(0.006, 0.005 * abs(v)) for v in values)


def attribute_to_window(exp: Explanation, evidence: dict) -> int:
    """Cite E0 for uncited claims that only restate E0's numbers. Returns how many."""
    values = window_values(evidence["items"][0])
    attributed = 0
    for claim in exp.claims:
        if claim.get("cites"):
            continue
        numbers = [float(n.replace(",", "")) for n in
                   NUMBER.findall(NOT_A_VALUE.sub(" ", str(claim.get("text", ""))))]
        if numbers and all(matches(x, values) for x in numbers):
            claim["cites"] = ["E0"]
            claim["attributed"] = True
            attributed += 1
    return attributed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="dataset folder holding results.json")
    parser.add_argument("--explainer", default=None,
                        help="explanations_<name>.json to rescore (default: every one present)")
    args = parser.parse_args()
    run = args.run.resolve()
    results = json.loads((run / "results.json").read_text())
    names = [args.explainer] if args.explainer else sorted(
        p.stem.removeprefix("explanations_") for p in run.glob("explanations_*.json")
        if not p.stem.endswith("_rescored"))

    def load(record: dict):
        path = BACKEND / record["selected_input"]
        if sha256(path) != record["selected_input_sha256"]:
            raise ValueError(f"{path} changed since the run")
        return loader.load_auto(str(path))

    baseline = features.learn_baseline(load(results["baseline"]["input"]), float("inf"),
                                       window_s=WINDOW_S)
    detector = RuleDetector(baseline, threshold=THRESHOLD)
    saved = {name: json.loads((run / f"explanations_{name}.json").read_text()) for name in names}
    for payload in saved.values():
        if payload["status"] != "complete":
            raise SystemExit(f"{payload['explainer']} run is still {payload['status']}")
    by_capture: dict[str, dict] = {}
    for capture in results["captures"]:
        wanted = {(r["alert_id"]) for p in saved.values() for r in p["alerts"]
                  if r["capture"] == capture["capture"]}
        if not wanted:
            continue
        print(f"rebuilding {capture['capture']}", flush=True)
        df = load(capture["input"])
        windows = features.extract_windows(df, baseline, window_s=WINDOW_S, stride_s=STRIDE_S)
        windows, alerts = detector.run(windows)
        by_capture[capture["capture"]] = {
            a.alert_id: (a, build_evidence(a, df, windows, baseline)) for a in alerts
            if a.alert_id in wanted}
        del df, windows

    parser_ = _APIExplainer()
    for name, payload in saved.items():
        rescored, attributed, mapped = [], 0, 0
        for record in payload["alerts"]:
            alert, evidence = by_capture[record["capture"]][record["alert_id"]]
            if (round(alert.start, 6), round(alert.end, 6)) != (round(record["start"], 6),
                                                                round(record["end"], 6)):
                raise ValueError(f"{record['capture']} alert {record['alert_id']} moved; "
                                 "the detector is not the one that produced this run")
            old = record["explanation"]
            if old["raw_response"] and not old["model"].startswith("mock"):
                raw = old["raw_response"]
                exp = parser_._parse(raw, evidence, old["model"])
                # _parse already dropped invalid citations; check once, from the raw claims.
                exp.claims = [dict(c) for c in
                              json.loads(raw[raw.find("{"):raw.rfind("}") + 1]).get("claims", [])]
                exp.raw_response, exp.latency_s = raw, old["latency_s"]
            else:  # mock or fallback: deterministic, so explain again
                exp = MockExplainer().explain(evidence)
                exp.model, exp.latency_s = old["model"], old["latency_s"]
            m = map_metadata_cites(exp)
            n = attribute_to_window(exp, evidence)
            mapped += m
            attributed += n
            exp = _check_citations(exp, evidence)
            rescored.append({**record, "explanation": exp.to_json(),
                             "grounded_before_rescore": old["grounded"],
                             "claims_attributed_to_E0": n, "metadata_cites_mapped_to_E0": m})
        out = {
            **{k: v for k, v in payload.items() if k != "alerts"},
            "rescore": {
                "method": "Rebuilt packets with E0 (alert window, frame count, detector score "
                          "and components); re-parsed saved raw replies and checked citations "
                          "once. Citations naming window, frame_count, detector_score or "
                          "detector_components (or a dotted sub-field of one) become E0; an uncited claim cites E0 only if "
                          "every number in it matches an E0 value within 0.5% (at least 0.006). "
                          "Any other invalid citation leaves the explanation ungrounded. "
                          "No model calls.",
                "summary_before": payload["summary"],
                "claims_attributed_to_E0": attributed,
                "metadata_cites_mapped_to_E0": mapped,
            },
            "summary": explanation_summary(rescored),
            "alerts": rescored,
        }
        path = run / f"explanations_{name}_rescored.json"
        path.write_text(json.dumps(out, indent=2, allow_nan=False) + "\n")
        before = payload["summary"]["grounding"]["grounded_rate"]
        after = out["summary"]["grounding"]["grounded_rate"]
        print(f"{name}: grounded {before} -> {after}, {mapped} field-name cites mapped and "
              f"{attributed} uncited claims attributed to E0; "
              f"wrote {path.relative_to(BACKEND)}", flush=True)


if __name__ == "__main__":
    main()
