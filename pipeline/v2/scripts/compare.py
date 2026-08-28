from __future__ import annotations

import pandas as pd


def compare_perimeters(v1: pd.DataFrame, v2: pd.DataFrame) -> pd.DataFrame:
    left = set(v1.grant_id.astype(str))
    right = set(v2.grant_id.astype(str))
    rows = []
    for grant_id in sorted(left | right):
        if grant_id in left and grant_id in right:
            status = "both"
        elif grant_id in left:
            status = "v1_only"
        else:
            status = "v2_only"
        rows.append({"grant_id": grant_id, "perimeter_status": status})
    return pd.DataFrame(rows)
