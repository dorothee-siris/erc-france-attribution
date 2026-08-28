"""Phase C step 3: for each RNSR-linked row, derive tutelles AT THE GRANT START DATE.

Rule (non-negotiable): start_year <= 2017 -> historical.parquet at annee==start_year (nearest
+/-1 year if the exact year is missing for that structure, flagged historical_year_gap; if still
nothing, fall back to active + crosswalk, flagged historical_fallback_to_active).
start_year >= 2018 -> active.parquet tutelles (crosswalk correction applied later by c04; if the
structure isn't in the active snapshot at all -- e.g. only ever linked via unit_id_historical --
fall back to the nearest historical year, flagged active_missing_fallback_to_historical).

Buckets (TUTE type only; PART entries -> participants_nontutelle, never credited):
  universities_at_start (nature UNIV / historical UNIV+UT) -- never converted from RTO,
  rto_tutelles (EPST/EPIC) -- CNRS/INSERM/CEA/Inria/INRAE/IRD/Pasteur etc, kept separate,
  other_etab_tutelles (everything else TUTE, e.g. grandes ecoles, foundations, hospitals).

RNSR commune/code_postal (for c05 region) are pulled from the ACTIVE snapshot for the linked
structure id regardless of which format supplied the tutelles -- labs essentially never change
city, so this is not subject to the same start-date gating as tutelle credit; if the structure is
absent from active (historical-only), city falls back to the researched `city` staging field.
"""
from __future__ import annotations

import pandas as pd

from common_io import RNSR_DIR, STAGED, aprint
from tutelle_align import (
    build_name_nature_dict,
    build_sigle_name_dict,
    build_sigle_nature_dict,
    parse_active_row,
    parse_historical_row,
)

CONFLICT_ROWS: list[dict] = []


def add_conflict(component_id, kind, detail):
    CONFLICT_ROWS.append({"component_id": component_id, "conflict_kind": kind, "detail": detail})


def bucket_lists(tutelle_recs: list[dict]) -> dict:
    """Bucket tutelle records; entries whose NAME could not be recovered (positional
    UNKNOWN_NAME[...] placeholder from tutelle_align) are dropped from every credit-bearing
    bucket rather than exported as a fake citable name -- we can know a UNIV-nature tutelle
    existed at a position without being able to say which one, and that is not a claim we make.
    Dropped entries are still counted (unresolved_tutelle_count) so the row is auditable."""
    univ, rto, other, part = [], [], [], []
    unresolved = 0
    for t in tutelle_recs:
        name = t.get("name") or ""
        if name.startswith("UNKNOWN_NAME["):
            unresolved += 1
            continue
        if t.get("type_code") == "PART":
            part.append(name)
            continue
        if t.get("type_code") != "TUTE":
            continue  # unknown/unaligned type -> not credited, not counted as participant either
        b = t.get("bucket")
        if b == "university":
            univ.append(name)
        elif b == "rto":
            rto.append(name)
        else:
            other.append(name)
    return {"universities_at_start": univ, "rto_tutelles": rto, "other_etab_tutelles": other,
            "participants_nontutelle": part, "unresolved_tutelle_count": unresolved}


