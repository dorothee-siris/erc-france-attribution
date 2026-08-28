"""Cross-source evidence grading. Groups all candidates (HAL, OpenAlex grant/author, v1) per component
and grades the winning lab:

  Grade A  — an authoritative grant-linked source (HAL), OR >=2 independent source families agree.
  Grade B  — a single corroborated source (OpenAlex >=2 works, or a v1 tier).
  manual   — genuine conflict (two well-supported but different labs) or no valid evidence.

All accepted evidence requires pi_match AND award_time. "Agreement" is by rnsr_id when both present,
else by a normalized token signature of the lab name.
"""
from __future__ import annotations

import pandas as pd

from rnsr_link import _norm

EXACT_GRANT_SOURCES = {"hal_grant", "institutional_grant", "official_project"}


def _lab_key(row) -> str:
    """Agreement key: rnsr_id when present (so cross-source candidates cluster after RNSR-linking),
    else the full normalized lab name (conservative — distinct unmatched labs stay distinct)."""
    rid = row.get("rnsr_id")
    if rid is not None and not (isinstance(rid, float) and pd.isna(rid)) and str(rid).strip():
        return f"rnsr:{rid}"
    name = _norm(row.get("lab_name", ""))
    return f"lab:{name}" if name else "lab:?"


def _bool(series) -> pd.Series:
    return series.fillna(False).astype(bool) if series is not None else series


def choose_resolution(candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates is None or candidates.empty:
        return pd.DataFrame()
    df = candidates.copy()
    for col in ("pi_match", "award_time", "independent_corroboration"):
        df[col] = _bool(df[col]) if col in df.columns else False
    if "source_family" not in df.columns:
        df["source_family"] = df.get("source_kind", "unknown")
    group_key = "component_id" if "component_id" in df.columns else "grant_id"
    rows = []
    for cid, group in df.groupby(group_key, sort=False):
        valid = group[group.pi_match & group.award_time].copy()
        if valid.empty:
            sel = group.iloc[0].to_dict()
            sel.update({"evidence_grade": "unresolved", "review_status": "manual_review",
                        "agreeing_families": 0, "conflict": False})
            rows.append(sel)
            continue
        valid["lab_key"] = valid.apply(_lab_key, axis=1)
        clusters = []
        for key, sub in valid.groupby("lab_key"):
            clusters.append({
                "key": key, "sub": sub,
                "families": set(sub.source_family), "n_families": sub.source_family.nunique(),
                "has_exact": bool(sub.source_kind.isin(EXACT_GRANT_SOURCES).any()),
                "corroborated": bool(sub.independent_corroboration.any()),
                "n": len(sub),
            })
        clusters.sort(key=lambda c: (c["has_exact"], c["n_families"], c["n"]), reverse=True)
        win = clusters[0]
        runner = clusters[1] if len(clusters) > 1 else None
        conflict = bool(runner and (runner["has_exact"] or runner["n_families"] >= 2)
                        and win["n_families"] - runner["n_families"] < 1 and runner["key"] != win["key"])
        # representative: prefer an exact/HAL row, then one carrying rnsr_id, else first
        sub = win["sub"]
        pref = sub[sub.source_kind.isin(EXACT_GRANT_SOURCES)]
        if pref.empty and "rnsr_id" in sub:
            pref = sub[sub.rnsr_id.notna()]
        selected = (pref.iloc[0] if not pref.empty else sub.iloc[0]).to_dict()
        if conflict:
            grade, status = "unresolved", "manual_review"
        elif win["has_exact"] or win["n_families"] >= 2:
            grade, status = "A", "auto_accepted"
        elif win["corroborated"]:
            grade, status = "B", "auto_accepted"
        else:
            grade, status = "unresolved", "manual_review"
        selected.update({"evidence_grade": grade, "review_status": status,
                         "agreeing_families": win["n_families"], "conflict": conflict})
        rows.append(selected)
    return pd.DataFrame(rows)
