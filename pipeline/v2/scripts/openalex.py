from __future__ import annotations

import re

import pandas as pd

from hal import normalize_name


LAB_PATTERN = re.compile(r"\b(laboratoire|laboratory|institut|institute|centre|center|unit[eé]|umr|uar|ums)\b", re.I)
RTO_NAMES = {normalize_name(value) for value in ["CNRS", "INSERM", "CEA", "INRIA", "INRAE", "IRD", "CIRAD"]}


def _extract_lab(raw: str) -> str | None:
    parts = [part.strip() for part in str(raw).split(",") if part.strip()]
    for part in parts:
        if LAB_PATTERN.search(part) and normalize_name(part) not in RTO_NAMES:
            return part
    return None


def pick_fr_author(authors_payload: dict, pi_name: str) -> str | None:
    """From an OpenAlex /authors search, pick the author whose name matches and has a FR institution."""
    target = normalize_name(pi_name)
    results = authors_payload.get("results", []) or []
    named = [a for a in results if normalize_name(a.get("display_name", "")) == target]
    for author in named or results[:1]:
        insts = author.get("last_known_institutions") or author.get("last_known_institution") or []
        if isinstance(insts, dict):
            insts = [insts]
        if any((i or {}).get("country_code") == "FR" for i in insts):
            return (author.get("id") or "").split("/")[-1] or None
    return (named[0]["id"].split("/")[-1]) if named else None


def extract_author_candidates(grant_id: str, pi_name: str, start_year: int, works_payload: dict) -> pd.DataFrame:
    """PI-author route: the author's OWN works in start_year-1..+2 reveal their French lab even when the
    grant has no award-linked works yet (recent grants). source_kind='openalex_author'."""
    df = extract_openalex_candidates(grant_id, pi_name, start_year, works_payload)
    if df.empty:
        return df
    df["source_kind"] = "openalex_author"
    df["source_url"] = f"https://api.openalex.org/works?filter=authorships.author.id:<{normalize_name(pi_name)}>"
    return df


def extract_openalex_candidates(grant_id: str, pi_name: str, start_year: int, payload: dict) -> pd.DataFrame:
    target = normalize_name(pi_name)
    occurrences: dict[str, dict] = {}
    for work in payload.get("results", []):
        year = pd.to_numeric(work.get("publication_year"), errors="coerce")
        if pd.isna(year) or not (int(start_year) - 1 <= int(year) <= int(start_year) + 2):
            continue
        for authorship in work.get("authorships", []) or []:
            author = (authorship.get("author") or {}).get("display_name", "")
            if normalize_name(author) != target:
                continue
            institutions = authorship.get("institutions", []) or []
            if not any(institution.get("country_code") == "FR" for institution in institutions):
                continue
            for raw in authorship.get("raw_affiliation_strings", []) or []:
                lab = _extract_lab(raw)
                if not lab:
                    continue
                key = normalize_name(lab)
                record = occurrences.setdefault(
                    key,
                    {
                        "grant_id": str(grant_id),
                        "pi_name": pi_name,
                        "pi_match": True,
                        "lab_name": lab,
                        "rnsr_id": None,
                        "source_kind": "openalex_grant",
                        "source_url": f"https://api.openalex.org/works?filter=awards.funder_award_id:{grant_id}",
                        "award_time": True,
                        "work_ids": set(),
                    },
                )
                record["work_ids"].add(str(work.get("id", "")))
    rows = []
    for record in occurrences.values():
        work_ids = sorted(record.pop("work_ids"))
        record["source_record_ids"] = ";".join(work_ids)
        record["n_supporting_works"] = len(work_ids)
        record["independent_corroboration"] = len(work_ids) >= 2
        rows.append(record)
    return pd.DataFrame(rows)
