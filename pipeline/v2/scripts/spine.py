from __future__ import annotations

import pandas as pd

from common import normalize_grant_id


COLUMN_MAP = {
    "Programme": "programme",
    "Acronym": "acronym",
    "Project Title": "project_title",
    "Abstract": "abstract",
    "Researcher(s)": "pi_names_raw",
    "Host Institution(s)": "host_institutions_raw",
    "Country": "dashboard_country",
    "Region": "dashboard_region",
    "Grant Type": "grant_type",
    "Domain": "domain",
    "Panel": "panel",
    "Call": "call",
    "Call Year": "call_year",
    "Start Date": "start_date",
    "End Date": "end_date",
    "EU contribution": "project_eu_contribution",
    "CORDIS Link": "cordis_url",
}


def build_spine(source: pd.DataFrame, start_inclusive: str, end_exclusive: str) -> pd.DataFrame:
    missing = ({"Project Number", *COLUMN_MAP} - set(source.columns))
    if missing:
        raise ValueError(f"dashboard is missing columns: {sorted(missing)}")
    frame = source.copy()
    frame["grant_id"] = normalize_grant_id(frame["Project Number"])
    frame["start_date"] = pd.to_datetime(frame["Start Date"], errors="coerce")
    frame = frame[(frame.start_date >= pd.Timestamp(start_inclusive)) & (frame.start_date < pd.Timestamp(end_exclusive))].copy()
    if frame.grant_id.isna().any():
        raise ValueError("dashboard contains missing/invalid project numbers in the selected cohort")
    if frame.grant_id.duplicated().any():
        duplicate_ids = frame.loc[frame.grant_id.duplicated(keep=False), "grant_id"].unique().tolist()
        raise ValueError(f"duplicate project IDs in selected cohort: {duplicate_ids[:10]}")
    frame = frame.rename(columns={key: value for key, value in COLUMN_MAP.items() if key != "Start Date"})
    frame["end_date"] = pd.to_datetime(frame.end_date, errors="coerce")
    frame["call_year"] = pd.to_numeric(frame.call_year, errors="coerce").astype("Int64")
    frame["project_eu_contribution"] = pd.to_numeric(frame.project_eu_contribution, errors="coerce")
    frame["start_year"] = frame.start_date.dt.year.astype("Int64")
    frame["is_synergy"] = frame.grant_type.eq("Synergy Grants")
    columns = [
        "grant_id", "programme", "acronym", "project_title", "abstract", "pi_names_raw",
        "host_institutions_raw", "dashboard_country", "dashboard_region", "grant_type", "domain",
        "panel", "call", "call_year", "start_date", "start_year", "end_date",
        "project_eu_contribution", "cordis_url", "is_synergy",
    ]
    return frame[columns].sort_values(["start_date", "grant_id"]).reset_index(drop=True)
