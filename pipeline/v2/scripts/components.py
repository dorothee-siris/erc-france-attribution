from __future__ import annotations

import re

import pandas as pd


HOST_PATTERN = re.compile(r"\s*(.*?)\s*\[([^,\]]+),([A-Za-z]{2})\]\s*(?:,|$)")


def parse_host_entries(value: str | None) -> list[dict[str, str]]:
    if not value or pd.isna(value):
        return []
    entries = []
    for match in HOST_PATTERN.finditer(str(value)):
        entries.append({"host_name": match.group(1).strip(), "host_pic": match.group(2).strip(), "host_country": match.group(3).upper()})
    return entries


def parse_pi_names(value: str | None) -> list[str]:
    if not value or pd.isna(value):
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _organisation_amounts(organisations: pd.DataFrame, grant_id: str) -> dict[str, float]:
    if organisations.empty or "grant_id" not in organisations.columns:
        return {}
    subset = organisations[(organisations.grant_id.astype(str) == str(grant_id)) & (organisations.country.astype(str).str.upper() == "FR")].copy()
    if subset.empty:
        return {}
    subset["net_eu_contribution"] = pd.to_numeric(subset.net_eu_contribution, errors="coerce")
    return subset.dropna(subset=["net_eu_contribution"]).groupby(subset.pic.astype(str)).net_eu_contribution.sum().to_dict()


def _french_organisations(organisations: pd.DataFrame, grant_id: str) -> pd.DataFrame:
    if organisations.empty or "grant_id" not in organisations.columns:
        return pd.DataFrame()
    subset = organisations[(organisations.grant_id.astype(str) == str(grant_id)) & (organisations.country.astype(str).str.upper() == "FR")].copy()
    if subset.empty:
        return subset
    subset["net_eu_contribution"] = pd.to_numeric(subset.net_eu_contribution, errors="coerce")
    subset["_pic"] = subset.pic.astype(str)
    aggregation = {"net_eu_contribution": "sum"}
    if "organisation_name" in subset:
        aggregation["organisation_name"] = "first"
    return subset.groupby("_pic", as_index=False).agg(aggregation)


def build_components(spine: pd.DataFrame, organisations: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for grant in spine.itertuples(index=False):
        pis = parse_pi_names(grant.pi_names_raw)
        hosts = parse_host_entries(grant.host_institutions_raw)
        is_synergy = grant.grant_type == "Synergy Grants"
        if not is_synergy:
            host = hosts[0] if hosts else {"host_name": grant.host_institutions_raw, "host_pic": None, "host_country": None}
            rows.append(
                {
                    "component_id": f"{grant.grant_id}:0",
                    "grant_id": str(grant.grant_id),
                    "acronym": grant.acronym,
                    "pi_name": pis[0] if pis else grant.pi_names_raw,
                    "starting_host": host["host_name"],
                    "host_pic": host["host_pic"],
                    "host_country": host["host_country"],
                    "project_eu_contribution": float(grant.project_eu_contribution),
                    "french_component_amount": float(grant.project_eu_contribution),
                    "amount_method": "ordinary_full_project",
                    "start_date": grant.start_date,
                    "call_year": grant.call_year,
                    "transfer_review": host["host_country"] not in (None, "FR"),
                }
            )
            continue

        aligned = len(pis) == len(hosts) and bool(pis)
        fr_pairs = [(pi, host) for pi, host in zip(pis, hosts) if host["host_country"] == "FR"] if aligned else []
        exact = _organisation_amounts(organisations, str(grant.grant_id))
        if not aligned and exact:
            french_orgs = _french_organisations(organisations, str(grant.grant_id))
            for index, organisation in enumerate(french_orgs.itertuples(index=False)):
                pic = str(getattr(organisation, "_pic", getattr(organisation, "pic", "")))
                rows.append(
                    {
                        "component_id": f"{grant.grant_id}:{index}",
                        "grant_id": str(grant.grant_id),
                        "acronym": grant.acronym,
                        "pi_name": None,
                        "starting_host": getattr(organisation, "organisation_name", None),
                        "host_pic": pic,
                        "host_country": "FR",
                        "project_eu_contribution": float(grant.project_eu_contribution),
                        "french_component_amount": float(organisation.net_eu_contribution),
                        "amount_method": "cordis_exact_host_pi_unknown",
                        "start_date": grant.start_date,
                        "call_year": grant.call_year,
                        "transfer_review": False,
                    }
                )
            continue
        exact_total = sum(exact.values())
        matched_total = sum(exact.get(host["host_pic"], 0.0) for _, host in fr_pairs)
        unmatched_exact = max(exact_total - matched_total, 0.0)
        for index, (pi, host) in enumerate(fr_pairs):
            if exact_total:
                direct = exact.get(host["host_pic"], 0.0)
                amount = direct + (unmatched_exact / len(fr_pairs) if fr_pairs else 0.0)
                method = "cordis_exact_host" if unmatched_exact == 0 else "cordis_fr_total_split_equal"
            else:
                amount = float(grant.project_eu_contribution) / max(len(pis), 1)
                method = "pi_fraction_fallback"
            rows.append(
                {
                    "component_id": f"{grant.grant_id}:{index}",
                    "grant_id": str(grant.grant_id),
                    "acronym": grant.acronym,
                    "pi_name": pi,
                    "starting_host": host["host_name"],
                    "host_pic": host["host_pic"],
                    "host_country": "FR",
                    "project_eu_contribution": float(grant.project_eu_contribution),
                    "french_component_amount": amount,
                    "amount_method": method,
                    "start_date": grant.start_date,
                    "call_year": grant.call_year,
                    "transfer_review": False,
                }
            )
    return pd.DataFrame(rows)
