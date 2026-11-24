"""The Evaluation tab's benchmark API and prediction submissions.

Submissions are the one place the dashboard accepts outside input, so the
validation rules each get a test. Everything runs against a copy of the
frozen held-out set in a temporary folder; the real results are untouched.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import benchmarks  # noqa: E402

REAL = Path(__file__).resolve().parents[1] / "out"
SET = "heldout"
pytestmark = pytest.mark.skipif(not (REAL / "alerts" / SET / "alerts.jsonl").exists(),
                                reason="frozen held-out set not present")


@pytest.fixture
def out(tmp_path, monkeypatch):
    shutil.copytree(REAL / "alerts" / SET, tmp_path / "alerts" / SET)
    src = REAL / "explanations" / SET
    for run in ("control-v2_alert", "gemma-4-31b_v2_alert"):
        if (src / run).exists():
            shutil.copytree(src / run, tmp_path / "explanations" / SET / run)
    monkeypatch.setattr(benchmarks, "OUT", tmp_path)
    benchmarks.rescore(SET)
    return tmp_path


def _alerts(out):
    return benchmarks._read_jsonl(out / "alerts" / SET / "alerts.jsonl")


def _file(rows):
    return "".join(json.dumps(r) + "\n" for r in rows).encode()


def test_perfect_submission_scores_perfectly(out):
    alerts = _alerts(out)
    rows = [{"id": a["id"], "attack_type": a["true_type"] if a["is_attack"] else "benign"}
            for a in alerts]
    res = benchmarks.submit(SET, "oracle", _file(rows))
    assert res == {"run": "submitted-oracle", "predictions": len(alerts), "missing_alerts": 0}
    run = benchmarks.explainers()[SET]["runs"]["submitted-oracle"]
    assert run["submitted"] and run["accuracy"]["all"]["k"] == run["accuracy"]["all"]["n"]
    assert run["false_alarms_called_benign"]["k"] == run["false_alarms_called_benign"]["n"]


def test_resubmitting_a_runs_labels_reproduces_its_score(out):
    src = out / "explanations" / SET / "gemma-4-31b_v2_alert"
    if not src.exists():
        pytest.skip("gemma run not present")
    rows = [{"id": r["id"], "attack_type": r["attack_type"]}
            for r in benchmarks._read_jsonl(src / "replies.jsonl") if not r.get("error")]
    benchmarks.submit(SET, "copy", _file(rows))
    runs = benchmarks.explainers()[SET]["runs"]
    assert runs["submitted-copy"]["accuracy"] == runs["gemma-4-31b_v2_alert"]["accuracy"]


def test_missing_alerts_count_as_wrong(out):
    a = next(x for x in _alerts(out) if x["is_attack"])
    res = benchmarks.submit(SET, "one", _file([{"id": a["id"], "attack_type": a["true_type"]}]))
    assert res["missing_alerts"] == len(_alerts(out)) - 1
    acc = benchmarks.explainers()[SET]["runs"]["submitted-one"]["accuracy"]["all"]
    assert acc["k"] == 1 and acc["n"] == sum(x["is_attack"] for x in _alerts(out))
    run = benchmarks.explainers()[SET]["runs"]["submitted-one"]
    assert run["no_answer"] == len(_alerts(out)) - 1


def test_invented_citations_are_dropped(out):
    a = _alerts(out)[0]
    benchmarks.submit(SET, "cites", _file([{"id": a["id"], "attack_type": "dos",
                                            "claims": [{"text": "t", "cites": ["E0", "E999"]}]}]))
    reply = benchmarks._read_jsonl(out / "explanations" / SET / "submitted-cites" / "replies.jsonl")[0]
    assert reply["claims"][0]["cites"] == ["E0"] and not reply["grounded"]


@pytest.mark.parametrize("name, body, message", [
    ("bad name!", b'{"id": "A0000", "attack_type": "dos"}\n', "name"),
    ("ok", b"not json\n", "not valid JSON"),
    ("ok", b'["A0000", "dos"]\n', "expected a JSON object"),
    ("ok", b'{"id": "Z9999", "attack_type": "dos"}\n', "unknown alert id"),
    ("ok", b'{"id": "A0000", "attack_type": "ransomware"}\n', "attack_type must be"),
    ("ok", b'{"id": "A0000", "attack_type": "dos"}\n{"id": "A0000", "attack_type": "dos"}\n',
     "duplicate"),
    ("ok", b"\n\n", "no predictions"),
    ("ok", b"\xff\xfe", "UTF-8"),
])
def test_bad_submissions_are_rejected_and_leave_nothing_behind(out, name, body, message):
    with pytest.raises(benchmarks.SubmissionError, match=message):
        benchmarks.submit(SET, name, body)
    assert not list((out / "explanations" / SET).glob("submitted-*"))


def test_names_cannot_be_reused_or_escape_the_folder(out):
    a = _alerts(out)[0]
    benchmarks.submit(SET, "mine", _file([{"id": a["id"], "attack_type": "dos"}]))
    with pytest.raises(benchmarks.SubmissionError, match="already exists"):
        benchmarks.submit(SET, "mine", _file([{"id": a["id"], "attack_type": "dos"}]))
    for bad in ("../x", "a/b", ".hidden", ""):
        with pytest.raises(benchmarks.SubmissionError):
            benchmarks.submit(SET, bad, _file([{"id": a["id"], "attack_type": "dos"}]))


def test_oversized_files_are_rejected(out, monkeypatch):
    monkeypatch.setattr(benchmarks, "MAX_SUBMISSION_BYTES", 10)
    with pytest.raises(benchmarks.SubmissionError, match="larger than"):
        benchmarks.submit(SET, "big", b'{"id": "A0000", "attack_type": "dos"}\n')


def test_unknown_set_is_rejected(out):
    with pytest.raises(KeyError):
        benchmarks.submit("nope", "x", b"")


def test_packets_carry_no_labels(out):
    text = benchmarks.packets(SET)
    for row in map(json.loads, text.splitlines()):
        assert set(row) == {"id", "evidence"}
    assert "true_type" not in text and "is_attack" not in text


def test_compare_lists_only_disagreements(out):
    runs = benchmarks.explainers()[SET]["runs"]
    if not {"control-v2_alert", "gemma-4-31b_v2_alert"} <= set(runs):
        pytest.skip("runs not present")
    res = benchmarks.compare(SET, "control-v2_alert", "gemma-4-31b_v2_alert")
    for row in res["alerts"]:
        if row["is_attack"]:
            assert row["a"]["correct"] != row["b"]["correct"]
        else:
            assert row["a"]["label"] != row["b"]["label"]
        assert all(i["kind"] != "frames" for i in row["evidence"])


def test_api_routes(out):
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    assert c.get("/api/benchmark/explainers").status_code == 200
    assert c.get(f"/api/benchmark/explainers/{SET}/packets").status_code == 200
    assert c.get("/api/benchmark/explainers/nope/packets").status_code == 404
    a = _alerts(out)[0]
    ok = c.post(f"/api/benchmark/explainers/{SET}/submit", data={"name": "api"},
                files={"file": ("p.jsonl", _file([{"id": a["id"], "attack_type": "dos"}]))})
    assert ok.status_code == 200 and ok.json()["run"] == "submitted-api"
    bad = c.post(f"/api/benchmark/explainers/{SET}/submit", data={"name": "api2"},
                 files={"file": ("p.jsonl", b"nope\n")})
    assert bad.status_code == 400


def test_tue_api_counts_missing_target_and_preserves_archived_scores():
    from fastapi.testclient import TestClient
    from app.main import app

    path = REAL / "explanations" / "tue" / "scores.json"
    if not path.exists():
        pytest.skip("saved TU Eindhoven results not present")
    saved = path.read_bytes()
    name = "glm-5.3_v2-dosv1_alert"
    assert json.loads(saved)["runs"][name]["accuracy"]["all"]["n"] == 43

    client = TestClient(app)
    response = client.get("/api/benchmark/explainers")
    assert response.status_code == 200
    tue = response.json()["tue"]
    run = tue["runs"][name]
    assert run["accuracy"]["tue"]["k"] == 2
    assert run["accuracy"]["tue"]["n"] == 44
    assert run["accuracy_by_type"]["tue/fuzzing"]["n"] == 40
    assert run["confusion"]["tue/fuzzing"]["no answer"] == 1
    assert run["no_answer"] == 1
    undefined_rate = {"k": 0, "n": 0, "value": None, "lo": None, "hi": None}
    assert run["false_alarms_called_benign"] == undefined_rate
    assert tue["runs"]["control-v2_alert"]["false_alarms_called_benign"] == undefined_rate
    assert tue["pairs"][f"control-v2_alert vs {name}"]["all"]["n"] == 44
    assert path.read_bytes() == saved

    comparison = client.get("/api/benchmark/explainers/midterm100/compare",
                            params={"a": name, "b": "control-v2_alert"})
    assert comparison.status_code == 200
    missing = next(row for row in comparison.json()["alerts"] if row["id"] == "A0093")
    assert missing["a"]["label"] == "no answer"
    assert missing["a"]["error"] == "no reply recorded for target"


def test_api_uses_declared_subset_targets(out, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from scripts import run_explanations

    runner_root = out / "runner"
    runner_root.mkdir()
    (runner_root / "out").symlink_to(out, target_is_directory=True)
    monkeypatch.setattr(run_explanations, "BACKEND", runner_root)
    monkeypatch.setattr(sys, "argv", ["run_explanations", "--set", SET, "--dataset",
                                     "hcrl", "--limit", "2", "--run", "subset"])
    run_explanations.main()
    run = out / "explanations" / SET / "subset"
    meta = json.loads((run / "run.json").read_text())
    assert len(meta["target_ids"]) == 2
    reply_path = run / "replies.jsonl"
    replies = reply_path.read_text().splitlines()
    reply_path.write_text(replies[0] + "\n")
    benchmarks.rescore(SET)
    scores_path = out / "explanations" / SET / "scores.json"
    saved = scores_path.read_bytes()
    saved_subset = json.loads(saved)["runs"]["subset"]
    assert saved_subset["accuracy"]["all"]["n"] == 2
    assert saved_subset["no_answer"] == 1

    client = TestClient(app)
    response = client.get("/api/benchmark/explainers")
    assert response.status_code == 200
    result = response.json()[SET]["runs"]["subset"]
    assert result["attack_alerts"] == 2
    assert result["accuracy"]["all"]["n"] == 2
    assert result["no_answer"] == 1

    reply_path.write_text("\n".join(replies) + "\n")
    updated = client.get("/api/benchmark/explainers").json()[SET]["runs"]["subset"]
    assert updated["accuracy"]["all"]["n"] == 2
    assert updated["no_answer"] == 0
    assert scores_path.read_bytes() == saved

    reply_path.write_text(replies[0] + "\n")
    del meta["target_ids"]
    (run / "run.json").write_text(json.dumps(meta))
    benchmarks.rescore(SET)
    legacy = client.get("/api/benchmark/explainers").json()[SET]["runs"]["subset"]
    assert legacy["accuracy"]["all"]["n"] == 1
    assert legacy["no_answer"] == 0


def test_detection_api_preserves_undefined_metrics_as_null(out):
    from fastapi.testclient import TestClient
    from app.main import app

    source = REAL / "benchmark" / "results.json"
    if not source.exists():
        pytest.skip("saved detection benchmark not present")
    destination = out / "benchmark" / "results.json"
    destination.parent.mkdir()
    shutil.copyfile(source, destination)
    response = TestClient(app).get("/api/benchmark/detection")
    assert response.status_code == 200
    result = response.json()
    assert result["datasets"]
    assert json.dumps(result, allow_nan=False)
    road = next(row for row in result["datasets"] if row["dataset"] == "road")
    precision = road["references"]["single"]["detectors"]["rule@tuned"]["precision"]
    assert precision == {"value": None, "lo": None, "hi": None}


def test_benchmark_api_keeps_both_result_formats(out):
    from fastapi.testclient import TestClient
    from app import benchmark
    from app.main import app

    client = TestClient(app)
    legacy = client.get("/api/benchmark/detectors")
    assert legacy.status_code == 200
    assert legacy.json() == benchmark.load_detection()
    assert set(client.get("/api/benchmark").json()) == {"datasets", "errors"}
    assert client.get("/api/benchmark/explainers").status_code == 200
    paths = [(method, route.path) for route in app.routes
             for method in getattr(route, "methods", [])]
    assert len(paths) == len(set(paths))
