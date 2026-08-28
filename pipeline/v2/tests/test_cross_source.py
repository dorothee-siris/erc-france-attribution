import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from resolution import choose_resolution


def _cand(**kw):
    base = dict(component_id="c1", grant_id="g1", pi_name="Jane Doe", pi_match=True, award_time=True,
                lab_name="Lab", rnsr_id=None, source_kind="v1_openalex", source_family="v1",
                independent_corroboration=True)
    base.update(kw)
    return base


def test_two_families_agree_grade_A():
    df = pd.DataFrame([
        _cand(source_family="v1", source_kind="v1_openalex", rnsr_id="200X"),
        _cand(source_family="openalex", source_kind="openalex_author", rnsr_id="200X"),
    ])
    out = choose_resolution(df).iloc[0]
    assert out.evidence_grade == "A" and out.review_status == "auto_accepted"


def test_hal_grant_alone_grade_A():
    df = pd.DataFrame([_cand(source_family="hal", source_kind="hal_grant",
                             independent_corroboration=False, rnsr_id="200Y")])
    out = choose_resolution(df).iloc[0]
    assert out.evidence_grade == "A"


def test_single_v1_grade_B():
    out = choose_resolution(pd.DataFrame([_cand()])).iloc[0]
    assert out.evidence_grade == "B" and out.review_status == "auto_accepted"


def test_no_pi_match_is_manual():
    out = choose_resolution(pd.DataFrame([_cand(pi_match=False, independent_corroboration=False)])).iloc[0]
    assert out.review_status == "manual_review"


def test_genuine_conflict_is_manual():
    # two well-supported but DIFFERENT labs (each 2 families) -> conflict -> manual
    df = pd.DataFrame([
        _cand(source_family="v1", rnsr_id="AAA"), _cand(source_family="hal", source_kind="hal_grant", rnsr_id="AAA"),
        _cand(source_family="openalex", source_kind="openalex_author", rnsr_id="BBB"),
        _cand(source_family="v1", source_kind="v1_llm", rnsr_id="BBB"),
    ])
    out = choose_resolution(df).iloc[0]
    assert out.review_status == "manual_review" and bool(out.conflict)
