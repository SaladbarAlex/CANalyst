"""Verify saved explanation experiments and write a new final summary offline."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile

from app import stats
from app.cache import sha256
from app.datasets import ctt_capture_name, find_root
from app.llm import SYSTEM_PROMPTS, parse_reply
from scripts.benchmark_models import atomic_write, fingerprint, summarize
from scripts.claim_review import LABELS
from scripts.compare_models import compare as compare_october
from scripts.freeze_alerts import cap_false_alarms
from scripts.revalidate_identifiers import annotate
from scripts.score_explanations import compare, read_jsonl, score_run

BACKEND = Path(__file__).resolve().parents[1]
OUT = BACKEND / "out"
FINAL = OUT / "final_2026-11-22"
BASELINE_COMMIT = "11dc0abc3ff2676aece7ff2d4b7a78a00ea1936c"
REPLICATION_COMMIT = "bf94d58a544c5068a4747f42c251394eb6474b78"
MODELS = ("gemma-4-31b", "glm-5.3", "qwen3.6-27b-fp8")
TARGET_FIELDS = ("capture", "alert_id", "start", "end", "true_type")
MISSING_TARGETS = {
    ("midterm100", "glm-5.3_v2-dosv1_alert"): ["A0093"],
    ("tue", "glm-5.3_v2-dosv1_alert"): ["A0028"],
}
EXTRA_CORPORA = {
    "ctt": {
        "name": "DTU can-train-and-test v2",
        "source_revision": "048c393b935bcdabc8799ca67845a971e0b05836",
        "scope": "Four vehicles and per-vehicle benign references. Attack captures come from the "
                 "publisher's known-vehicle test splits. Only the saved subset is evaluated.",
    },
    "tue": {
        "name": "TU Eindhoven CAN v2",
        "source_revision": "12f21b8f7c574ac51efd821d3b58fee62bc5e217",
        "scope": "Two cars with per-vehicle training references. The attack files are offline edits "
                 "of the benign testing log. Diagnostics are mapped to fuzzing. The prototype "
                 "and deletion-only suspension file are outside the scored scope.",
    },
}


def load(path):
    return json.loads(path.read_text())


def source(path):
    return {"path": str(path.relative_to(BACKEND)), "sha256": sha256(path)}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def nullable_intervals(value):
    """Use JSON null for undefined interval bounds in zero-denominator scores."""
    if isinstance(value, dict):
        return {k: nullable_intervals(v) for k, v in value.items()}
    if isinstance(value, list):
        return [nullable_intervals(item) for item in value]
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def october_results(midterm_alerts):
    results = {}
    for dataset in ("hcrl", "road"):
        corpus_file = OUT / "frozen_2026-10-30_v4" / f"{dataset}.json"
        corpus = load(corpus_file)
        target_keys = {
            tuple(row[key] for key in TARGET_FIELDS)
            for row in midterm_alerts if row["dataset"] == dataset
        }
        corpus_keys = {tuple(row[key] for key in TARGET_FIELDS) for row in corpus["alerts"]}
        require(corpus_keys == target_keys, f"October and November midterm targets differ for {dataset}")
        paths = {
            "control": OUT / "explanations_v4_2026-10-30_control_v5" / dataset / "explanations_mock.json",
            "glm": OUT / "explanations_v4_2026-10-30_glm_low" / dataset / "explanations_rcd.json",
            "qwen": OUT / "explanations_expansion_2026-10-30_qwen3-30b-a3b-instruct-fp8"
            / dataset / "explanations_rcd.json",
        }
        runs = {name: load(path) for name, path in paths.items()}
        comparison_files = {
            "glm": OUT / "comparisons_v4_2026-10-30_control_v5" / f"{dataset}.json",
            "qwen": FINAL / f"qwen_v4_{dataset}.json",
        }
        comparisons = {}
        for model, path in comparison_files.items():
            saved = load(path)["comparisons"][0]
            rescored = compare_october(runs["control"], runs[model])
            require(all(saved.get(key) == value for key, value in rescored.items()),
                    f"Saved comparison differs from scores in {path}")
            require(saved["source_sha256"] == {"control": sha256(paths["control"]), "model": sha256(paths[model])},
                    f"Source hashes differ in {path}")
            comparisons[model] = {"source": source(path), "paired_attack_outcomes": rescored["paired_attack_outcomes"]}
        data = {}
        for name, run in runs.items():
            annotations = annotate(run, corpus)
            scores = summarize(run["alerts"])
            scores["successful_alerts_per_second"] = scores["successful_responses"] / run["wall_seconds"]
            require(run["summary"] == scores, f"Saved run scores differ for {dataset}/{name}")
            if name == "glm":
                prior = load(OUT / "validation_2026-10-30_v4" / f"{dataset}_glm.json")
                require(prior["summary"] == annotations["summary"] and prior["alerts"] == annotations["alerts"],
                        f"GLM identifier warnings differ for {dataset}")
            data[name] = {
                "source": source(paths[name]),
                "settings": {k: run[k] for k in (
                    "model", "prompt_version", "temperature", "max_tokens", "reasoning_effort", "status"
                )},
                "manifest": run["manifest"],
                "results": scores,
                "identifier_validation": annotations["summary"],
            }
        results[dataset] = {
            "frozen_corpus_file": source(corpus_file),
            "canonical_corpus_sha256": fingerprint(corpus),
            "exact_targets_shared_with_november_midterm100": len(corpus_keys),
            "runs": data,
            "paired_comparisons": comparisons,
        }
    return results


def alert_counts(rows):
    attack = sum(row["is_attack"] for row in rows)
    return {"alerts": len(rows), "attack": attack, "false_alarm": len(rows) - attack}


def read_alerts(path):
    rows = read_jsonl(path)
    alerts = {row["id"]: row for row in rows}
    require(len(rows) == len(alerts), f"Duplicate alert IDs in {path}")
    return alerts


def verify_cap(corpus_path, manifest, packet_files, alerts):
    full_path = corpus_path / "alerts_all.jsonl"
    full = read_alerts(full_path)
    cap = manifest["cap"]
    full_packets = {scope: corpus_path / f"packets_{scope}_all.jsonl" for scope in packet_files}
    with tempfile.TemporaryDirectory() as temp:
        scratch = Path(temp)
        for path in (full_path, *full_packets.values()):
            shutil.copyfile(path, scratch / path.name)
        reproduced = cap_false_alarms(scratch, cap["false_alarm_cap_per_capture"], cap["seed"])
        require(reproduced == cap and read_alerts(scratch / "alerts.jsonl") == alerts,
                f"Capped alert sample differs in {corpus_path}")
        for path in packet_files.values():
            require(read_jsonl(scratch / path.name) == read_jsonl(path),
                    f"Capped evidence packets differ in {path}")
    require(alert_counts(full.values()) == manifest["counts"]["by_dataset"][manifest["set"]],
            f"Full alert counts differ in {full_path}")
    return full, {"settings": cap, "alerts": source(full_path),
                  "evidence_packets": {scope: source(path) for scope, path in full_packets.items()}}


def capture_coverage(set_name, inputs, alerts, full_alerts):
    target_captures = Counter(a["capture"] for a in alerts.values())
    attack_captures = Counter(a["capture"] for a in alerts.values() if a["is_attack"])
    detected_captures = Counter(a["capture"] for a in full_alerts.values())
    captures = {}
    for row in inputs:
        path = Path(row["source"])
        name = ctt_capture_name(path) if set_name == "ctt" else f"{path.parent.name}/{path.stem}"
        require(name not in captures, f"Duplicate capture in {set_name}: {name}")
        require(row.get("alerts", 0) == detected_captures.pop(name, 0),
                f"Manifest alert count differs for capture {set_name}/{name}")
        captures[name] = {**row, "target_alerts": target_captures[name], "target_attacks": attack_captures[name]}
    require(not detected_captures, f"Capture manifest lacks alerts in {set_name}: {detected_captures}")
    return captures


def november_results(set_name):
    corpus_path = OUT / "alerts" / set_name
    alerts_path = corpus_path / "alerts.jsonl"
    alerts = read_alerts(alerts_path)
    manifest_path = corpus_path / "manifest.json"
    corpus_manifest = load(manifest_path)
    full_counts = corpus_manifest["counts"]
    counts = {"alerts": len(alerts), "by_dataset": {
        dataset: alert_counts([a for a in alerts.values() if a["dataset"] == dataset])
        for dataset in sorted({a["dataset"] for a in alerts.values()})
    }}
    packet_files = {scope: corpus_path / f"packets_{scope}.jsonl" for scope in ("alert", "window")}
    coverage = {}
    if "cap" in corpus_manifest:
        full_alerts, cap = verify_cap(corpus_path, corpus_manifest, packet_files, alerts)
        require(full_counts["alerts"] == len(full_alerts)
                and corpus_manifest["counts_after_cap"] == alert_counts(alerts.values()),
                f"Manifest counts differ for {set_name}")
        coverage = {**EXTRA_CORPORA[set_name], "full_detector_counts": full_counts, "cap": cap,
                    "captures": capture_coverage(set_name, corpus_manifest["inputs"], alerts, full_alerts)}
    else:
        require(counts == full_counts, f"Manifest alert counts differ for {set_name}")

    evidence = {}
    for scope, path in packet_files.items():
        packets = read_jsonl(path)
        evidence[scope] = {p["id"]: p["evidence"] for p in packets}
        require(len(packets) == len(alerts) and evidence[scope].keys() == alerts.keys(),
                f"Packet and alert IDs differ in {path}")
    root = OUT / "explanations" / set_name
    saved_path = root / "scores.json"
    saved = load(saved_path)
    paths = sorted(root.glob("*/replies.jsonl"))
    require({path.parent.name for path in paths} == saved["runs"].keys(),
            f"Saved run roster differs for {set_name}")
    runs = {}
    subsets = {}
    for path in paths:
        run_name = path.parent.name
        run_manifest = path.parent / "run.json"
        manifest = load(run_manifest)
        replies = read_jsonl(path)
        ids = {reply["id"] for reply in replies}
        require(len(ids) == len(replies) and ids <= alerts.keys(),
                f"Duplicate or unexpected reply IDs in {path}")
        require(manifest["set"] == set_name and manifest["run"] == run_name and manifest["strict"]
                and manifest["fallbacks"] == 0, f"Run manifest identity differs in {run_manifest}")
        if manifest["prompt_version"]:
            actual = hashlib.sha256(SYSTEM_PROMPTS[manifest["prompt_version"]].encode()).hexdigest()
            require(actual == manifest["prompt_sha256"], f"Prompt identity differs in {run_manifest}")
        legacy_empty_claim_ids = []
        for reply in replies:
            if not reply["error"]:
                packet = evidence[manifest["scope"]][reply["id"]]
                if verify_reply(reply, packet, manifest, path):
                    legacy_empty_claim_ids.append(reply["id"])
        scores = score_run(alerts, replies)
        recorded_scores = {k: v for k, v in scores.items() if k != "correct_by_id"}
        require(nullable_intervals(recorded_scores) == nullable_intervals(saved["runs"][run_name]),
                f"Saved scores differ for {set_name}/{run_name}")
        require(scores["alerts"] == manifest["alerts"] and scores["errors"] == manifest["errors"],
                f"Run manifest counts differ in {run_manifest}")
        missing = sorted(alerts.keys() - ids)
        require(missing == MISSING_TARGETS.get((set_name, run_name), []),
                f"Unexpected missing targets for {set_name}/{run_name}")
        target_scores = score_run(alerts, replies + [{"id": i, "error": "missing reply"} for i in missing])
        subsets[run_name] = (replies, scores)
        runs[run_name] = {
            "replies": source(path),
            "manifest": source(run_manifest),
            "settings": manifest,
            "target_alerts": len(alerts),
            "reply_rows": len(replies),
            "raw_response_rows": sum(bool(reply.get("raw")) for reply in replies),
            "recorded_reply_failures": [reply["id"] for reply in replies if reply["error"]],
            "recorded_reply_errors": {reply["id"]: reply["error"] for reply in replies if reply["error"]},
            "legacy_empty_claim_replies_marked_grounded": legacy_empty_claim_ids,
            "missing_target_ids": missing,
            "scores": recorded_scores,
            "target_scores": {k: target_scores[k] for k in (
                "accuracy", "accuracy_by_type", "false_alarms_called_benign",
            )},
        }

    ablation = {}
    for model in MODELS:
        v2 = f"{model}_v2_alert"
        dos = f"{model}_v2-dosv1_alert"
        before, before_scores = subsets[v2]
        after, after_scores = subsets[dos]
        shared_ids = {r["id"] for r in before} & {r["id"] for r in after}
        shared = {i: alerts[i] for i in sorted(shared_ids)}
        by_prompt = {name: score_run(shared, rows) for name, rows in (("v2", before), ("v2-dosv1", after))}
        paired_attacks = compare(after_scores, before_scores, alerts)
        require(paired_attacks == saved["pairs"][f"{dos} vs {v2}"],
                f"Saved paired scores differ for {set_name}/{model}")
        ablation[model] = {
            "shared_alerts": len(shared),
            "paired_attack_scores_v2_dosv1_vs_v2": paired_attacks,
            "shared_false_alarms_called_benign": {
                name: r["false_alarms_called_benign"] for name, r in by_prompt.items()
            },
            "shared_successful_median_latency_s": {name: r["latency_s"]["median"] for name, r in by_prompt.items()},
        }
    if set_name == "midterm100":
        missing_id = runs["glm-5.3_v2-dosv1_alert"]["missing_target_ids"][0]
        base_replies = subsets["glm-5.3_v2_alert"][0]
        base = next(r for r in base_replies if r["id"] == missing_id)
        road_targets = {i: a for i, a in alerts.items() if a["dataset"] == "road"}
        road_baseline = score_run(road_targets, base_replies)
        known_benign = runs["glm-5.3_v2-dosv1_alert"]["scores"]["false_alarms_called_benign"]["k"]
        ablation["glm-5.3"]["missing_false_alarm_sensitivity"] = {
            "target": alerts[missing_id],
            "baseline_v2_prediction": base["attack_type"],
            "v2_full_road_false_alarms_called_benign": road_baseline["false_alarms_called_benign"],
            "v2_full_road_successful_median_latency_s": road_baseline["latency_s"]["median"],
            "v2_dosv1_if_missing_incorrect_or_failed": {"k": known_benign, "n": road_baseline["false_alarms"]},
            "v2_dosv1_if_missing_correct": {"k": known_benign + 1, "n": road_baseline["false_alarms"]},
            "road_attack_labels_unaffected_by_missing_row": not alerts[missing_id]["is_attack"],
        }
    return nullable_intervals({
        "manifest": source(manifest_path),
        "detector_protocol": {k: corpus_manifest[k] for k in ("detector", "threshold", "window_s", "stride_s")},
        "counts": counts,
        "attack_alerts_by_type": dict(Counter(
            f"{row['dataset']}/{row['true_type']}" for row in alerts.values() if row["is_attack"]
        )),
        "alerts": source(alerts_path),
        "evidence_packets": {scope: source(path) for scope, path in packet_files.items()},
        "saved_scores": source(saved_path),
        "runs": runs,
        "prompt_ablation": ablation,
        **({"coverage": coverage} if coverage else {}),
    })


def verify_reply(reply, packet, manifest, path):
    require(reply["evidence_ids"] == sorted({item["id"] for item in packet["items"]}),
            f"Evidence IDs differ for {reply['id']} in {path}")
    if manifest["explainer"] == "control":
        require(reply["raw"] is None, f"Unexpected hosted response in control run {path}")
        return False
    require(isinstance(reply["raw"], str) and reply["raw"], f"Missing raw response in {path}/{reply['id']}")
    parsed = parse_reply(reply["raw"], packet, manifest["model"])
    fields = ("attack_type", "confidence", "severity", "affected_function", "summary", "claims")
    require(all(reply[field] == getattr(parsed, field) for field in fields),
            f"Parsed response differs for {reply['id']} in {path}")
    # The pre-merge checker marked an empty claim list grounded. Preserve the saved scores.
    legacy_empty_claim = manifest["set"] != "tue" and not parsed.claims and reply["grounded"]
    require(reply["grounded"] == parsed.grounded or legacy_empty_claim,
            f"Citation validation differs for {reply['id']} in {path}")
    return legacy_empty_claim


def overlap():
    november = {row["dataset"]: row for row in load(OUT / "benchmark" / "results.json")["datasets"]}
    prior_hcrl = OUT / "midterm_2026-10-20" / "hcrl_full" / "results.json"
    prior_road = OUT / "midterm_2026-10-20" / "road" / "results.json"
    broad_road = OUT / "detectors_2026-10-30" / "road_broad" / "results.json"
    hcrl_attack = {row["capture"] for row in load(prior_hcrl)["captures"] if row["role"] == "attack_capture"}
    road_attack = {row["capture"] for row in load(prior_road)["captures"] if row["role"] == "attack_capture"}
    road_normal = {row["capture"] for row in load(broad_road)["captures"] if row["role"] != "attack_capture"}
    road_baselines = {Path(row["source"]).stem for row in load(broad_road)["baseline_inputs"]}
    eval_hcrl = set(november["hcrl"]["split"]["evaluation"]["captures"])
    eval_road = set(november["road"]["split"]["evaluation"]["captures"])
    return {
        "interpretation": "November roles are separated within that protocol. "
                          "October development already used these recordings.",
        "prior_hcrl": source(prior_hcrl),
        "prior_road": source(prior_road),
        "prior_broad_road": source(broad_road),
        "november_detection": source(OUT / "benchmark" / "results.json"),
        "november_evaluation_hcrl_attacks_scored_in_full_october": sorted(eval_hcrl & hcrl_attack),
        "november_evaluation_road_attacks_scored_in_full_october": sorted(eval_road & road_attack),
        "november_evaluation_road_ambient_prefixes_scored_in_october": sorted(eval_road & road_normal),
        "november_evaluation_road_ambient_prefixes_used_as_october_reference": sorted(eval_road & road_baselines),
        "ambient_slice_note": "October scored extended_short [0,120) and November heldout uses [120,240). "
                              "The November detector evaluates the full capture.",
    }


def read_review_rows(path, expected_ids):
    with path.open(newline="", encoding="utf-8-sig") as sheet:
        rows = list(csv.DictReader(sheet))
    indexed = {row["claim_id"]: row for row in rows}
    require(len(rows) == len(indexed) and indexed.keys() == expected_ids,
            f"Missing, duplicate, or unexpected claim IDs in {path}")
    return indexed


def human_review():
    root = OUT / "claim_review" / "heldout"
    key_path = root / "key.json"
    sheet_path = root / "sheet.csv"
    saved_path = root / "results.json"
    key = load(key_path)
    ids = {f"C{i:03d}" for i in range(1, 41)}
    require(key["claims"].keys() == ids, "Unexpected claim IDs in the review key")
    sheet = read_review_rows(sheet_path, ids)
    verify_review_sample(key, sheet)
    sheets = {}
    rated = {}
    for rater in ("A", "B"):
        path = root / f"rater_{rater}.csv"
        original = root / "originals" / f"rater_{rater}_original.csv"
        require(sha256(path) == sha256(original), f"Rater {rater} differs from the archived original")
        rated[rater] = read_review_rows(path, ids)
        for claim_id, row in rated[rater].items():
            require(row["label"] in LABELS, f"Invalid label for {claim_id} in {path}")
            require(all(row[k] == sheet[claim_id][k] for k in ("claim", "cited_items")),
                    f"Claim or evidence differs from the frozen sheet for {claim_id} in {path}")
        sheets[rater] = {"source": source(path), "original": source(original), "rows": len(rated[rater]),
                         "labeled": len(rated[rater])}

    a, b = rated["A"], rated["B"]
    agreement = stats.cohen_kappa([a[i]["label"] for i in sorted(ids)], [b[i]["label"] for i in sorted(ids)])
    per_run = {name: Counter() for name in key["runs"]}
    disagreements = []
    for i in sorted(ids):
        run = key["claims"][i]["run"]
        if a[i]["label"] == b[i]["label"]:
            per_run[run][a[i]["label"]] += 1
            continue
        disagreements.append({"claim_id": i, "run": run, "rater_A": a[i]["label"], "rater_B": b[i]["label"],
                              "note_A": a[i]["note"].strip(), "note_B": b[i]["note"].strip()})
    per_run_results = {}
    for name, labels in per_run.items():
        n = sum(labels.values())
        per_run_results[name] = {desc: {"k": labels[code], "n": n,
                                       "ci": list(stats.wilson_interval(labels[code], n))}
                                 for code, desc in LABELS.items()}
    recomputed = {"set": "heldout", "claims": len(ids), "agreed": len(ids) - len(disagreements),
                  "kappa": agreement, "per_run": per_run_results, "disagreements": disagreements}
    require(recomputed == load(saved_path), "Saved human review scores differ from the original ratings")
    return {
        "status": "rated_adjudication_pending" if disagreements else "rated",
        "sheets": sheets,
        "review_protocol": {"set": key["set"], "seed": key["seed"], "claims_per_run": key["per_run"],
                            "unique_alerts": len({record["alert"] for record in key["claims"].values()}),
                            "claim_counts_by_true_type": {
                                run: dict(sorted(Counter(r["true_type"] for r in key["claims"].values()
                                                         if r["run"] == run).items())) for run in key["runs"]
                            }},
        "sources": {"sheet": source(sheet_path), "key": source(key_path), "rubric": source(root / "rubric.md"),
                    "saved_scores": source(saved_path)},
        "results": recomputed,
        "adjudication": {"unresolved": len(disagreements), "adjudicated_support_rates": None,
                         "decisions": {d["claim_id"]: "UNRESOLVED" for d in disagreements}},
    }


def verify_review_sample(key, sheet):
    root = OUT / "alerts" / key["set"]
    alerts = read_alerts(root / "alerts.jsonl")
    packets = {scope: {row["id"]: row["evidence"]["items"]
                       for row in read_jsonl(root / f"packets_{scope}.jsonl")}
               for scope in {record["scope"] for record in key["claims"].values()}}
    replies = {run: {r["id"]: r for r in read_jsonl(OUT / "explanations" / key["set"] / run / "replies.jsonl")}
               for run in key["runs"]}
    for claim_id, record in key["claims"].items():
        alert = record["alert"]
        reply = replies[record["run"]][alert]
        claim = reply["claims"][record["claim_index"]]
        items = {row["id"]: row["text"] for row in packets[record["scope"]][alert]}
        cited = "\n".join(f"[{ref}] {items[ref]}" for ref in claim["cites"] if ref in items)
        require(not reply["error"] and claim["cites"] and claim["text"] == sheet[claim_id]["claim"]
                and cited == sheet[claim_id]["cited_items"] and record["true_type"] == alerts[alert]["true_type"],
                f"Review sample differs from the saved claim or evidence for {claim_id}")


def source_revisions():
    baseline_path = FINAL / "model_results.json"
    baseline = load(baseline_path)

    def references(item):
        if isinstance(item, dict):
            if item.keys() == {"path", "sha256"}:
                yield item
            else:
                for value in item.values():
                    yield from references(value)

    changes = []
    sources = {record["path"]: record for record in references(baseline)}
    for name, frozen in sorted(sources.items()):
        path = BACKEND / name
        current = source(path)
        if current == frozen:
            continue
        old = git_bytes(BASELINE_COMMIT, path)
        require(hashlib.sha256(old).hexdigest() == frozen["sha256"], f"Historical hash differs for {name}")
        if name.startswith("out/explanations/midterm100/"):
            require(git_bytes(REPLICATION_COMMIT, path) == path.read_bytes(),
                    f"Current replication differs from {REPLICATION_COMMIT} for {name}")
        changes.append({"historical": frozen, "current": current})
    require(git_bytes(BASELINE_COMMIT, baseline_path) == baseline_path.read_bytes(),
            "Historical report itself differs from the frozen revision")
    return {"historical_summary": source(baseline_path), "historical_revision": BASELINE_COMMIT,
            "historical_source_hashes_verified": len(sources),
            "midterm100_hcrl_replication_revision": REPLICATION_COMMIT,
            "changed_sources": changes}


def git_bytes(revision, path):
    repo = BACKEND.parent
    name = path.relative_to(repo).as_posix()
    return subprocess.check_output(["git", "show", f"{revision}:{name}"], cwd=repo)


def october_additional_evidence():
    smoke = {}
    for path in sorted(OUT.glob("explanations_expansion_smoke_2026-10-30_*/road/explanations_rcd.json")):
        run = load(path)
        smoke[run["model"]] = {"source": source(path), "limit": run["manifest"]["limit"],
                               "corpus_sha256": run["corpus_sha256"], "results": summarize(run["alerts"])}
    audit_root = OUT / "semantic_audit_2026-10-30"
    numeric = audit_root / "numeric_validation_v4.json"
    semantic = audit_root / "claims_v4_followup.json"
    numeric_summary = load(numeric)
    return {
        "one_alert_smoke_runs": smoke,
        "numeric_packet_validation": {"source": source(numeric), "checks": numeric_summary["total_checks"],
                                      "passed": numeric_summary["passed"]},
        "ai_assisted_semantic_audit": {"source": source(semantic), **load(semantic)["summary"]},
    }


def verify_raw_sources(results):
    for name in EXTRA_CORPORA:
        root = find_root(name)
        for capture in results[name]["coverage"]["captures"].values():
            original = Path(capture["source"])
            relative = Path(*original.parts[-3:]) if name == "ctt" else Path(*original.parts[-2:])
            path = root / relative
            require(sha256(path) == capture["source_sha256"], f"Raw capture hash differs for {path}")


def window_detection_sources():
    provenance = FINAL / "detection" / "verification.json"
    hashes = load(provenance)["result_sha256"]
    files = [source(BACKEND / name) for name in hashes]
    for record in files:
        require(record["sha256"] == hashes[record["path"]], f"Saved detector result hash differs for {record['path']}")
    return {"verification": source(provenance), "verified_results": files}


def markdown_report(report):
    lines = [
        "# Verified saved experiment results",
        "",
        "Evidence snapshot for November 23, 2026 (US Eastern time). The offline verifier rescored saved replies.",
        "[Machine-readable results and source hashes](model_results.json)",
        "",
        "Attack-label accuracy uses frozen attack alerts. False-alarm columns count alerts called benign.",
        "Failures and missing replies count as incorrect on the full target denominators below.",
        "Paired comparisons use alerts with reply records in both runs, including recorded errors.",
        "Citation validity checks whether IDs identify packet items. Human review assesses claim support.",
        "",
        "## Additional datasets",
    ]
    for name, notes in EXTRA_CORPORA.items():
        result = report["november"][name]
        counts = result["counts"]["by_dataset"][name]
        coverage = result["coverage"]
        full = coverage["full_detector_counts"]["by_dataset"][name]
        captures = coverage["captures"]
        baseline = sum(row["role"] == "baseline" for row in captures.values())
        labels = {"dos": "DoS"}
        classes = ", ".join(f"{count} {labels.get(kind, kind)}" for kind, count in sorted(
            (kind.split("/")[-1], count) for kind, count in result["attack_alerts_by_type"].items()
        ))
        lines += [
            "", f"### {notes['name']}", "", notes["scope"], "",
            f"The manifest lists {baseline} reference and {len(captures) - baseline} scored captures.",
            f"The detector emitted {full['alerts']} alerts ({full['attack']} attack alerts and {full['false_alarm']} false alarms).",
            f"The explanation targets include {counts['attack']} attack alerts ({classes}) and "
            f"{counts['false_alarm']} false alarms.",
            "The sampling rule keeps all attack alerts and caps false alarms at three per capture with seed 0.",
            f"[Capture manifest](../alerts/{name}/manifest.json) · [Saved scores](../explanations/{name}/scores.md)",
            "",
            "| Run | Attack labels | False alarms called benign | Reply rows | Failed | Missing |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for run_name, run in result["runs"].items():
            scores = run["target_scores"]
            lines.append(f"| `{run_name}` | {ratio(scores['accuracy']['all'])} | "
                         f"{ratio(scores['false_alarms_called_benign'])} | {run['reply_rows']} | "
                         f"{len(run['recorded_reply_failures'])} | {len(run['missing_target_ids'])} |")

    lines += [
        "",
        "Both datasets used a rule detector with a 0.50 s window, 0.25 s stride, and 0.55 threshold.",
        "All hosted arms used alert packets, temperature 0, a 16,000-token limit, and no fallback.",
        "The experiments measure alert labeling for selected captures with per-vehicle reference traffic.",
        "The old citation checker marked two empty-claim replies as grounded, one each in CTT and midterm100.",
        "The JSON identifies both replies. Their attack-label scores and claim-level citation counts are unaffected.",
        "",
        "For TU Eindhoven, the detector raised zero alerts on both payload-fuzzing files and both benign testing logs.",
        "The 40 fuzzing targets include 20 diagnostic alerts.",
        "All correct attack labels are DoS, with zero correct fuzzing or replay labels in any arm.",
        "GLM's DoS-line run lacks fuzzing alert `A0028`. Its saved score is 2/43 and its full target score is 2/44.",
        "",
        "## Midterm100 DoS-line replication",
        "",
        "The later run added 69 HCRL targets to the earlier ROAD-only DoS-line run.",
        "The corpus has 69 HCRL attack alerts, 20 ROAD attack alerts, and 11 ROAD false alarms.",
        "HCRL gains came from spoofing labels. Qwen lost one DoS and two fuzzing labels.",
        "[Saved scores](../explanations/midterm100/scores.md)",
        "",
        "| Model | HCRL attacks, v2 to DoS-line | ROAD attacks, v2 to DoS-line |",
        "| --- | --- | --- |",
    ]
    midterm = report["november"]["midterm100"]
    for model, ablation in midterm["prompt_ablation"].items():
        groups = ablation["paired_attack_scores_v2_dosv1_vs_v2"]
        cells = [f"{groups[ds]['b_correct']}/{groups[ds]['n']} to {groups[ds]['a_correct']}/{groups[ds]['n']}"
                 for ds in ("hcrl", "road")]
        lines.append(f"| `{model}` | " + " | ".join(cells) + " |")
    review = report["human_claim_review"]
    results = review["results"]
    lines += [
        "",
        "GLM's DoS-line run lacks ROAD false alarm `A0093`. Its paired attack denominator is still 89.",
        "On the 10 ROAD false alarms with replies in both runs, both prompts called six benign.",
        "Across all 11 ROAD false alarms, the full target score is 7/11 for v2 and 6/11 for the DoS-line run.",
        "The missing alert could raise the latter to 7/11 if answered correctly.",
        "",
        "## Human review",
        "",
        f"Each reviewer labeled {results['claims']} claims. The reviewers agreed on {results['agreed']}/{results['claims']} "
        f"({results['kappa']['observed']:.0%}), with Cohen's kappa {results['kappa']['kappa']:.6f}.",
        f"Human adjudication is pending for {review['adjudication']['unresolved']} claims.",
        "The sample covers 27 alerts and four arms, with 10 cited claims per arm.",
        "Each arm includes three DoS, three fuzzing, two spoofing, and two ROAD false-alarm claims.",
        "The denominator below includes only claims on which both raters agreed.",
        "[Saved review and disagreements](../claim_review/heldout/results.md)",
        "",
        "| Arm | Supported | Unsupported | Contradicted | Agreed claims |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for run, counts in results["per_run"].items():
        labels = [str(counts[label]["k"]) for label in LABELS.values()]
        lines.append(f"| `{run}` | " + " | ".join(labels) + f" | {counts['supported']['n']} |")
    revisions = report["source_revisions"]
    lines += [
        "",
        "## Historical evidence and reproduction",
        "",
        "The prior report remains frozen in Git at `" + revisions["historical_revision"] + "`.",
        f"The verifier checked {revisions['historical_source_hashes_verified']} historical source hashes.",
        "The later midterm100 replication updated three reply files, three run manifests, and the aggregate score file.",
        "Two completed rating files replaced the blank copies. The JSON records the old and current hashes for all nine.",
        "[Prior report](../final_2026-11-22/model_results.json) · "
        "[Saved window-level detector verification](../final_2026-11-22/detection/verification.md)",
        "",
        "Run from `backend` with the project environment and a checkout containing the historical revision.",
        "Choose new output paths to preserve prior reports. Add `--verify-raw` to check the 42 DTU and 14 TU Eindhoven capture hashes.",
        "",
        "```sh",
        ".venv/bin/python -m scripts.summarize_final_models \\",
        "  --out out/final_verify/model_results.json --markdown out/final_verify/model_results.md",
        "```",
    ]
    return "\n".join(lines) + "\n"


def ratio(value):
    return f"{value['k']}/{value['n']}" if value["n"] else "n/a"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--verify-raw", action="store_true", help="check installed DTU and TU Eindhoven captures")
    args = parser.parse_args()
    outputs = [path.resolve() for path in (args.out, args.markdown) if path is not None]
    if any(path.exists() for path in outputs) or len(set(outputs)) != len(outputs):
        parser.error("Output already exists. Choose a new path.")
    midterm = read_jsonl(OUT / "alerts" / "midterm100" / "alerts.jsonl")
    report = {
        "source_revisions": source_revisions(),
        "october_v4": october_results(midterm),
        "october_additional_evidence": october_additional_evidence(),
        "november": {name: november_results(name) for name in ("midterm100", "heldout", "ctt", "tue")},
        "prior_development_overlap": overlap(),
        "human_claim_review": human_review(),
        "window_detection": window_detection_sources(),
    }
    if args.verify_raw:
        verify_raw_sources(report["november"])
    if args.markdown:
        markdown = markdown_report(report)
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        with args.markdown.open("x", encoding="utf-8") as output:
            output.write(markdown)
    atomic_write(args.out, report)


if __name__ == "__main__":
    main()
