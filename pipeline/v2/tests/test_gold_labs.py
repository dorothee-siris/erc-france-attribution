"""Accuracy gate: resolved labs for source-verified gold grants must contain their expected lab.
Skips gracefully when the pipeline output isn't present yet (so the suite passes pre-run)."""
import os
import re
import sys
import unicodedata

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "..", "outputs", "french_components.parquet")
GOLD = os.path.join(HERE, "data", "gold_labs.csv")


def _norm(v):
    a = unicodedata.normalize("NFKD", str(v)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", a.lower())).strip()


@pytest.mark.skipif(not os.path.exists(OUT), reason="pipeline output not generated yet")
def test_gold_precision():
    comp = pd.read_parquet(OUT)
    comp["grant_id"] = comp.grant_id.astype(str)
    gold = pd.read_csv(GOLD, dtype={"grant_id": str})
    acc = comp[comp.review_status == "auto_accepted"]
    resolved, correct = 0, 0
    for _, g in gold.iterrows():
        rows = acc[acc.grant_id == g.grant_id]
        if rows.empty:
            continue
        resolved += 1
        hay = _norm(str(rows.iloc[0].get("lab_name", "")) + " " + str(rows.iloc[0].get("tutelles", "")))
        if any(_norm(kw) in hay for kw in str(g.gold_keyword).split("|")):
            correct += 1
    if resolved < 3:
        pytest.skip(f"only {resolved}/8 gold grants resolved so far — precision gate deferred")
    precision = correct / resolved
    assert precision >= 0.85, f"gold precision {precision:.0%} ({correct}/{resolved}) below 85%"
