"""Verify saved explanation experiments and write a new final summary offline."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

from app.cache import sha256
from app.llm import SYSTEM_PROMPTS
from scripts.benchmark_models import atomic_write, fingerprint, summarize
from scripts.compare_models import compare as compare_october
from scripts.revalidate_identifiers import annotate
from scripts.score_explanations import compare, read_jsonl, score_run

BACKEND = Path(__file__).resolve().parents[1]
OUT = BACKEND / "out"
FINAL = OUT / "final_2026-11-22"
MODELS = ("gemma-4-31b", "glm-5.3", "qwen3.6-27b-fp8")
TARGET_FIELDS = ("capture", "alert_id", "start", "end", "true_type")


def load(path):
    return json.loads(path.read_text())


def source(path):
    return {"path": str(path.relative_to(BACKEND)), "sha256": sha256(path)}


def require(condition, message):
    if not condition:
        raise ValueError(message)


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


def november_results(set_name):
    corpus_path = OUT / "alerts" / set_name
    alerts_path = corpus_path / "alerts.jsonl"
    alerts = {row["id"]: row for row in read_jsonl(alerts_path)}
    manifest_path = corpus_path / "manifest.json"
    counts = load(manifest_path)["counts"]
    require(counts["alerts"] == len(alerts), f"Manifest alert count differs for {set_name}")
    for dataset, expected in counts["by_dataset"].items():
        dataset_alerts = [a for a in alerts.values() if a["dataset"] == dataset]
        attack_count = sum(a["is_attack"] for a in dataset_alerts)
        require(expected == {"alerts": len(dataset_alerts), "attack": attack_count,
                             "false_alarm": len(dataset_alerts) - attack_count},
                f"Manifest alert counts differ for {set_name}/{dataset}")
    packet_files = {scope: corpus_path / f"packets_{scope}.jsonl" for scope in ("alert", "window")}
    packet_ids = {}
    for scope, path in packet_files.items():
        packets = read_jsonl(path)
        packet_ids[scope] = {
            p["id"]: sorted({item["id"] for item in p["evidence"]["items"]}) for p in packets
        }
        require(len(packets) == len(alerts) and packet_ids[scope].keys() == alerts.keys(),
                f"Packet and alert IDs differ in {path}")
    root = OUT / "explanations" / set_name
    saved_path = root / "scores.json"
    saved = load(saved_path)
    runs = {}
    subsets = {}
    for path in sorted(root.glob("*/replies.jsonl")):
        run_name = path.parent.name
        manifest_path = path.parent / "run.json"
        manifest = load(manifest_path)
        replies = read_jsonl(path)
        road_only = set_name == "midterm100" and manifest["prompt_version"] == "v2-dosv1"
        targets = {a["id"]: a for a in alerts.values() if not road_only or a["dataset"] == "road"}
        ids = {reply["id"] for reply in replies}
        require(len(ids) == len(replies) and ids <= targets.keys(),
                f"Duplicate or unexpected reply IDs in {path}")
        if manifest["prompt_version"]:
            actual = hashlib.sha256(SYSTEM_PROMPTS[manifest["prompt_version"]].encode()).hexdigest()
            require(actual == manifest["prompt_sha256"], f"Prompt identity differs in {manifest_path}")
        for reply in replies:
            if not reply["error"]:
                require(reply["evidence_ids"] == packet_ids[manifest["scope"]][reply["id"]],
                        f"Evidence IDs differ for {reply['id']} in {path}")
        scores = score_run(alerts, replies)
        recorded_scores = {k: v for k, v in scores.items() if k != "correct_by_id"}
        require(recorded_scores == saved["runs"][run_name], f"Saved scores differ for {set_name}/{run_name}")
        require(scores["alerts"] == manifest["alerts"] and scores["errors"] == manifest["errors"],
                f"Run manifest counts differ in {manifest_path}")
        missing = sorted(targets.keys() - ids)
        require(missing == (["A0093"] if road_only and manifest["model"] == "glm-5.3" else []),
                f"Unexpected missing targets for {set_name}/{run_name}")
        subsets[run_name] = (replies, scores)
        runs[run_name] = {
            "replies": source(path),
            "manifest": source(manifest_path),
            "settings": manifest,
            "target_alerts": len(targets),
            "recorded_reply_failures": [reply["id"] for reply in replies if reply["error"]],
            "missing_target_ids": missing,
            "scores": recorded_scores,
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
    return {
        "manifest": source(manifest_path),
        "counts": counts,
        "attack_alerts_by_type": dict(Counter(
            f"{row['dataset']}/{row['true_type']}" for row in alerts.values() if row["is_attack"]
        )),
        "alerts": source(alerts_path),
        "evidence_packets": {scope: source(path) for scope, path in packet_files.items()},
        "saved_scores": source(saved_path),
        "runs": runs,
        "prompt_ablation": ablation,
    }


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


def human_review():
    review = {"status": "incomplete", "sheets": {}}
    for rater in ("A", "B"):
        path = OUT / "claim_review" / "heldout" / f"rater_{rater}.csv"
        with path.open(newline="") as sheet:
            rows = list(csv.DictReader(sheet))
        review["sheets"][rater] = {"source": source(path), "rows": len(rows),
                                   "labeled": sum(bool(row["label"].strip()) for row in rows)}
    return review


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Output already exists. Choose a new path.")
    midterm = read_jsonl(OUT / "alerts" / "midterm100" / "alerts.jsonl")
    report = {
        "october_v4": october_results(midterm),
        "october_additional_evidence": october_additional_evidence(),
        "november": {name: november_results(name) for name in ("midterm100", "heldout")},
        "prior_development_overlap": overlap(),
        "human_claim_review": human_review(),
    }
    atomic_write(args.out, report)


if __name__ == "__main__":
    main()
