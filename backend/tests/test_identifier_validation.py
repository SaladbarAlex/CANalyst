from copy import deepcopy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.llm import Explanation, MockExplainer, RCDExplainer, _check_citations, explainer_key
from app.validation import identifier_warnings
from scripts.benchmark_models import fingerprint
from scripts.revalidate_identifiers import annotate


def evidence():
    return {"items": [{"id": "E1", "kind": "id_stats", "detail": {"can_id": "0x655"}}],
            "sample_frames": [{"can_id": "0x025"}], "ids_involved": ["0x075", "0x4EE"]}


def test_summary_typo_is_flagged_without_changing_prediction_citations_or_raw():
    raw = '{"attack_type":"spoofing","summary":"Other flagged IDs (0x075, 0x4EE, 0x55)"}'
    exp = Explanation("spoofing", .8, "high", "unknown", "Other flagged IDs (0x075, 0x4EE, 0x55)",
                      claims=[{"text": "Known ID 0x655 transmitted", "cites": ["E1"]}], raw_response=raw)
    _check_citations(exp, evidence())
    assert exp.grounded and exp.attack_type == "spoofing" and exp.raw_response == raw
    warning, = exp.validation_warnings
    assert warning["code"] == "can_id_not_in_evidence" and warning["field"] == "summary"
    assert warning["token"] == "0x55" and warning["canonical_id"] == "0x055"
    assert exp.summary[warning["start"]:warning["end"]] == "0x55"
    assert exp.to_json()["validation_version"] == "can-id-membership-v1"


@pytest.mark.parametrize("token", ["0x655", "0X655", "0x00000655", "0x4ee", "0X000004EE"])
def test_case_and_padding_identify_the_same_can_id(token):
    assert identifier_warnings({"summary": f"CAN ID {token} appeared"}, evidence()) == []


def test_unqualified_hex_is_review_only_and_not_an_id_assertion():
    warning, = identifier_warnings({"summary": "The payload mask is 0xFF."}, evidence())
    assert warning["code"] == "ambiguous_hex_reference"
    assert not identifier_warnings({"summary": "Payload 0x1122334455667788"}, evidence())


def test_validator_version_participates_in_cache_identity(monkeypatch):
    import app.llm as llm
    before = explainer_key(RCDExplainer())
    monkeypatch.setattr(llm, "VALIDATION_VERSION", "next-version")
    assert before != explainer_key(RCDExplainer())


def test_offline_annotations_preserve_saved_output_and_reject_wrong_evidence():
    row = {"capture": "test", "alert_id": 0, "start": 0, "end": 1, "true_type": "spoofing", "evidence": evidence()}
    corpus = {"dataset": "test", "alerts": [row]}
    run = {"dataset": "test", "model": "model", "status": "complete", "expected_alerts": 1,
           "corpus_sha256": fingerprint(corpus), "alerts": [{**{k: v for k, v in row.items() if k != "evidence"},
               "corpus_index": 0, "evidence_sha256": fingerprint(evidence()),
               "explanation": {"attack_type": "spoofing", "summary": "Known ID 0x55 appeared", "grounded": True, "raw_response": "original"}}]}
    original = deepcopy(run)
    result = annotate(run, corpus)
    assert run == original
    assert result["summary"]["responses_with_absent_explicit_ids"] == 1
    run["alerts"][0]["evidence_sha256"] = "wrong"
    with pytest.raises(ValueError):
        annotate(run, corpus)
