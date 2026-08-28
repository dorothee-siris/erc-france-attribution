from __future__ import annotations

import re

import pandas as pd

from common import normalize_grant_id


ERC_SCHEME_PATTERN = r"(?:^|-)ERC(?:$|-)"


def _grant_type(master_call: str, funding_scheme: str) -> str:
    value = f"{master_call} {funding_scheme}".upper()
    for token, label in [
        ("SYG", "Synergy Grants"), ("STG", "Starting Grants"), ("COG", "Consolidator Grants"),
        ("ADG", "Advanced Grants"), ("POC", "Proof of Concept"),
    ]:
        if token in value:
            return label
    return "Unknown ERC"


def _call_year(master_call: str):
    match = re.search(r"ERC-(\d{4})", str(master_call), flags=re.I)
    return int(match.group(1)) if match else None


def _host_text(organisations: pd.DataFrame) -> str:
    entries = []
    for organisation in organisations.itertuples(index=False):
        entries.append(f"{organisation.organisation_name} [{organisation.pic},{organisation.country}]")
    return ", ".join(dict.fromkeys(entries))


def reconcile_dashboard_cordis(
    dashboard: pd.DataFrame,
    cordis_projects: pd.DataFrame,
    organisations: pd.DataFrame,
    v1: pd.DataFrame,
    start_inclusive: str,
    end_exclusive: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    base = dashboard.copy()
    dashboard_ids = set(base.grant_id.astype(str)) if not base.empty else set()
    old = v1.copy()
    if not old.empty:
        old["grant_id"] = normalize_grant_id(old.grant_id)
        old = old.drop_duplicates("grant_id").set_index("grant_id", drop=False)
    projects = cordis_projects.copy()
    if projects.empty:
        audit = pd.DataFrame([{"grant_id": gid, "included": True, "inclusion_reason": "dashboard"} for gid in sorted(dashboard_ids)])
        return base, audit
    projects["grant_id"] = normalize_grant_id(projects.id)
    projects["start_date"] = pd.to_datetime(projects.startDate, errors="coerce")
    funding = projects.fundingScheme.fillna("").astype(str)
    projects = projects[
        funding.str.contains(ERC_SCHEME_PATTERN, case=False, regex=True)
        & (projects.start_date >= pd.Timestamp(start_inclusive))
        & (projects.start_date < pd.Timestamp(end_exclusive))
    ].copy()
    orgs = organisations.copy()
    orgs["grant_id"] = orgs.grant_id.astype(str)
    synthetic = []
    audit_rows = [{"grant_id": gid, "included": True, "inclusion_reason": "dashboard"} for gid in sorted(dashboard_ids)]
    for project in projects.itertuples(index=False):
        grant_id = str(project.grant_id)
        if grant_id in dashboard_ids:
            continue
        project_orgs = orgs[orgs.grant_id == grant_id].copy()
        french = project_orgs[project_orgs.country == "FR"].copy()
        if french.empty:
            continue
        grant_type = _grant_type(project.masterCall, project.fundingScheme)
        if grant_type == "Synergy Grants":
            included, reason = True, "cordis_synergy_fr_component"
        elif french.role.astype(str).str.casefold().eq("coordinator").any():
            included, reason = True, "cordis_fr_coordinator"
        elif not old.empty and grant_id in old.index:
            included, reason = True, "v1_confirmed_transfer"
        else:
            included, reason = False, "foreign_host_fr_participant_only"
        audit_rows.append({"grant_id": grant_id, "included": included, "inclusion_reason": reason})
        if not included:
            continue
        old_row = old.loc[grant_id] if not old.empty and grant_id in old.index else None
        if grant_type == "Synergy Grants":
            host_rows = project_orgs
        else:
            role_rank = french.role.astype(str).str.casefold().map({"coordinator": 0, "participant": 1, "thirdparty": 2}).fillna(3)
            host_rows = french.assign(_rank=role_rank).sort_values(["_rank", "net_eu_contribution"], ascending=[True, False]).head(1)
        amount = pd.to_numeric(project.ecMaxContribution, errors="coerce")
        if pd.isna(amount):
            amount = pd.to_numeric(project_orgs.net_eu_contribution, errors="coerce").sum(min_count=1)
        pi_name = old_row.get("pi_name") if old_row is not None else None
        call_year = old_row.get("call_year") if old_row is not None else _call_year(project.masterCall)
        panel = old_row.get("panel") if old_row is not None else None
        synthetic.append(
            {
                "grant_id": grant_id,
                "programme": "Horizon Europe" if str(project.frameworkProgramme).upper() == "HORIZON" else "Horizon 2020",
                "acronym": project.acronym,
                "project_title": project.title,
                "abstract": project.objective,
                "pi_names_raw": pi_name,
                "host_institutions_raw": _host_text(host_rows),
                "dashboard_country": None,
                "dashboard_region": None,
                "grant_type": grant_type,
                "domain": None,
                "panel": panel,
                "call": project.masterCall,
                "call_year": call_year,
                "start_date": project.start_date,
                "start_year": project.start_date.year,
                "end_date": pd.to_datetime(project.endDate, errors="coerce"),
                "project_eu_contribution": amount,
                "cordis_url": f"https://cordis.europa.eu/project/id/{grant_id}",
                "is_synergy": grant_type == "Synergy Grants",
            }
        )
    synthetic_frame = pd.DataFrame(synthetic, columns=base.columns if not base.empty else None)
    result = pd.concat([base, synthetic_frame], ignore_index=True) if not synthetic_frame.empty else base
    result = result.sort_values(["start_date", "grant_id"]).reset_index(drop=True) if not result.empty else result
    return result, pd.DataFrame(audit_rows)
