"""Annotate a saved model run against its frozen corpus without model calls.

Writes a separate, source-hashed annotation artifact. Original results,
classification, citation validity, and raw responses remain untouched.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from app.validation import VALIDATION_VERSION, identifier_warnings
from scripts.benchmark_models import atomic_write, fingerprint
from scripts.compare_models import validated_records


def annotate(run, corpus):
    rows = validated_records(run)
    if run["corpus_sha256"] != fingerprint(corpus) or len(rows) != len(corpus["alerts"]):
        raise ValueError("Run and corpus identities or alert counts differ")
    alerts = []
    for index, row in sorted(rows.items()):
        evidence = corpus["alerts"][index]["evidence"]
        if row["evidence_sha256"] != fingerprint(evidence):
            raise ValueError(f"Evidence hash mismatch at index {index}")
        for key in ("capture", "alert_id", "start", "end", "true_type"):
            if row.get(key) != corpus["alerts"][index].get(key):
                raise ValueError(f"Target identity mismatch at index {index}")
        alerts.append({"corpus_index": index, "evidence_sha256": row["evidence_sha256"],
                       "validation_version": VALIDATION_VERSION,
                       "validation_warnings": identifier_warnings(row["explanation"], evidence)})
    counts = Counter(w["code"] for row in alerts for w in row["validation_warnings"])
    return {"status": "complete", "dataset": run["dataset"],
            "validation_version": VALIDATION_VERSION, "corpus_sha256": run["corpus_sha256"],
            "alerts": alerts,
            "summary": {"responses_checked": len(alerts),
                        "responses_with_warnings": sum(bool(a["validation_warnings"]) for a in alerts),
                        "responses_with_absent_explicit_ids": sum(any(w["code"] == "can_id_not_in_evidence" for w in a["validation_warnings"]) for a in alerts),
                        "warnings_by_code": dict(counts),
                        "meaning": "Identifier membership review only; neither citation validity nor semantic entailment."}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Annotation output already exists; choose a new path to preserve provenance")
    run_bytes, corpus_bytes = args.run.read_bytes(), args.corpus.read_bytes()
    try:
        result = annotate(json.loads(run_bytes), json.loads(corpus_bytes))
    except (ValueError, KeyError) as exc:
        parser.error(str(exc))
    result.update({"source_run": str(args.run), "source_run_sha256": hashlib.sha256(run_bytes).hexdigest(),
                   "corpus_file": str(args.corpus), "corpus_file_sha256": hashlib.sha256(corpus_bytes).hexdigest(),
                   "validator_sha256": hashlib.sha256((Path(__file__).resolve().parents[1] / "app/validation.py").read_bytes()).hexdigest(),
                   "annotation_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   "created_at": datetime.now(timezone.utc).isoformat()})
    atomic_write(args.out, result)
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
