import json
import hashlib

from app import benchmark, metrics


def test_same_alert_number_different_corpus_never_merges(tmp_path):
    for name, corpus, status in [("a", "a" * 64, "complete"), ("b", "b" * 64, "complete_with_failures")]:
        directory = tmp_path / f"explanations_{name}" / "road"
        directory.mkdir(parents=True)
        payload = {"dataset": "road", "explainer": "rcd", "model": name, "status": status,
                   "corpus_sha256": corpus, "summary": {"grounding": {"rate": 0.5}},
                   "alerts": [{"capture": "same", "role": "attack_capture", "alert_id": 0,
                               "start": 0, "end": 1, "detector_score": .8, "true_type": "dos",
                               "explanation": {"attack_type": "dos"}}]}
        (directory / "explanations_rcd.json").write_text(json.dumps(payload))
    result = benchmark.load(tmp_path)
    assert len(result["datasets"]) == 2
    assert all(len(d["runs"]) == 1 for d in result["datasets"])
    assert all(d["runs"][0]["summary"]["grounding"]["grounded_rate"] == .5 for d in result["datasets"])


def test_model_failure_cannot_borrow_correct_control_prediction():
    score = metrics.classification_accuracy([{"true_type": "dos", "explanation": {
        "attack_type": "dos", "fallback": True, "model": "mock (fallback: broken)"}}])
    assert score["accuracy"] == 0
    assert score["confusion"] == {"dos": {"request_failed": 1}}


def test_model_failure_cannot_borrow_control_citation_validity():
    result = metrics.grounding_rate([{"explanation": {"fallback": True, "grounded": True}}])
    assert result["grounded_rate"] is None
    assert result["failed_responses"] == 1


def test_two_models_in_one_run_root_keep_both_predictions(tmp_path):
    for model in ["model_a", "model_b"]:
        directory = tmp_path / "explanations_shared" / model
        directory.mkdir(parents=True)
        payload = {"dataset": "road", "explainer": "rcd", "model": model, "status": "complete",
                   "corpus_sha256": "a" * 64, "summary": {"grounding": {"rate": 1}},
                   "alerts": [{"capture": "same", "role": "attack_capture", "alert_id": 0,
                               "start": 0, "end": 1, "detector_score": .8, "true_type": "dos",
                               "explanation": {"attack_type": "dos", "model": model}}]}
        (directory / "explanations_rcd.json").write_text(json.dumps(payload))
    dataset = benchmark.load(tmp_path)["datasets"][0]
    assert len({r["id"] for r in dataset["runs"]}) == 2
    assert {v["model"] for v in dataset["alerts"][0]["results"].values()} == {"model_a", "model_b"}


def test_detection_view_keeps_negative_complete_results_and_skips_partial(tmp_path):
    for name, status in [("bad_result", "complete"), ("partial", "running")]:
        directory = tmp_path / "detectors_test" / name
        directory.mkdir(parents=True)
        payload = {"dataset": "road", "baseline_profile": "broad", "status": status,
                   "pooled": {"forest": {"all": {"recall": .01, "false_positive_rate": .8},
                                         "held_out_normal": {"false_positive_rate": .9}}}}
        (directory / "results.json").write_text(json.dumps(payload))
    runs = benchmark.load_detection(tmp_path)["runs"]
    assert len(runs) == 1
    assert runs[0]["metrics"]["false_positive_rate"] == .8
    assert runs[0]["normal_metrics"]["false_positive_rate"] == .9


def test_saved_annotations_require_exact_source_and_evidence_identity(tmp_path):
    directory = tmp_path / "explanations_run" / "road"
    directory.mkdir(parents=True)
    payload = {"dataset": "road", "explainer": "rcd", "model": "glm", "status": "complete",
               "corpus_sha256": "corpus", "summary": {}, "alerts": [{
                   "capture": "same", "role": "attack_capture", "alert_id": 0, "corpus_index": 0,
                   "evidence_sha256": "packet", "start": 0, "end": 1, "detector_score": .8,
                   "true_type": "dos", "explanation": {"attack_type": "dos", "grounded": True}}]}
    source = directory / "explanations_rcd.json"
    source.write_text(json.dumps(payload))
    annotation_dir = tmp_path / "validation_run"
    annotation_dir.mkdir()
    annotation = {"status": "complete", "source_run_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                  "corpus_sha256": "corpus", "alerts": [{"corpus_index": 0, "evidence_sha256": "packet",
                      "validation_version": "ids-v1", "validation_warnings": [{"token": "0x55"}]}]}
    annotation_file = annotation_dir / "road.json"
    annotation_file.write_text(json.dumps(annotation))
    def result():
        return next(iter(benchmark.load(tmp_path)["datasets"][0]["alerts"][0]["results"].values()))
    assert result()["validation_warnings"] == [{"token": "0x55"}]
    assert result()["grounded"] is True
    # Same path and corpus number are insufficient once the source changes.
    payload["alerts"][0]["explanation"]["summary"] = "changed response"
    source.write_text(json.dumps(payload))
    assert result()["validation_warnings"] is None
