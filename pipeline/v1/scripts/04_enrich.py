"""Stage 4: deterministic lab -> RNSR (tutelles, UMR flag, commune, region) + commune -> site.
Column names for RNSR/EPCI confirmed by the Task-2/Task-8 snapshots; adjust the KEYS block if they differ."""
import os
import sys
import glob
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_erc
import pandas as pd

lib_erc.setup_stdout()
cfg = lib_erc.load_config()
P = lib_erc.paths(cfg)


def rnsr_index(rnsr_json_path):
    data = json.load(open(rnsr_json_path, encoding="utf-8"))
    if isinstance(data, dict) and "records" in data:
        data = [r.get("fields", r) for r in data["records"]]
    idx = {}
    for r in data:
        rid = r.get("numero_national_de_structure") or r.get("rnsr")
        if not rid:
            continue
        tut = r.get("tutelles") or []
        tut = [t.get("libelle") if isinstance(t, dict) else t for t in tut] if isinstance(tut, list) else [tut]
        code_unite = (r.get("code_unite") or "").upper()
        idx[rid] = {"label": r.get("libelle"), "tutelles": [t for t in tut if t],
                    "is_umr": code_unite.startswith(("UMR", "UAR", "UMS")) or len([t for t in tut if t]) > 1,
                    "commune_code": r.get("code_commune") or r.get("commune"),
                    "region": r.get("region")}
    return idx


def commune_to_site(commune_code, epci_df):
    if not commune_code:
        return None
    m = epci_df[epci_df["insee"].astype(str) == str(commune_code)]
    if len(m) and str(m.iloc[0]["epci_nature"]).upper().startswith(("MET", "METR")):
        return m.iloc[0]["epci_nom"]
    return None


def main():
    grants = pd.read_parquet(P["spine"])
    res = pd.read_parquet(P["resolution"])
    rnsr_path = sorted(glob.glob(os.path.join(P["raw"], "rnsr", "*", "rnsr.json")))[-1]
    idx = rnsr_index(rnsr_path)
    epci_path = sorted(glob.glob(os.path.join(P["raw"], "epci", "*", "epci_communes.csv")))[-1]
    epci = pd.read_csv(epci_path, dtype=str)  # rename to canonical cols per Step-1 comments:
    epci = epci.rename(columns={c: "insee" for c in epci.columns if c.lower() in ("codgeo", "insee", "code_commune")})

    df = grants.merge(res, on="grant_id", how="left")

    def enr(row):
        e = idx.get(row.rnsr_id, {}) if row.rnsr_id else {}
        tut = e.get("tutelles", []) or ([] if pd.isna(row.tutelles) else str(row.tutelles).split(";"))
        region = e.get("region")
        site = commune_to_site(e.get("commune_code"), epci)
        return pd.Series({"is_umr": e.get("is_umr", len(tut) > 1), "tutelles": tut,
                          "n_tutelles": max(len(tut), 1), "region": region, "site": site})

    df = pd.concat([df, df.apply(enr, axis=1)], axis=1)
    df.to_parquet(P["enriched"], compression="zstd", index=False)
    print(f"enriched {len(df)} | with region: {df.region.notna().sum()} | with site: {df.site.notna().sum()}")
    lib_erc.runlog(cfg, f"Task 8 enrich: region={df.region.notna().sum()}/{len(df)}")


if __name__ == "__main__":
    main()
