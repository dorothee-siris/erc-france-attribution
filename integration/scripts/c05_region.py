"""Phase C step 5: region from RNSR code_postal (fallback: commune, then researched city string via
a targeted city->departement lookup built for the cities actually present in this dataset).

Departement = first 2 digits of the postal code (971-976 DOM: first 3 digits; Corse 20xxx: 2A if
postal in 200xx/201xx (Ajaccio side), 2B if 202xx-209xx (Bastia side) -- ambiguous 20-prefixed codes
route to conflicts rather than guessing). Region taken from the stable 13-region + 5-DOM 2016
nomenclature (unchanged across the whole 2016-2026 window covered by this run) -- reused verbatim
from V2\\scripts\\region.py's canonical name list (imported, never retyped, to guarantee identical
accented spelling / apostrophe style to the rest of the V2 pipeline).

Region is NEVER derived from a tutelle/RTO-HQ name -- only from the performing lab's own location
(RNSR postal/commune, or the researched city string), per the non-negotiable semantics.
"""
from __future__ import annotations

import re

import pandas as pd

from common_io import STAGED, aprint
from region import canon_region as _canon_region  # copied from V2\scripts\region.py (checksummed)

# Index into region.py's _CANON_NAMES (order fixed in that module) so every region string used
# below is byte-identical to the one V2 already validated -- avoids retyping any accented name.
from region import _CANON_NAMES

(IDF, ARA, OCC, PACA, NAQ, GES, BRE, PDL, HDF, NOR, BFC, CVL, COR,
 GUA, MTQ, GUF, REU, MYT) = _CANON_NAMES

# Standard INSEE departement -> region correspondence, 2016 nomenclature (stable through 2026).
DEPT_TO_REGION: dict[str, str] = {
    "01": ARA, "02": HDF, "03": ARA, "04": PACA, "05": PACA, "06": PACA, "07": ARA,
    "08": GES, "09": OCC, "10": GES, "11": OCC, "12": OCC, "13": PACA, "14": NOR,
    "15": ARA, "16": NAQ, "17": NAQ, "18": CVL, "19": NAQ, "2A": COR, "2B": COR,
    "21": BFC, "22": BRE, "23": NAQ, "24": NAQ, "25": BFC, "26": ARA, "27": NOR,
    "28": CVL, "29": BRE, "30": OCC, "31": OCC, "32": OCC, "33": NAQ, "34": OCC,
    "35": BRE, "36": CVL, "37": CVL, "38": ARA, "39": BFC, "40": NAQ, "41": CVL,
    "42": ARA, "43": ARA, "44": PDL, "45": CVL, "46": OCC, "47": NAQ, "48": OCC,
    "49": PDL, "50": NOR, "51": GES, "52": GES, "53": PDL, "54": GES, "55": GES,
    "56": BRE, "57": GES, "58": BFC, "59": HDF, "60": HDF, "61": NOR, "62": HDF,
    "63": ARA, "64": NAQ, "65": OCC, "66": OCC, "67": GES, "68": GES, "69": ARA,
    "70": BFC, "71": BFC, "72": PDL, "73": ARA, "74": ARA, "75": IDF, "76": NOR,
    "77": IDF, "78": IDF, "79": NAQ, "80": HDF, "81": OCC, "82": OCC, "83": PACA,
    "84": PACA, "85": PDL, "86": NAQ, "87": NAQ, "88": GES, "89": BFC, "90": BFC,
    "91": IDF, "92": IDF, "93": IDF, "94": IDF, "95": IDF,
    "971": GUA, "972": MTQ, "973": GUF, "974": REU, "976": MYT,
}

# Targeted city -> departement lookup, built ONLY for the (unambiguous, major) cities actually
# present in this dataset's researched `city` field where RNSR postal/commune is unavailable --
# per task instruction, not an exhaustive gazetteer. Verified against this run's staging table
# (2026-08-27): every city below is unambiguous (single well-known French commune).
CITY_DEPT: dict[str, str] = {
    "paris": "75", "bordeaux": "33", "pessac": "33", "grenoble": "38", "lille": "59",
    "lyon": "69", "marseille": "13", "rennes": "35", "toulouse": "31",
    "gif sur yvette": "91", "fontenay aux roses": "92", "biot": "06",
    "saint priest en jarez": "42", "moulis": "09", "valbonne": "06", "montpellier": "34",
    "strasbourg": "67", "nantes": "44", "nice": "06",
}


