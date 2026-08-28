"""Finish: merge resolved tiers (OpenAlex + 100-batch LLM + overrides) onto the spine, derive
region/site from resolver-provided city/tutelles, and attribute funding (both lenses) by region and
university. Pure Python, no API/LLM. Unresolved grants (~493) are kept + flagged for manual fill-in.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_erc
import pandas as pd

lib_erc.setup_stdout()
cfg = lib_erc.load_config()
P = lib_erc.paths(cfg)

# --- compact city -> region (nouvelle region) lookup for French research sites ---
CITY2REG = {
    # Ile-de-France
    "paris": "Île-de-France", "orsay": "Île-de-France", "palaiseau": "Île-de-France",
    "gif-sur-yvette": "Île-de-France", "gif sur yvette": "Île-de-France", "villejuif": "Île-de-France",
    "nanterre": "Île-de-France", "versailles": "Île-de-France", "guyancourt": "Île-de-France",
    "créteil": "Île-de-France", "jouy-en-josas": "Île-de-France", "cachan": "Île-de-France",
    "evry": "Île-de-France", "champs-sur-marne": "Île-de-France", "bures-sur-yvette": "Île-de-France",
    "fontainebleau": "Île-de-France", "massy": "Île-de-France", "le chesnay": "Île-de-France",
    "saclay": "Île-de-France", "montrouge": "Île-de-France", "aubervilliers": "Île-de-France",
    # Auvergne-Rhone-Alpes
    "lyon": "Auvergne-Rhône-Alpes", "villeurbanne": "Auvergne-Rhône-Alpes", "grenoble": "Auvergne-Rhône-Alpes",
    "bron": "Auvergne-Rhône-Alpes", "clermont-ferrand": "Auvergne-Rhône-Alpes", "saint-étienne": "Auvergne-Rhône-Alpes",
    "annecy": "Auvergne-Rhône-Alpes", "chambéry": "Auvergne-Rhône-Alpes", "aubière": "Auvergne-Rhône-Alpes",
    # PACA
    "marseille": "Provence-Alpes-Côte d'Azur", "nice": "Provence-Alpes-Côte d'Azur",
    "sophia antipolis": "Provence-Alpes-Côte d'Azur", "sophia-antipolis": "Provence-Alpes-Côte d'Azur",
    "aix-en-provence": "Provence-Alpes-Côte d'Azur", "valbonne": "Provence-Alpes-Côte d'Azur",
    "avignon": "Provence-Alpes-Côte d'Azur", "toulon": "Provence-Alpes-Côte d'Azur",
    # Occitanie
    "toulouse": "Occitanie", "montpellier": "Occitanie", "perpignan": "Occitanie", "narbonne": "Occitanie",
    # Nouvelle-Aquitaine
    "bordeaux": "Nouvelle-Aquitaine", "pau": "Nouvelle-Aquitaine", "poitiers": "Nouvelle-Aquitaine",
    "limoges": "Nouvelle-Aquitaine", "la rochelle": "Nouvelle-Aquitaine", "talence": "Nouvelle-Aquitaine",
    "pessac": "Nouvelle-Aquitaine",
    # Grand Est
    "strasbourg": "Grand Est", "nancy": "Grand Est", "metz": "Grand Est", "reims": "Grand Est",
    "mulhouse": "Grand Est", "illkirch": "Grand Est", "vandœuvre-lès-nancy": "Grand Est",
    # Hauts-de-France
    "lille": "Hauts-de-France", "compiègne": "Hauts-de-France", "amiens": "Hauts-de-France",
    "villeneuve-d'ascq": "Hauts-de-France", "roubaix": "Hauts-de-France",
    # Bretagne
    "rennes": "Bretagne", "brest": "Bretagne", "lannion": "Bretagne", "roscoff": "Bretagne",
    # Pays de la Loire
    "nantes": "Pays de la Loire", "angers": "Pays de la Loire", "le mans": "Pays de la Loire",
    # Normandie
    "caen": "Normandie", "rouen": "Normandie", "le havre": "Normandie",
    # Bourgogne-Franche-Comte
    "dijon": "Bourgogne-Franche-Comté", "besançon": "Bourgogne-Franche-Comté",
    # Centre-Val de Loire
    "orléans": "Centre-Val de Loire", "tours": "Centre-Val de Loire",
    # Overseas / other
    "cayenne": "Guyane", "saint-denis": "La Réunion", "pointe-à-pitre": "Guadeloupe",
}
# fallback: tutelle/university name keyword -> region (when city missing, e.g. OpenAlex rows)
UNIV_KW2REG = [
    (("paris", "saclay", "sorbonne", "polytechnique", "ens-", "psl", "créteil", "nanterre",
      "versailles", "sciences po", "hec", "institut curie", "gustave roussy", "pasteur"), "Île-de-France"),
    (("lyon", "grenoble", "clermont", "saint-étienne", "savoie"), "Auvergne-Rhône-Alpes"),
    (("marseille", "aix-marseille", "côte d'azur", "nice", "avignon", "toulon"), "Provence-Alpes-Côte d'Azur"),
    (("toulouse", "montpellier",), "Occitanie"),
    (("bordeaux", "pau", "poitiers", "limoges", "rochelle"), "Nouvelle-Aquitaine"),
    (("strasbourg", "lorraine", "reims", "haute-alsace", "nancy", "metz"), "Grand Est"),
    (("lille", "compiègne", "picardie", "artois", "littoral"), "Hauts-de-France"),
    (("rennes", "bretagne", "brest", "occidentale"), "Bretagne"),
    (("nantes", "angers", "mans"), "Pays de la Loire"),
    (("caen", "rouen", "normand"), "Normandie"),
    (("dijon", "bourgogne", "besançon", "franche-comté"), "Bourgogne-Franche-Comté"),
    (("orléans", "tours"), "Centre-Val de Loire"),
]


def to_list(t):
    if isinstance(t, list):
        return [str(x).strip() for x in t if str(x).strip()]
    if isinstance(t, str) and t.strip():
        return [x.strip() for x in t.split(";") if x.strip()]
    return []


def region_of(city, tutelles):
    if city and str(city).lower().strip() in CITY2REG:
        return CITY2REG[str(city).lower().strip()]
    blob = " ".join([str(city or "")] + tutelles).lower()
    for kws, reg in UNIV_KW2REG:
        if any(k in blob for k in kws):
            return reg
    return "Autre/NC"


# ---- merge resolved tiers onto the spine ----
spine = pd.read_parquet(P["spine"]).copy()
spine["grant_id"] = spine.grant_id.astype(str)
frames = []
for f, deftier in [("resolution_openalex.parquet", "openalex"), ("resolution_llm_100.parquet", "llm-sonnet"),
                   ("resolution_piauthor.parquet", "openalex-piauthor"), ("resolution_harvest.parquet", "cnrs-page")]:
    p = os.path.join(P["outputs"], f)
    if os.path.exists(p):
        d = pd.read_parquet(p)
        d["grant_id"] = d.grant_id.astype(str)
        if "source_tier" not in d.columns:
            d["source_tier"] = deftier
        d["source_tier"] = d.source_tier.fillna(deftier)
        frames.append(d[[c for c in ["grant_id", "resolved_lab", "tutelles", "city", "confidence", "source_tier"] if c in d.columns]])
res = pd.concat(frames, ignore_index=True)
res = res[res.resolved_lab.notna() & (res.resolved_lab.astype(str).str.len() > 3)]
# overrides (locked)
if os.path.exists(P["overrides"]):
    ov = pd.read_csv(P["overrides"])
    if len(ov) and "locked" in ov.columns:
        ov = ov[ov.locked.astype(str).str.lower().isin(["true", "1"])]
        if len(ov):
            ov["grant_id"] = ov.grant_id.astype(str)
            ov["source_tier"] = "manual"; ov["confidence"] = 1.0
            res = pd.concat([ov[["grant_id", "resolved_lab", "tutelles", "city", "confidence", "source_tier"]], res], ignore_index=True)
# precedence: manual first, then highest confidence
order = {"manual": 0}
res["_r"] = res.source_tier.map(lambda s: order.get(s, 1))
res = res.sort_values(["_r", "confidence"], ascending=[True, False]).drop_duplicates("grant_id", keep="first")

df = spine.merge(res.drop(columns="_r"), on="grant_id", how="left")
df["tutelles_list"] = df.tutelles.apply(to_list)
df["resolved"] = df.resolved_lab.notna() & (df.resolved_lab.astype(str).str.len() > 3)
df["region"] = [region_of(c, t) if r else None for c, t, r in zip(df.city, df.tutelles_list, df.resolved)]
df["site"] = df.city
df["tutelles_str"] = df.tutelles_list.apply(lambda x: ";".join(x))
df = df.drop(columns=[c for c in ["tutelles"] if c in df.columns])  # raw col has mixed types
for c in ("n_fr_pis", "n_total_pis"):
    if c not in df.columns:
        df[c] = 1
df.to_parquet(P["enriched"], compression="zstd", index=False)


# ---- attribution (both lenses) over resolved grants ----
def french_portion(r):
    if r["scheme"] == "Synergy":
        tot = r.get("n_total_pis") or 1
        return float(r["amount_eur"]) * (float(r.get("n_fr_pis") or 1) / float(tot))
    return float(r["amount_eur"])


rows = []
for _, r in df[df.resolved].iterrows():
    tut = r["tutelles_list"] or ["<tutelle inconnue>"]
    n = len(tut)
    fr = french_portion(r)
    syn = r["scheme"] == "Synergy"
    for t in tut:
        rows.append({"grant_id": r.grant_id, "scheme": r.scheme, "university": t,
                     "region": r.region, "site": r.site,
                     "eur_fractional": fr / n,
                     "eur_fullclaim": (None if syn else float(r.amount_eur))})
claims = pd.DataFrame(rows)


def rollup(key):
    g = claims.groupby(key, dropna=False).agg(
        grants=("grant_id", "nunique"),
        eur_fractional=("eur_fractional", "sum"),
        eur_fullclaim=("eur_fullclaim", "sum")).reset_index()
    return g.sort_values("eur_fractional", ascending=False)


rollup("region").to_csv(os.path.join(P["outputs"], "region_funding.csv"), index=False, encoding="utf-8")
rollup("university").to_csv(os.path.join(P["outputs"], "university_funding.csv"), index=False, encoding="utf-8")
rollup("site").to_csv(os.path.join(P["outputs"], "site_funding.csv"), index=False, encoding="utf-8")
keep = ["grant_id", "acronym", "pi_name", "host_entity", "scheme", "panel", "call_year", "start_year",
        "amount_eur", "resolved_lab", "tutelles_str", "city", "region", "site", "confidence", "source_tier", "resolved"]
df[[c for c in keep if c in df.columns]].to_csv(os.path.join(P["outputs"], "grants_enriched.csv"), index=False, encoding="utf-8")
df[["grant_id", "acronym", "resolved_lab", "confidence", "source_tier", "resolved"]].to_csv(
    os.path.join(P["outputs"], "provenance_log.csv"), index=False, encoding="utf-8")
# worklist for manual completion: the unresolved grants (fill labs into overrides/manual_overrides.csv)
uw = ["grant_id", "acronym", "pi_name", "host_entity", "scheme", "panel", "call_year", "start_year", "amount_eur"]
df[~df.resolved][[c for c in uw if c in df.columns]].sort_values("amount_eur", ascending=False).to_csv(
    os.path.join(P["outputs"], "unresolved_grants.csv"), index=False, encoding="utf-8")

# ---- summary ----
nres = int(df.resolved.sum())
print(f"resolved: {nres}/{len(df)} ({100*nres/len(df):.0f}%) | unresolved (flagged for manual): {len(df)-nres}")
print(f"resolved funding: {df.loc[df.resolved,'amount_eur'].sum()/1e6:.0f} M EUR of {df.amount_eur.sum()/1e6:.0f} M total")
print("\nsource tiers:"); print(df[df.resolved].source_tier.value_counts().to_string())
print("\nTop regions (fractional M EUR):")
rr = rollup("region"); rr["eur_fractional"] /= 1e6
print(rr.head(8).to_string(index=False))
lib_erc.runlog(cfg, f"finish: {nres}/{len(df)} resolved, attribution outputs written")