def main() -> None:
    aprint("=== c03_tutelles_at_start ===")
    linked = pd.read_parquet(STAGED / "staging_linked.parquet")
    active = pd.read_parquet(RNSR_DIR / "active.parquet")
    historical = pd.read_parquet(RNSR_DIR / "historical.parquet")
    active_by_id = active.set_index("numero_national_de_structure", drop=False)
    hist_by_id = historical.groupby("numero_national_de_structure")

    sigle_dict = build_sigle_name_dict(active, historical)
    aprint(f"global sigle->name dictionary: {len(sigle_dict)} entries")
    # S7f: fixes the historical_nature_code_misaligned bucketing bug -- see tutelle_align.py
    # module docstring ("THE BUCKETING BUG" / "THE FIX") for the diagnosis. These are built once
    # from every row (active + historical) where the row's own type/nature columns already agree
    # in length with the names list, i.e. exclusively from associations already self-verified.
    name_nature_dict = build_name_nature_dict(active, historical)
    sigle_nature_dict = build_sigle_nature_dict(active, historical)
    aprint(f"global name->nature dictionary: {len(name_nature_dict)} entries")
    aprint(f"global sigle->nature dictionary: {len(sigle_nature_dict)} entries")

    out_cols = {
        "universities_at_start": [], "rto_tutelles": [], "other_etab_tutelles": [],
        "participants_nontutelle": [], "tutelle_source": [], "tutelle_flags": [],
        "rnsr_commune": [], "rnsr_code_postal": [], "crosswalk_pending": [],
        "unresolved_tutelle_count": [],
    }

    for _, row in linked.iterrows():
        cid = row.component_id
        rid = row.rnsr_id

        # S7a: linked_non_rnsr rows (Institut Pasteur / Inria / EURECOM / CEA patterns, task step
        # 5) have no rnsr_id by construction -- c02's evidence-hint pass already computed their
        # final tutelle buckets (nonrnsr_* columns) directly from evidence, so just carry those
        # through unchanged rather than running the RNSR historical/active lookup below.
        def _as_list(v):
            # after a parquet round-trip an empty/absent list column comes back as None or a
            # numpy array rather than a plain list; numpy arrays have no unambiguous truthiness
            # (even when empty, as of a recent numpy deprecation), so `v or []` is unsafe here.
            if v is None:
                return []
            if isinstance(v, list):
                return v
            return list(v)

        if not rid and row.get("location_status") == "linked_non_rnsr":
            out_cols["universities_at_start"].append(_as_list(row.get("nonrnsr_universities_at_start")))
            out_cols["rto_tutelles"].append(_as_list(row.get("nonrnsr_rto_tutelles")))
            out_cols["other_etab_tutelles"].append(_as_list(row.get("nonrnsr_other_etab_tutelles")))
            out_cols["participants_nontutelle"].append(_as_list(row.get("nonrnsr_participants_nontutelle")))
            out_cols["tutelle_source"].append(row.get("nonrnsr_tutelle_source"))
            out_cols["tutelle_flags"].append(row.get("hint_flags"))
            out_cols["rnsr_commune"].append(None)
            out_cols["rnsr_code_postal"].append(None)
            out_cols["crosswalk_pending"].append(False)
            out_cols["unresolved_tutelle_count"].append(0)
            continue

        if not rid:
            list_cols = ("universities_at_start", "rto_tutelles", "other_etab_tutelles", "participants_nontutelle")
            for k in out_cols:
                if k in list_cols:
                    out_cols[k].append([])
                elif k == "crosswalk_pending":
                    out_cols[k].append(False)
                elif k == "unresolved_tutelle_count":
                    out_cols[k].append(0)
                else:
                    out_cols[k].append(None)
            continue

        start_year = int(row.start_year) if pd.notna(row.start_year) else None
        # S7a: carry c02's evidence-hint flag (e.g. 'city_confirmed_from_evidence') into the same
        # tutelle_flags pipe-string the rest of this loop builds, so it survives to the final CSV.
        flags: list[str] = [row.get("hint_flags")] if isinstance(row.get("hint_flags"), str) else []
        recs: list[dict] = []
        tutelle_source = None
        crosswalk_pending = False

        def _hist_recs_for_year(rid_, year):
            if rid_ not in hist_by_id.groups:
                return None, None
            g = hist_by_id.get_group(rid_)
            exact = g[g.annee.astype(str) == str(year)]
            if not exact.empty:
                return (parse_historical_row(exact.iloc[0], sigle_dict, name_nature_dict, sigle_nature_dict),
                        f"historical_rnsr_{year}")
            g = g.copy()
            g["year_int"] = g.annee.astype(str).str.extract(r"(\d{4})").astype(float)
            g["year_diff"] = (g["year_int"] - year).abs()
            near = g[g["year_diff"] <= 1].sort_values("year_diff")
            if not near.empty:
                yr_used = int(near.iloc[0]["year_int"])
                return (parse_historical_row(near.iloc[0], sigle_dict, name_nature_dict, sigle_nature_dict),
                        f"historical_rnsr_{yr_used}_nearest")
            return None, None

        if start_year is not None and start_year <= 2017:
            parsed, tutelle_source = _hist_recs_for_year(rid, start_year)
            if parsed is None:
                if rid in active_by_id.index:
                    arow = active_by_id.loc[rid]
                    if isinstance(arow, pd.DataFrame):
                        arow = arow.iloc[0]
                    parsed = parse_active_row(arow, sigle_dict)
                    tutelle_source = "active_rnsr+crosswalk_fallback_no_historical"
                    flags.append("historical_fallback_to_active")
                    crosswalk_pending = True
                    add_conflict(cid, "historical_fallback_to_active",
                                 f"rnsr_id={rid}, start_year={start_year}: no historical record within +/-1 year; used active snapshot instead (undated)")
                else:
                    flags.append("no_historical_and_no_active_record")
                    add_conflict(cid, "undatable_tutelle",
                                 f"rnsr_id={rid}, start_year={start_year}: no historical record and structure absent from active snapshot")
            elif tutelle_source and tutelle_source.endswith("_nearest"):
                flags.append("historical_year_gap")
                add_conflict(cid, "historical_year_gap",
                             f"rnsr_id={rid}, start_year={start_year}: exact annee missing, used {tutelle_source}")
            if parsed is not None:
                recs = parsed.get("tutelles", [])
                flags.extend(parsed.get("flags", []))
        elif start_year is not None:
            if rid in active_by_id.index:
                arow = active_by_id.loc[rid]
                if isinstance(arow, pd.DataFrame):
                    arow = arow.iloc[0]
                parsed = parse_active_row(arow, sigle_dict)
                recs = parsed.get("tutelles", [])
                flags.extend(parsed.get("flags", []))
                tutelle_source = "active_rnsr"
                crosswalk_pending = True  # c04 will check per-university event dates; no-op if none apply
            else:
                parsed, tutelle_source = _hist_recs_for_year(rid, 2017)
                if parsed is not None:
                    flags.append("active_missing_fallback_to_historical")
                    tutelle_source = (tutelle_source or "historical_rnsr") + "_fallback_active_missing"
                    add_conflict(cid, "active_missing_fallback_to_historical",
                                 f"rnsr_id={rid}, start_year={start_year}: structure absent from active snapshot, used nearest historical year instead")
                    recs = parsed.get("tutelles", [])
                    flags.extend(parsed.get("flags", []))
                else:
                    flags.append("no_active_and_no_historical_record")
                    add_conflict(cid, "undatable_tutelle",
                                 f"rnsr_id={rid}, start_year={start_year}: structure absent from both active and historical")

        buckets = bucket_lists(recs)
        for k, v in buckets.items():
            out_cols[k].append(v)
        out_cols["tutelle_source"].append(tutelle_source)
        out_cols["tutelle_flags"].append("|".join(flags) if flags else None)
        out_cols["crosswalk_pending"].append(crosswalk_pending)

        if rid in active_by_id.index:
            arow = active_by_id.loc[rid]
            if isinstance(arow, pd.DataFrame):
                arow = arow.iloc[0]
            out_cols["rnsr_commune"].append(arow.get("commune"))
            out_cols["rnsr_code_postal"].append(arow.get("code_postal"))
        else:
            out_cols["rnsr_commune"].append(None)
            out_cols["rnsr_code_postal"].append(None)

        if any("unrecoverable" in f for f in flags):
            add_conflict(cid, "tutelle_name_unrecoverable",
                         f"rnsr_id={rid}: some tutelle name(s) could not be recovered from either direct split or sigle lookup")

    for k, v in out_cols.items():
        linked[k] = v

    linked.to_parquet(STAGED / "staging_tutelles.parquet", index=False)
    aprint(f"wrote staged/staging_tutelles.parquet ({len(linked)} rows)")

    n_with_univ = sum(1 for u in out_cols["universities_at_start"] if u)
    aprint(f"rows with >=1 university_at_start: {n_with_univ}")
    aprint(f"rows with crosswalk_pending: {sum(out_cols['crosswalk_pending'])}")
    src_counts = pd.Series([s for s in out_cols["tutelle_source"] if s]).value_counts()
    aprint("tutelle_source distribution:")
    aprint(src_counts.to_string())

    conflicts = pd.DataFrame(CONFLICT_ROWS)
    conflicts.to_csv(STAGED / "phase_c_conflicts_tutelles.csv", index=False, encoding="utf-8")
    aprint(f"wrote staged/phase_c_conflicts_tutelles.csv ({len(conflicts)} rows)")
    aprint("c03 done.")


if __name__ == "__main__":
    main()
