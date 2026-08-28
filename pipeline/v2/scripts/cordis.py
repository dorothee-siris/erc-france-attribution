from __future__ import annotations

import pandas as pd

from common import normalize_grant_id


ORGANISATION_COLUMNS = {
    "projectID": "grant_id",
    "organisationID": "pic",
    "name": "organisation_name",
    "country": "country",
    "role": "role",
    "ecContribution": "eu_contribution",
    "netEcContribution": "net_eu_contribution",
    "endOfParticipation": "participation_ended",
    "active": "active",
    "city": "city",
    "nutsCode": "nuts_code",
}


def normalize_organisations(raw: pd.DataFrame) -> pd.DataFrame:
    missing = {"projectID", "organisationID", "country"} - set(raw.columns)
    if missing:
        raise ValueError(f"CORDIS organisation data missing columns: {sorted(missing)}")
    frame = raw.rename(columns=ORGANISATION_COLUMNS).copy()
    for column in ORGANISATION_COLUMNS.values():
        if column not in frame.columns:
            frame[column] = None
    frame["grant_id"] = normalize_grant_id(frame.grant_id)
    frame["pic"] = normalize_grant_id(frame.pic)
    frame["eu_contribution"] = pd.to_numeric(frame.eu_contribution, errors="coerce")
    frame["net_eu_contribution"] = pd.to_numeric(frame.net_eu_contribution, errors="coerce")
    frame["participation_ended"] = frame.participation_ended.astype("string").str.casefold().map({"true": True, "false": False}).astype("boolean")
    frame["country"] = frame.country.astype("string").str.upper()
    return frame[list(ORGANISATION_COLUMNS.values())]


def select_french_participations(organisations: pd.DataFrame, starts: pd.DataFrame) -> pd.DataFrame:
    orgs = organisations.copy()
    orgs["grant_id"] = orgs.grant_id.astype(str)
    project_starts = starts[["grant_id", "start_date"]].copy()
    project_starts["grant_id"] = project_starts.grant_id.astype(str)
    joined = orgs.merge(project_starts, on="grant_id", how="inner")
    return joined[joined.country == "FR"].reset_index(drop=True)
