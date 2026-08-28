from __future__ import annotations

import pandas as pd


def enrich_from_rnsr(resolutions: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    rows = []
    hist = history.copy()
    hist["year"] = pd.to_numeric(hist.year, errors="coerce").astype("Int64")
    for resolution in resolutions.itertuples(index=False):
        candidates = hist[hist.rnsr_id.astype(str) == str(resolution.rnsr_id)].copy()
        exact = candidates[candidates.year == int(resolution.start_year)]
        if not exact.empty:
            selected = exact.iloc[0]
        else:
            prior = candidates[candidates.year <= int(resolution.start_year)].sort_values("year")
            selected = prior.iloc[-1] if not prior.empty else (candidates.iloc[0] if not candidates.empty else None)
        row = resolution._asdict()
        if selected is not None:
            for column in ["lab_name", "tutelles", "commune_code", "region", "unit_type"]:
                row[column] = selected.get(column)
            row["rnsr_record_year"] = int(selected.year)
        rows.append(row)
    return pd.DataFrame(rows)
