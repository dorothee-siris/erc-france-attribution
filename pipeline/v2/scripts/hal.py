from __future__ import annotations

import re
import unicodedata

import pandas as pd


FACET_SEP = "_FacetSep_"
JOIN_SEP = "_JoinSep_"


def normalize_name(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", ascii_value.lower())


def _name_parts(value: str) -> list[str]:
    ascii_value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return [p for p in re.split(r"[^a-z]+", ascii_value.lower()) if p]


def loose_match(a: str, b: str) -> bool:
    """Exact normalized match, else a shared surname-length token (>=4 chars) — order-robust, tolerant
    of accents / middle names / name order. Homonym risk is bounded by the French-structure +
    award-window guards and the corroboration requirement in grading."""
    if normalize_name(a) == normalize_name(b):
        return True
    common = set(_name_parts(a)) & set(_name_parts(b))
    return any(len(t) >= 4 for t in common)


def extract_hal_author_candidates(grant_id: str, pi_name: str, start_year: int, payload: dict) -> pd.DataFrame:
    """HAL author-name route: the PI's HAL deposits (not grant-tagged) reveal their primary structure.
    Aggregates by structure within the award window; corroboration = >=2 supporting deposits.
    source_kind='hal_author' (Grade B via corroboration, not the grant-linked Grade A)."""
    lo, hi = int(start_year) - 1, int(start_year) + 3
    per_structure: dict[str, dict] = {}
    for doc in payload.get("response", {}).get("docs", []):
        year = pd.to_numeric(doc.get("producedDateY_i"), errors="coerce")
        if pd.isna(year) or not (lo <= int(year) <= hi):
            continue
        lab_ids = {str(v) for v in doc.get("labStructId_i", [])}
        for encoded in doc.get("authIdHasPrimaryStructure_fs", []):
            parsed = _parse_author_structure(encoded)
            if not parsed:
                continue
            author, structure_id, structure_name = parsed
            if not loose_match(author, pi_name) or structure_id not in lab_ids:
                continue
            rec = per_structure.setdefault(structure_id, {
                "grant_id": str(grant_id), "pi_name": pi_name, "pi_match": True,
                "lab_name": structure_name, "structure_id": structure_id, "rnsr_id": None,
                "source_kind": "hal_author", "source_family": "hal",
                "source_url": f"https://api.archives-ouvertes.fr/search/?q=authFullName_t:\"{pi_name}\"",
                "award_time": True, "_docs": set(), "_exact": False})
            rec["_docs"].add(str(doc.get("docid", "")))
            rec["_exact"] = rec["_exact"] or (normalize_name(author) == normalize_name(pi_name))
    rows = []
    for rec in per_structure.values():
        docs = rec.pop("_docs")
        exact = rec.pop("_exact")
        rec["source_record_id"] = ";".join(sorted(docs))
        rec["n_supporting_docs"] = len(docs)
        # the PI's OWN primary structure is reliable self-affiliation: accept single deposit when the
        # name matched EXACTLY; require >=2 deposits when the match was only loose (homonym guard).
        rec["independent_corroboration"] = exact or len(docs) >= 2
        rows.append(rec)
    return pd.DataFrame(rows)


def _parse_author_structure(value: str) -> tuple[str, str, str] | None:
    try:
        _, rest = value.split(FACET_SEP, 1)
        author, structure = rest.split(JOIN_SEP, 1)
        structure_id, structure_name = structure.split(FACET_SEP, 1)
        return author.strip(), structure_id.strip(), structure_name.strip()
    except ValueError:
        return None


def extract_hal_candidates(grant_id: str, pi_name: str, start_year: int, payload: dict) -> pd.DataFrame:
    rows = []
    target_name = normalize_name(pi_name)
    for doc in payload.get("response", {}).get("docs", []):
        year = pd.to_numeric(doc.get("producedDateY_i"), errors="coerce")
        lab_ids = {str(value) for value in doc.get("labStructId_i", [])}
        for encoded in doc.get("authIdHasPrimaryStructure_fs", []):
            parsed = _parse_author_structure(encoded)
            if not parsed:
                continue
            author, structure_id, structure_name = parsed
            if normalize_name(author) != target_name or structure_id not in lab_ids:
                continue
            rows.append(
                {
                    "grant_id": str(grant_id),
                    "pi_name": pi_name,
                    "pi_match": True,
                    "lab_name": structure_name,
                    "structure_id": structure_id,
                    "rnsr_id": None,
                    "source_kind": "hal_grant",
                    "source_url": f"https://api.archives-ouvertes.fr/search/?q=europeanProjectReference_s:{grant_id}",
                    "source_record_id": str(doc.get("docid", "")),
                    "publication_year": int(year) if pd.notna(year) else None,
                    "award_time": bool(pd.notna(year) and (int(start_year) - 1 <= int(year) <= int(start_year) + 2)),
                    "independent_corroboration": False,
                }
            )
    return pd.DataFrame(rows)
