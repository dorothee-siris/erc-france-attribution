"""Evidence-policy invariants: accepted resolutions must be PI-matched + award-time + non-conflicting,
and no candidate may rely on institution `lineage:` (a forbidden inference)."""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from resolution import choose_resolution

HERE = os.path.dirname(__file__)
COMP = os.path.join(HERE, "..", "outputs", "french_components.parquet")
CKPT = os.path.join(HERE, "..", "checkpoints")


def test_accept_requires_pi_match_and_award_time():
    df = pd.DataFrame([
        {"component_id": "c1", "grant_id": "g", "pi_match": True, "award_time": False,
         "lab_name": "L", "rnsr_id": None, "source_kind": "v1_openalex", "source_family": "v1",
         "independent_corroboration": True},
    ])
    assert choose_resolution(df).iloc[0].review_status == "manual_review"


@pytest.mark.skipif(not os.path.exists(COMP), reason="pipeline output not generated yet")
def test_accepted_rows_are_graded_and_conflict_free():
    comp = pd.read_parquet(COMP)
    acc = comp[comp.review_status == "auto_accepted"]
    assert acc.evidence_grade.isin(["A", "B"]).all()
    if "conflict" in acc.columns:
        assert not acc.conflict.fillna(False).any()


def test_no_lineage_in_candidate_sources():
    for name in ("openalex_candidates.parquet", "v1_candidates.parquet", "hal_candidates.parquet"):
        p = os.path.join(CKPT, name)
        if not os.path.exists(p):
            continue
        d = pd.read_parquet(p)
        if "source_url" in d.columns:
            assert not d.source_url.astype(str).str.contains("lineage", case=False).any()