def _norm_city(s) -> str:
    import unicodedata
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    a = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii").lower()
    a = re.sub(r"\bcedex\b.*$", "", a)
    return re.sub(r"[^a-z0-9]+", " ", a).strip()


def dept_from_postal(postal) -> tuple[str | None, str | None]:
    """Returns (dept_code, flag) -- flag set when Corse postal is ambiguous (route to conflict)."""
    if postal is None or (isinstance(postal, float) and pd.isna(postal)):
        return None, None
    digits = re.sub(r"\D", "", str(postal))
    if len(digits) < 5:
        return None, None
    if digits[:2] in ("97", "98"):
        return digits[:3], None
    if digits[:2] == "20":
        if digits[:3] in ("200", "201"):
            return "2A", None
        if digits[:3] in ("202", "203", "204", "205", "206"):
            return "2B", None
        return None, "corse_postal_ambiguous"
    return digits[:2], None


CONFLICT_ROWS: list[dict] = []


def add_conflict(component_id, kind, detail):
    CONFLICT_ROWS.append({"component_id": component_id, "conflict_kind": kind, "detail": detail})


def main() -> None:
    aprint("=== c05_region ===")
    st = pd.read_parquet(STAGED / "staging_crosswalked.parquet")

    regions, region_sources, code_postals_out = [], [], []
    for _, row in st.iterrows():
        cid = row.component_id
        region, source, cp_out = None, None, None

        cp = row.get("rnsr_code_postal")
        dept, flag = dept_from_postal(cp)
        if flag == "corse_postal_ambiguous":
            add_conflict(cid, "ambiguous_corse_postal", f"code_postal={cp!r}: cannot tell 2A vs 2B")
        if dept and dept in DEPT_TO_REGION:
            region, source, cp_out = DEPT_TO_REGION[dept], "rnsr_postal", cp

        if region is None:
            commune = row.get("rnsr_commune")
            nc = _norm_city(commune)
            if nc in CITY_DEPT:
                dept = CITY_DEPT[nc]
                region, source = DEPT_TO_REGION.get(dept), "rnsr_commune"

        if region is None:
            nc = _norm_city(row.get("city"))
            if nc in CITY_DEPT:
                dept = CITY_DEPT[nc]
                # S7a: c02's evidence-hint pass marks city_from_hint=True when it set/overrode
                # `city` from an explicit-confidence harvested hint rather than the original
                # web-research pass -- label the provenance accordingly (task spec:
                # "explicit-confidence hints may set city with region_source='evidence_city'").
                region = DEPT_TO_REGION.get(dept)
                source = "evidence_city" if row.get("city_from_hint") is True else "researched_city"

        if region is None and row.get("integration_action") != "NO_FRENCH_ATTRIBUTION" and (
                pd.notna(cp) or pd.notna(row.get("rnsr_commune")) or pd.notna(row.get("city"))):
            add_conflict(cid, "ambiguous_or_unresolved_location",
                         f"code_postal={cp!r}, rnsr_commune={row.get('rnsr_commune')!r}, "
                         f"city={row.get('city')!r}: none resolvable via postal/commune/city lookup")

        region = _canon_region(region)
        regions.append(region)
        region_sources.append(source)
        code_postals_out.append(cp_out)

    st["region"] = regions
    st["region_source"] = region_sources
    st["code_postal"] = code_postals_out

    st.to_parquet(STAGED / "staging_regioned.parquet", index=False)
    aprint(f"wrote staged/staging_regioned.parquet ({len(st)} rows)")
    aprint(f"region resolved: {st.region.notna().sum()} / {len(st)}")
    aprint("region_source distribution:")
    aprint(st.region_source.value_counts(dropna=False).to_string())
    aprint("region distribution:")
    aprint(st.region.value_counts(dropna=False).to_string())

    conflicts = pd.DataFrame(CONFLICT_ROWS, columns=["component_id", "conflict_kind", "detail"])
    conflicts.to_csv(STAGED / "phase_c_conflicts_region.csv", index=False, encoding="utf-8")
    aprint(f"wrote staged/phase_c_conflicts_region.csv ({len(conflicts)} rows)")
    aprint("c05 done.")


if __name__ == "__main__":
    main()
