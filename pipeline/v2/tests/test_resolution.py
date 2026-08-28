import pandas as pd

from resolution import choose_resolution


def test_grade_a_exact_grant_pi_lab_is_auto_accepted():
    candidates = pd.DataFrame(
        [
            {
                "grant_id": "1",
                "pi_match": True,
                "lab_name": "Laboratoire Exemple",
                "source_kind": "hal_grant",
                "source_url": "https://hal.science/example",
                "award_time": True,
                "independent_corroboration": False,
            }
        ]
    )
    result = choose_resolution(candidates).iloc[0]
    assert result.evidence_grade == "A"
    assert result.review_status == "auto_accepted"


def test_unmatched_coauthor_affiliation_is_never_accepted():
    candidates = pd.DataFrame(
        [
            {
                "grant_id": "2",
                "pi_match": False,
                "lab_name": "Coauthor Lab",
                "source_kind": "openalex_grant",
                "source_url": "https://openalex.org/W1",
                "award_time": True,
                "independent_corroboration": True,
            }
        ]
    )
    result = choose_resolution(candidates).iloc[0]
    assert result.evidence_grade == "unresolved"
    assert result.review_status == "manual_review"


def test_two_distinct_exact_labs_remain_manual_review():
    candidates = pd.DataFrame(
        [
            {"component_id": "3:0", "grant_id": "3", "pi_match": True, "lab_name": "Lab A", "source_kind": "hal_grant", "source_url": "u1", "award_time": True, "independent_corroboration": False},
            {"component_id": "3:0", "grant_id": "3", "pi_match": True, "lab_name": "Lab B", "source_kind": "hal_grant", "source_url": "u2", "award_time": True, "independent_corroboration": False},
        ]
    )
    result = choose_resolution(candidates).iloc[0]
    assert result.review_status == "manual_review"
    assert result.evidence_grade == "unresolved"
