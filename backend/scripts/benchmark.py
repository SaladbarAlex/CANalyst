"""Held-out detection benchmark: tuning and evaluation never share a capture.

Run from the backend folder, after `python -m scripts.build_cache`:
    python -m scripts.benchmark                 # both datasets
    python -m scripts.benchmark --dataset road

What it reports, on the evaluation split of app/datasets.py only:

    detectors      the rule detector at its fixed 0.55 threshold (v1, six
                   components, as deployed at the midterm), v1 at a threshold
                   chosen on tuning data, v2 (the three components that
                   carried every tuning detection), three single-statistic
                   baselines (ID whitelist, message interval,
                   ID-distribution entropy), the union of the first two, and
                   two learned one-class baselines (IsolationForest [Liu et
                   al. 2008] and a one-class SVM) over the same features
    references     ROAD only: the single reference capture of the midterm,
                   and a reference pooled from every tuning ambient capture
    intervals      95% block-bootstrap intervals; windows overlap, so blocks
                   of consecutive windows are resampled, not single windows
    coverage       ROAD only: false alarms on held-out normal driving as
                   ambient captures are added to the reference

Nothing is fitted on evaluation captures. Thresholds are the smallest value
whose false-positive rate on attack-free tuning windows is at most 1%, and
the one-class models are fitted on the same windows. With a
pooled reference the tuning ambient captures are part of the reference, so
their scores are computed leave-one-capture-out: each is scored against a
reference pooled from the others. Scoring a capture against a reference
that contains it would understate normal variation and set thresholds too
tight.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import cache, datasets, stats, windowstats as ws  # noqa: E402
from app.detector import ALERT_PROFILES  # noqa: E402
from app.features import FEATURE_COLUMNS, Baseline  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
CACHE = BACKEND / "out" / "cache"
WINDOW_S = 0.5
RULE_THRESHOLD = 0.55
TARGET_FPR = 0.01
BLOCK = 20           # windows per bootstrap block: 5 s of traffic at a 0.25 s stride
N_BOOT = 2000
SEED = 0

SCORE_COLUMNS = ["rule", "id_whitelist", "interval", "whitelist_interval", "id_entropy",
                 "iforest", "ocsvm"]
LABELS = {
    "rule@0.55": "Rule detector v1 (six components), fixed 0.55",
    "rule@tuned": "Rule detector v1, tuned threshold",
    "rule_v2@0.55": "Rule detector v2 (three components), fixed 0.55",
    "id_whitelist": "ID whitelist",
    "interval": "Message interval",
    "whitelist_interval": "ID whitelist + message interval",
    "id_entropy": "ID entropy",
    "iforest": "IsolationForest",
    "ocsvm": "One-class SVM",
}


# --------------------------------------------------------------------------
# Loading and splitting
# --------------------------------------------------------------------------

def load_dataset(dataset: str) -> dict[str, tuple[datasets.Capture, cache.Measured]]:
    out = {}
    for cap in datasets.catalog(dataset):
        if cap.role == "excluded":
            continue
        path = CACHE / dataset / f"{cap.name}.npz"
        if not path.exists():
            raise FileNotFoundError(f"{path} missing: run python -m scripts.build_cache")
        out[cap.name] = (cap, cache.load(path))
    return out


def window_roles(cap: datasets.Capture, m: cache.Measured) -> np.ndarray:
    """Role of every window: reference, tuning, evaluation or drop.

    Windows that straddle a split boundary are dropped, so no frame is
    shared between two roles.
    """
    start, end = m.win["start"].to_numpy(), m.win["end"].to_numpy()
    roles = np.full(len(m.win), "drop", dtype=object)
    if cap.dataset == "road":
        roles[:] = cap.role
        return roles
    if cap.kind == "ambient":
        r0, r1 = datasets.HCRL_REFERENCE_S
        t0, t1 = datasets.HCRL_NORMAL_TUNING_S
        roles[end <= r1] = "reference"
        roles[(start >= t0) & (end <= t1)] = "tuning"
        roles[start >= datasets.HCRL_NORMAL_EVAL_START_S] = "evaluation"
        return roles
    # An attack capture is one session of injection bursts followed by an
    # attack-free tail, so it is split at its median non-empty window: the
    # first half of the session is tuning, the rest (and the tail) evaluation.
    mid = float(start[len(start) // 2])
    roles[end <= mid] = "tuning"
    roles[start >= mid] = "evaluation"
    return roles


def references(dataset: str, data: dict) -> dict[str, dict]:
    """Reference configurations: name -> {'stats': {capture: BaselineStats}}."""
    if dataset == "hcrl":
        st = data["normal_run_data"][1].reference["0-120"]
        return {"single": {"parts": {"normal_run_data[0-120)": st}}}
    ref = datasets.ROAD_REFERENCE
    single = {ref: data[ref][1].reference["all"]}
    pooled = dict(single)
    for name, (cap, m) in data.items():
        if cap.kind == "ambient" and cap.role == "tuning":
            pooled[name] = m.reference["all"]
    return {"single": {"parts": single}, "pooled": {"parts": pooled}}


def baseline_from(parts: dict[str, ws.BaselineStats], leave_out: str | None = None) -> Baseline:
    chosen = [st for name, st in parts.items() if name != leave_out]
    return ws.BaselineStats.pool(chosen).to_baseline()


# --------------------------------------------------------------------------
# Scores
# --------------------------------------------------------------------------

def id_entropy(m: cache.Measured) -> np.ndarray:
    """Shannon entropy of the arbitration-ID distribution in each window."""
    c = m.ids["count"].to_numpy(dtype=float)
    widx = m.ids["window"].to_numpy()
    n = np.bincount(widx, weights=c, minlength=len(m.win))
    s = np.bincount(widx, weights=c * np.log2(c), minlength=len(m.win))
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(n > 0, np.log2(n) - s / n, 0.0)


def raw_scores(m: cache.Measured, baseline: Baseline) -> pd.DataFrame:
    """Everything a detector here needs, for one capture against one baseline."""
    wf, _ = ws.apply_baseline(m.win, m.ids, baseline, WINDOW_S)
    sc = ws.rule_scores(wf, RULE_THRESHOLD)
    out = sc[["window", "start", "end", "label", "attack_type", "score"]
             + ws.COMPONENTS + FEATURE_COLUMNS].copy()
    out = out.rename(columns={"score": "rule"})
    out["rule_v2"] = ws.rule_scores(wf, RULE_THRESHOLD, ALERT_PROFILES["v2"])["score"].to_numpy()
    out["id_whitelist"] = wf["n_unknown_ids"].to_numpy(dtype=float)
    out["interval"] = wf["max_rate_ratio"].to_numpy(dtype=float)
    # Either baseline alone misses a whole attack class, so the natural simple
    # detector is their union: any unseen ID, or a known ID above its rate.
    out["whitelist_interval"] = np.where(out["id_whitelist"] > 0, 1e6, out["interval"])
    out["h_ids"] = id_entropy(m)
    return out


def feature_matrix(df: pd.DataFrame) -> np.ndarray:
    X = df[FEATURE_COLUMNS].to_numpy(dtype=float)
    return np.nan_to_num(X, nan=0.0, posinf=1e6, neginf=-1e6)


def fit_normal_models(normal: pd.DataFrame) -> dict:
    """Fit the baselines that need a model of normal windows."""
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import OneClassSVM

    rng = np.random.default_rng(SEED)
    X = feature_matrix(normal)
    mu, sd = float(normal["h_ids"].mean()), float(normal["h_ids"].std(ddof=0))
    forest = IsolationForest(n_estimators=200, random_state=SEED).fit(X)
    sub = X[rng.choice(len(X), size=min(len(X), 6000), replace=False)]
    scaler = StandardScaler().fit(sub)
    svm = OneClassSVM(nu=0.01, gamma="scale").fit(scaler.transform(sub))
    return {"h_mu": mu, "h_sd": max(sd, 1e-9), "forest": forest, "scaler": scaler, "svm": svm,
            "fit_windows": int(len(X)), "svm_fit_windows": int(len(sub))}


def add_model_scores(df: pd.DataFrame, models: dict) -> pd.DataFrame:
    out = df.copy()
    X = feature_matrix(out)
    out["id_entropy"] = np.abs(out["h_ids"].to_numpy() - models["h_mu"]) / models["h_sd"]
    out["iforest"] = -models["forest"].score_samples(X)
    out["ocsvm"] = -models["svm"].score_samples(models["scaler"].transform(X))
    return out


def threshold_at_fpr(normal_scores: np.ndarray, target: float = TARGET_FPR) -> float:
    """Smallest threshold t with mean(score >= t) <= target on normal windows."""
    s = np.sort(np.asarray(normal_scores, dtype=float))
    n = len(s)
    k = int(np.floor(target * n))          # windows allowed above the threshold
    if k >= n:
        return float(s[0])
    cut = s[n - k - 1]                     # the (k+1)-th largest: must fall below t
    return float(np.nextafter(cut, np.inf))


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------

def auc_scores(label: np.ndarray, score: np.ndarray) -> dict:
    from sklearn.metrics import average_precision_score, roc_auc_score
    if label.min() == label.max():
        return {"auroc": None, "auprc": None}
    s = np.nan_to_num(score, nan=0.0, posinf=1e12, neginf=-1e12)
    return {"auroc": float(roc_auc_score(label, s)),
            "auprc": float(average_precision_score(label, s))}


def evaluate(frames: dict[str, pd.DataFrame], caps: dict[str, datasets.Capture],
             column: str, threshold: float) -> dict:
    """Pooled metrics on evaluation windows, with block-bootstrap intervals."""
    blocks, parts = {}, []
    for name, df in frames.items():
        flagged = df[column].to_numpy() >= threshold
        blocks[name] = stats.block_counts(df["label"].to_numpy(), flagged, BLOCK)
        parts.append(df.assign(flagged=flagged, capture=name, kind=caps[name].kind,
                               family=caps[name].family or "",
                               ctype=caps[name].attack_type or "normal"))
    allw = pd.concat(parts, ignore_index=True)
    boot = stats.bootstrap_detection(blocks, n_boot=N_BOOT, seed=SEED, resample_captures=False)
    counts = stats.confusion(allw["label"], allw["flagged"])
    out = {
        "threshold": threshold,
        "windows": int(len(allw)),
        "tp": int(counts[0]), "fp": int(counts[1]), "fn": int(counts[2]), "tn": int(counts[3]),
        **{k: boot[k] for k in ("precision", "recall", "f1", "fpr")},
        **auc_scores(allw["label"].to_numpy(), allw[column].to_numpy()),
    }
    pos = allw[allw["label"] == 1]
    out["recall_by_type"] = {
        t: {"k": int(g["flagged"].sum()), "n": int(len(g)),
            "value": float(g["flagged"].mean()),
            "ci": list(stats.wilson_interval(int(g["flagged"].sum()), len(g)))}
        for t, g in pos.groupby("ctype")}
    out["recall_by_family"] = {
        f"{fam}{'/masquerade' if t == 'masquerade' else ''}":
            {"k": int(g["flagged"].sum()), "n": int(len(g)), "value": float(g["flagged"].mean())}
        for (fam, t), g in pos.groupby(["family", "ctype"])}
    neg = allw[allw["label"] == 0]
    out["fpr_by_source"] = {}
    for kind, g in neg.groupby("kind"):
        key = "ambient captures" if kind == "ambient" else "normal windows inside attack captures"
        out["fpr_by_source"][key] = {"k": int(g["flagged"].sum()), "n": int(len(g)),
                                     "value": float(g["flagged"].mean())}
    out["fpr_by_ambient_capture"] = {
        name: {"k": int(g["flagged"].sum()), "n": int(len(g)), "value": float(g["flagged"].mean())}
        for name, g in neg[neg["kind"] == "ambient"].groupby("capture")}
    return out


# --------------------------------------------------------------------------
# One dataset
# --------------------------------------------------------------------------

def run_dataset(dataset: str) -> dict:
    data = load_dataset(dataset)
    caps = {name: cap for name, (cap, _) in data.items()}
    roles = {name: window_roles(cap, m) for name, (cap, m) in data.items()}
    result = {"dataset": dataset, "references": {}, "split": {}}

    for role in ("reference", "tuning", "evaluation"):
        names = sorted(n for n in data if (roles[n] == role).any())
        result["split"][role] = {
            "captures": names,
            "windows": int(sum((roles[n] == role).sum() for n in names)),
            "attack_windows": int(sum(data[n][1].win["label"].to_numpy()[roles[n] == role].sum()
                                      for n in names)),
        }

    for ref_name, ref in references(dataset, data).items():
        parts = ref["parts"]
        baseline = baseline_from(parts)
        tuning_normal, tuning_all, evaluation = [], {}, {}
        for name, (cap, m) in data.items():
            role = roles[name]
            if (role == "tuning").any():
                # Leave-one-capture-out when the capture is part of the reference.
                bl = baseline_from(parts, leave_out=name) if name in parts and len(parts) > 1 \
                    else baseline
                df = raw_scores(m, bl)[role == "tuning"]
                tuning_all[name] = df
                tuning_normal.append(df[df["label"] == 0])
            if (role == "evaluation").any():
                evaluation[name] = raw_scores(m, baseline)[role == "evaluation"]
        normal = pd.concat(tuning_normal, ignore_index=True)
        models = fit_normal_models(normal)
        normal = add_model_scores(normal, models)
        evaluation = {n: add_model_scores(df, models) for n, df in evaluation.items()}
        tuning_all = {n: add_model_scores(df, models) for n, df in tuning_all.items()}

        thresholds = {c: threshold_at_fpr(normal[c].to_numpy()) for c in SCORE_COLUMNS}
        thresholds["id_whitelist"] = 1.0     # any unknown ID; nothing to tune
        detectors = {"rule@0.55": evaluate(evaluation, caps, "rule", RULE_THRESHOLD),
                     "rule_v2@0.55": evaluate(evaluation, caps, "rule_v2", RULE_THRESHOLD)}
        tuning_scores = {"rule@0.55": evaluate(tuning_all, caps, "rule", RULE_THRESHOLD),
                         "rule_v2@0.55": evaluate(tuning_all, caps, "rule_v2", RULE_THRESHOLD)}
        for col in SCORE_COLUMNS:
            key = "rule@tuned" if col == "rule" else col
            detectors[key] = evaluate(evaluation, caps, col, thresholds[col])
            tuning_scores[key] = evaluate(tuning_all, caps, col, thresholds[col])
        result["references"][ref_name] = {
            "reference_captures": sorted(parts),
            "reference_seconds": round(sum(st.span for st in parts.values()), 1),
            "reference_ids": len(baseline.known_ids),
            "normal_model_windows": models["fit_windows"],
            "threshold_rule": "smallest threshold with FPR <= 1% on attack-free tuning windows",
            "thresholds": thresholds,
            "evaluation": detectors,
            "tuning": {k: {m_: v[m_] for m_ in ("precision", "recall", "f1", "fpr", "windows")}
                       for k, v in tuning_scores.items()},
        }

    if dataset == "road":
        result["coverage"] = coverage_study(data, caps, roles)
    return result


def coverage_study(data: dict, caps: dict, roles: dict) -> list[dict]:
    """False alarms on held-out normal driving as the reference grows.

    Tuning ambient captures are added to the reference one at a time, in
    order of increasing duration, and the rule detector at 0.55 is scored
    on the evaluation split each time.
    """
    ref = datasets.ROAD_REFERENCE
    order = sorted((n for n, c in caps.items() if c.kind == "ambient" and c.role == "tuning"),
                   key=lambda n: data[n][1].info["duration_s"])
    eval_names = [n for n in data if (roles[n] == "evaluation").any()]
    rows = []
    parts = {ref: data[ref][1].reference["all"]}
    for step in range(len(order) + 1):
        if step:
            parts[order[step - 1]] = data[order[step - 1]][1].reference["all"]
        baseline = baseline_from(parts)
        frames = {n: raw_scores(data[n][1], baseline)[roles[n] == "evaluation"] for n in eval_names}
        res = evaluate(frames, caps, "rule", RULE_THRESHOLD)
        rows.append({
            "added": order[step - 1] if step else None,
            "reference_captures": len(parts),
            "reference_seconds": round(sum(st.span for st in parts.values()), 1),
            "fpr_ambient": res["fpr_by_source"]["ambient captures"],
            "fpr_in_attack_captures": res["fpr_by_source"]["normal windows inside attack captures"],
            "fpr_by_ambient_capture": res["fpr_by_ambient_capture"],
            "recall": res["recall"]["value"],
            "recall_by_type": {k: v["value"] for k, v in res["recall_by_type"].items()},
            "precision": res["precision"]["value"],
        })
    return rows


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def ci(v: dict) -> str:
    return f"{v['value']:.3f} [{v['lo']:.3f}, {v['hi']:.3f}]"


def markdown(report: dict) -> str:
    lines = ["# Held-out detection benchmark", "",
             f"Generated {report['created_utc']}. Evaluation split only; 95% block-bootstrap "
             f"intervals ({N_BOOT} draws, blocks of {BLOCK} windows). Thresholds marked "
             f"\"tuned\" were chosen on attack-free tuning windows at a {TARGET_FPR:.0%} "
             f"false-positive rate.", ""]
    for ds in report["datasets"]:
        lines += [f"## {ds['dataset'].upper()}", ""]
        for role, s in ds["split"].items():
            lines.append(f"- {role}: {len(s['captures'])} capture(s), {s['windows']:,} windows, "
                         f"{s['attack_windows']:,} attack windows")
        lines.append("")
        for ref_name, ref in ds["references"].items():
            lines += [f"### Reference: {ref_name} ({len(ref['reference_captures'])} capture(s), "
                      f"{ref['reference_seconds']:,.0f} s)", "",
                      "| detector | threshold | precision | recall | F1 | FPR | AUROC | AUPRC |",
                      "|---|---|---|---|---|---|---|---|"]
            for key, r in ref["evaluation"].items():
                name = LABELS.get(key, key)
                auroc = "n/a" if r["auroc"] is None else f"{r['auroc']:.3f}"
                auprc = "n/a" if r["auprc"] is None else f"{r['auprc']:.3f}"
                lines.append(f"| {name} | {r['threshold']:.3g} | {ci(r['precision'])} | "
                             f"{ci(r['recall'])} | {ci(r['f1'])} | {ci(r['fpr'])} | "
                             f"{auroc} | {auprc} |")
            types = sorted({t for r in ref["evaluation"].values() for t in r["recall_by_type"]})
            lines += ["", "Recall by attack type (attack windows detected / total):", "",
                      "| detector | " + " | ".join(types) + " | FPR on ambient captures |",
                      "|---|" + "---|" * (len(types) + 1)]
            for key, r in ref["evaluation"].items():
                cells = []
                for t in types:
                    v = r["recall_by_type"].get(t)
                    cells.append(f"{v['value']:.3f} ({v['k']}/{v['n']})" if v else "n/a")
                amb = r["fpr_by_source"].get("ambient captures")
                amb_txt = f"{amb['value']:.3f} ({amb['k']}/{amb['n']})" if amb else "n/a"
                lines.append(f"| {LABELS.get(key, key)} | " + " | ".join(cells) + f" | {amb_txt} |")
            lines.append("")
        if "coverage" in ds:
            names = sorted(ds["coverage"][0]["fpr_by_ambient_capture"])
            lines += ["### Reference coverage (rule detector, fixed 0.55)", "",
                      "| reference captures | seconds | added | FPR, held-out ambient | "
                      + " | ".join(n.replace("ambient_", "") for n in names)
                      + " | attack recall |",
                      "|---|---|---|---|" + "---|" * (len(names) + 1)]
            for row in ds["coverage"]:
                a = row["fpr_ambient"]
                per = [f"{row['fpr_by_ambient_capture'][n]['value']:.3f}" for n in names]
                lines.append(f"| {row['reference_captures']} | {row['reference_seconds']:,.0f} | "
                             f"{(row['added'] or 'reference only').replace('ambient_', '')} | "
                             f"{a['value']:.3f} ({a['k']}/{a['n']}) | " + " | ".join(per)
                             + f" | {row['recall']:.3f} |")
            lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", choices=["road", "hcrl", "all"], default="all")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    t0 = time.perf_counter()
    kinds = ["road", "hcrl"] if args.dataset == "all" else [args.dataset]
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "protocol": "app/datasets.py",
        "window_s": WINDOW_S, "rule_threshold": RULE_THRESHOLD, "target_fpr": TARGET_FPR,
        "bootstrap": {"draws": N_BOOT, "block_windows": BLOCK, "seed": SEED},
        "code_sha256": {name: cache.sha256(BACKEND / name) for name in
                         ["app/windowstats.py", "app/datasets.py", "app/stats.py",
                          "app/features.py", "app/detector.py", "scripts/benchmark.py"]},
        "datasets": [run_dataset(d) for d in kinds],
    }
    report["seconds"] = round(time.perf_counter() - t0, 1)
    out = args.out or BACKEND / "out" / "benchmark"
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    text = markdown(report)
    (out / "results.md").write_text(text)
    print(text)
    print(f"wrote {out}/results.json and results.md in {report['seconds']}s")


if __name__ == "__main__":
    main()
