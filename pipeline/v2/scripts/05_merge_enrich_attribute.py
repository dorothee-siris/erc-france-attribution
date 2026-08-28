"""Merge all candidate evidence (v1 seed + HAL + OpenAlex), grade cross-source, link RNSR, enrich
region/tutelles, and attribute funding under BOTH lenses (fractional 1/N + full-claim). Deterministic,
no model calls.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata

import pandas as pd
import requests

from attribution import build_fractional_claims, build_fullclaim_claims, reconcile_claims
from common import V2_ROOT, ensure_v2_path, load_config
from region import canon_region as _canon_region
from resolution import choose_resolution
from rnsr_link import apply_links

cfg = load_config()
date = cfg["snapshot_date"]
CAND_COLS = ["component_id", "grant_id", "pi_name", "pi_match", "award_time", "lab_name", "rnsr_id",
             "tutelles_candidate", "city", "source_kind", "source_family", "independent_corroboration", "source_url"]


def _load_candidates() -> pd.DataFrame:
    frames = []
    for name, family in (("v1_candidates.parquet", "v1"), ("hal_candidates.parquet", "hal"),
                         ("hal_author_candidates.parquet", "hal"), ("openalex_candidates.parquet", "openalex")):
        p = ensure_v2_path(V2_ROOT / "checkpoints" / name)
        if not p.exists():
            continue
        d = pd.read_parquet(p)
        if d.empty:
            continue
        if "source_family" not in d.columns:
            d["source_family"] = family
        if family == "hal" and "lab_address" in d.columns:
            d["city"] = d.get("city", d["lab_address"])
        for col in CAND_COLS:
            if col not in d.columns:
                d[col] = None
        frames.append(d[CAND_COLS])
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=CAND_COLS)


def _split(value, sep):
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    return [x.strip() for x in re.split(sep, str(value)) if x.strip()]


# ---- resolve (cross-source) + RNSR link ----
_BASE = ["component_id", "grant_id", "acronym", "pi_name", "starting_host", "host_pic", "host_country",
         "project_eu_contribution", "french_component_amount", "amount_method", "start_date",
         "call_year", "transfer_review"]
components = pd.read_parquet(ensure_v2_path(V2_ROOT / "outputs" / "french_components.parquet"))
components = components[[c for c in _BASE if c in components.columns]]  # keep only base cols -> idempotent re-runs

active_path = ensure_v2_path(V2_ROOT / "data" / "raw" / "rnsr" / date / "active.parquet")
active = pd.read_parquet(active_path) if active_path.exists() else pd.DataFrame()

candidates = _load_candidates()
if not candidates.empty:
    candidates = apply_links(candidates, active)  # RNSR-link candidates BEFORE grading so cross-source agreement works
resolutions = choose_resolution(candidates) if not candidates.empty else pd.DataFrame()
if not resolutions.empty:
    keep = [c for c in ["component_id", "lab_name", "rnsr_id", "tutelles_candidate", "city", "source_kind",
                        "source_url", "evidence_grade", "review_status", "agreeing_families", "conflict"] if c in resolutions]
    components = components.merge(resolutions[keep], on="component_id", how="left")
for col, default in (("evidence_grade", "unresolved"), ("review_status", "manual_review")):
    if col not in components.columns:
        components[col] = default
    components[col] = components[col].fillna(default)

# ---- enrich: RNSR tutelles (comma-split!) + commune + region (geo.api, cached); candidate fallback ----
active_index = active.set_index("numero_national_de_structure", drop=False) if not active.empty else pd.DataFrame()
geo_path = ensure_v2_path(V2_ROOT / "checkpoints" / "cache" / "commune_regions.json")
geo_path.parent.mkdir(parents=True, exist_ok=True)
geo = json.loads(geo_path.read_text(encoding="utf-8")) if geo_path.exists() else {}


def _region(place, postcode=None):
    """Resolve a commune to (code_insee, region_name). Prefer an exact INSEE postal-code lookup when a
    5-digit code is available (RNSR carries one) — this disambiguates same-name communes across
    departments (e.g. Saint-Denis 93200 Île-de-France vs 97400 La Réunion, which a population-boosted
    name search wrongly resolves to Réunion). Falls back to a population-boosted name search."""
    pc = re.sub(r"\D", "", str(postcode)) if postcode and not pd.isna(postcode) else ""
    if len(pc) == 5:
        key = f"cp:{pc}"
        if key not in geo:
            try:
                r = requests.get("https://geo.api.gouv.fr/communes",
                                 params={"codePostal": pc, "fields": "nom,code,region"}, timeout=30)
                r.raise_for_status()
                res = r.json()
                geo[key] = res[0] if res else None
                time.sleep(0.05)
            except requests.RequestException:
                geo[key] = None
        g = geo.get(key)
        if g:
            return g.get("code"), (g.get("region") or {}).get("nom")
        # CEDEX codes (e.g. 93526) return no commune -> fall back to the DEPARTMENT, which is enough
        # for region. Overseas departments are 3-digit (97x/98x); mainland 2-digit. This is what fixes
        # Saint-Denis-93526 (Seine-Saint-Denis / Île-de-France) being read as La Réunion.
        dep = pc[:3] if pc[:2] in ("97", "98") else pc[:2]
        dkey = f"dep:{dep}"
        if dkey not in geo:
            try:
                r = requests.get(f"https://geo.api.gouv.fr/departements/{dep}",
                                 params={"fields": "nom,region"}, timeout=30)
                geo[dkey] = r.json() if r.status_code == 200 else None
                time.sleep(0.05)
            except requests.RequestException:
                geo[dkey] = None
        d = geo.get(dkey)
        if d and d.get("region"):
            return None, d["region"].get("nom")
    q = re.sub(r"\bCEDEX\b.*$", "", str(place), flags=re.I).strip() if place and not pd.isna(place) else ""
    q = re.sub(r"\s+", " ", q)
    if not q:
        return None, None
    if q not in geo:
        try:
            r = requests.get("https://geo.api.gouv.fr/communes",
                             params={"nom": q, "fields": "nom,code,region", "boost": "population", "limit": 1}, timeout=30)
            r.raise_for_status()
            res = r.json()
            geo[q] = res[0] if res else None
            time.sleep(0.05)
        except requests.RequestException:
            geo[q] = None
    g = geo.get(q)
    return (g.get("code") if g else None), ((g.get("region") or {}).get("nom") if g else None)


spine0 = pd.read_parquet(ensure_v2_path(V2_ROOT / "outputs" / "canonical_spine.parquet"))
dash_region = ({str(g): re.sub(r"\s*\(.*\)\s*$", "", str(rg)).strip()
                for g, rg in zip(spine0.grant_id.astype(str), spine0.dashboard_region)}
               if "dashboard_region" in spine0 else {})
# covers French names, English dashboard names, and parenthesised acronyms
_RTO_HOSTS = ("centre national de la recherche", "national centre for scientific research", "cnrs",
              "institut national de la sante", "national institute of health and medical research", "inserm",
              "commissariat a l", "alternative energies and atomic energy", "cea",
              "national institute for research in computer science", "inria",
              "recherche en sciences et technologies du num",
              "recherche pour l agriculture", "national research institute for agriculture", "inrae",
              "recherche pour le developpement", "institute of research for development", "ird",
              "cooperation internationale en recherche agronomique", "cirad",
              "institut pasteur", "pasteur institute")


def _is_rto(host):
    h = _norm_host(host)
    return any(k in h for k in _RTO_HOSTS)


def _norm_host(v):
    import unicodedata
    return unicodedata.normalize("NFKD", str(v)).encode("ascii", "ignore").decode("ascii").lower()




rows = []
for c in components.to_dict("records"):
    rid = c.get("rnsr_id")
    act = active_index.loc[rid] if rid and not active.empty and rid in active_index.index else None
    if isinstance(act, pd.DataFrame):
        act = act.iloc[0]
    if act is not None:
        c["tutelles"] = _split(act.get("tutelles"), r"[;,]")
        c["lab_name_rnsr"] = act.get("libelle")
        c["commune"] = act.get("commune")
        c["code_postal"] = act.get("code_postal")
        c["unit_type"] = act.get("type_de_structure")
    else:
        c["tutelles"] = _split(c.get("tutelles_candidate"), r"[;]")
        c["lab_name_rnsr"] = None
        c["commune"] = None
        c["code_postal"] = None
        c["unit_type"] = None
    place = c.get("commune") or c.get("city")
    c["commune_code"], c["region"] = _region(place, c.get("code_postal"))
    if not c["region"] and not _is_rto(c.get("starting_host")):
        c["region"] = dash_region.get(str(c["grant_id"]))  # non-RTO: dashboard region == host region (safe)
    c["region"] = _canon_region(c["region"])
    c["site"] = c.get("commune") or c.get("city")
    rows.append(c)

geo_path.write_text(json.dumps(geo, ensure_ascii=False, indent=2), encoding="utf-8")
enriched = pd.DataFrame(rows)

# is_synergy from spine (fallback: grant appears in >1 component)
syn = dict(zip(spine0.grant_id.astype(str), spine0.is_synergy)) if "is_synergy" in spine0 else {}
multi = enriched.grant_id.astype(str).value_counts()
enriched["is_synergy"] = enriched.grant_id.astype(str).map(lambda g: bool(syn.get(g, multi.get(g, 1) > 1)))
enriched.to_parquet(ensure_v2_path(V2_ROOT / "outputs" / "french_components.parquet"), compression="zstd", index=False)
enriched.to_csv(ensure_v2_path(V2_ROOT / "outputs" / "french_components.csv"), index=False, encoding="utf-8")

# ---- attribution: both lenses ----
resolved = enriched[enriched.review_status == "auto_accepted"].copy()
frac = build_fractional_claims(resolved)
full = build_fullclaim_claims(resolved)
reconcile_claims(resolved, frac)  # asserts fractional sums to component totals
frac.to_parquet(ensure_v2_path(V2_ROOT / "outputs" / "fractional_claims.parquet"), compression="zstd", index=False)


def _rollup(key):
    f = frac.groupby(key, dropna=False).agg(grants=("grant_id", "nunique"),
                                            eur_fractional=("fractional_amount", "sum")).reset_index()
    # split fractional € by evidence grade so consumers see how much rests on grant-linked (A)
    # vs corroboration-only (B) evidence — A is authoritative, B is heuristic.
    if "evidence_grade" in frac.columns:
        byg = (frac.assign(g=frac.evidence_grade.where(frac.evidence_grade.isin(["A", "B"]), "other"))
               .pivot_table(index=key, columns="g", values="fractional_amount", aggfunc="sum", dropna=False)
               .reset_index())
        for col, out in (("A", "eur_fractional_gradeA"), ("B", "eur_fractional_gradeB")):
            f = f.merge(byg[[key, col]].rename(columns={col: out}) if col in byg.columns
                        else pd.DataFrame({key: [], out: []}), on=key, how="left")
    if not full.empty:
        fc = full.groupby(key, dropna=False).agg(eur_fullclaim=("fullclaim_amount", "sum")).reset_index()
        f = f.merge(fc, on=key, how="outer")
    else:
        f["eur_fullclaim"] = 0.0
    for c in ("eur_fractional_gradeA", "eur_fractional_gradeB"):
        if c in f.columns:
            f[c] = f[c].fillna(0.0)
    return f.sort_values("eur_fractional", ascending=False)


_rollup("region").to_csv(ensure_v2_path(V2_ROOT / "outputs" / "region_funding.csv"), index=False, encoding="utf-8")
_rollup("tutelle").rename(columns={"tutelle": "university"}).to_csv(ensure_v2_path(V2_ROOT / "outputs" / "university_funding.csv"), index=False, encoding="utf-8")
frac.groupby("region", dropna=False).agg(grants=("grant_id", "nunique"), eur_fractional=("fractional_amount", "sum")).reset_index().to_csv(ensure_v2_path(V2_ROOT / "outputs" / "site_funding.csv"), index=False, encoding="utf-8")

evid = [c for c in ["component_id", "grant_id", "pi_name", "lab_name", "rnsr_id", "region", "tutelles",
                    "source_kind", "source_url", "evidence_grade", "review_status", "agreeing_families", "conflict"] if c in enriched]
enriched[evid].to_csv(ensure_v2_path(V2_ROOT / "outputs" / "evidence_provenance.csv"), index=False, encoding="utf-8")
enriched[enriched.review_status != "auto_accepted"].to_csv(ensure_v2_path(V2_ROOT / "outputs" / "manual_review_queue.csv"), index=False, encoding="utf-8")

report = {
    "components": len(enriched),
    "auto_accepted": int((enriched.review_status == "auto_accepted").sum()),
    "resolved_pct": round(100 * (enriched.review_status == "auto_accepted").mean(), 1),
    "grade_A": int((enriched.evidence_grade == "A").sum()),
    "grade_B": int((enriched.evidence_grade == "B").sum()),
    "rnsr_resolved": int(enriched.rnsr_id.notna().sum()),
    "region_resolved": int(enriched.region.notna().sum()),
    "conflicts": int(enriched.get("conflict", pd.Series(dtype=bool)).fillna(False).sum()),
    "by_source": enriched[enriched.review_status == "auto_accepted"].source_kind.value_counts().to_dict(),
    "french_component_total_eur": float(pd.to_numeric(resolved.french_component_amount).sum()),
    "eur_gradeA": float(pd.to_numeric(resolved.loc[resolved.evidence_grade == "A", "french_component_amount"]).sum()),
    "eur_gradeB": float(pd.to_numeric(resolved.loc[resolved.evidence_grade == "B", "french_component_amount"]).sum()),
    "region_unresolved": int(resolved.region.isna().sum()),
    "model_tokens_used": 0,
}
ensure_v2_path(V2_ROOT / "outputs" / "coverage_cost_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
