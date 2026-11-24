import pytest

from scripts.summarize_final_models import human_review, november_results, read_review_rows


def test_tue_missing_attack_stays_in_the_target_denominator():
    result = november_results("tue")
    run = result["runs"]["glm-5.3_v2-dosv1_alert"]

    assert result["counts"]["alerts"] == 44
    assert run["reply_rows"] == 43
    assert run["missing_target_ids"] == ["A0028"]
    assert run["recorded_reply_failures"] == []
    assert run["scores"]["accuracy"]["all"]["n"] == 43
    assert run["target_scores"]["accuracy"]["all"]["n"] == 44
    assert run["target_scores"]["accuracy"]["all"]["k"] == 2
    paired = result["prompt_ablation"]["glm-5.3"]["paired_attack_scores_v2_dosv1_vs_v2"]
    assert paired["all"]["n"] == 43


def test_midterm_replication_adds_hcrl_and_still_tracks_the_missing_false_alarm():
    result = november_results("midterm100")
    glm = result["runs"]["glm-5.3_v2-dosv1_alert"]
    paired = result["prompt_ablation"]["glm-5.3"]["paired_attack_scores_v2_dosv1_vs_v2"]

    assert glm["reply_rows"] == 99
    assert glm["missing_target_ids"] == ["A0093"]
    assert glm["target_scores"]["false_alarms_called_benign"]["n"] == 11
    assert paired["all"]["n"] == 89
    assert (paired["hcrl"]["b_correct"], paired["hcrl"]["a_correct"]) == (61, 68)


def test_human_review_keeps_disagreements_unresolved():
    review = human_review()

    assert review["status"] == "rated_adjudication_pending"
    assert [sheet["labeled"] for sheet in review["sheets"].values()] == [40, 40]
    assert review["results"]["agreed"] == 32
    assert review["results"]["kappa"]["kappa"] == pytest.approx(0.520958)
    assert review["adjudication"]["unresolved"] == len(review["adjudication"]["decisions"]) == 8
    assert set(review["adjudication"]["decisions"].values()) == {"UNRESOLVED"}
    assert review["adjudication"]["adjudicated_support_rates"] is None


def test_review_validation_rejects_duplicate_claim_ids(tmp_path):
    rater_file = tmp_path / "rater.csv"
    rater_file.write_text("claim_id,label\nC001,S\nC001,U\n")

    with pytest.raises(ValueError, match="duplicate"):
        read_review_rows(rater_file, {"C001"})
