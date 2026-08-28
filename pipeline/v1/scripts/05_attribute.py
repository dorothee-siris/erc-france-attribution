"""Stage 5: attribution. Two lenses (full-claim single-host only; fractional 1/N across cotutelles),
rolled up by region, site, and university. Synergy = fractional only, on the French portion."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_erc
import pandas as pd

lib_erc.setup_stdout()
cfg = lib_erc.load_config()
P = lib_erc.paths(cfg)


def french_portion(row):
    if row["scheme"] == "Synergy":
        tot = row.get("n_total_pis") or 1
        return float(row["amount_eur"]) * (float(row.get("n_fr_pis") or 1) / float(tot))
    return float(row["amount_eur"])


def explode_claims(df):
    out = []
    for _, r in df.iterrows():
        tut = r["tutelles"] if isinstance(r["tutelles"], list) and r["tutelles"] else ["<unresolved>"]
        n = max(len(tut), 1)
        fr_amt = french_portion(r)
        is_syn = r["scheme"] == "Synergy"
        for t in tut:
            out.append({"grant_id": r["grant_id"], "scheme": r["scheme"], "tutelle": t,
                        "region": r.get("region"), "site": r.get("site"),
                        "amount_frac": fr_amt / n,
                        # full-claim: each tutelle claims full amount; Synergy excluded (NaN)
                        "amount_full": (None if is_syn else float(r["amount_eur"]))})
    return pd.DataFrame(out)


def rollup(claims, key):
    g = claims.groupby(key, dropna=False).agg(
        grants=("grant_id", "nunique"),
        eur_fractional=("amount_frac", "sum"),
        eur_fullclaim=("amount_full", "sum")).reset_index()
    return g.sort_values("eur_fractional", ascending=False)


def main():
    df = pd.read_parquet(P["enriched"])
    for c in ("n_fr_pis", "n_total_pis"):
        if c not in df.columns:
            df[c] = 1   # non-Synergy default; Synergy PI counts filled where known
    claims = explode_claims(df)
    df.to_csv(os.path.join(P["outputs"], "grants_enriched.csv"), index=False, encoding="utf-8")
    rollup(claims, "region").to_csv(os.path.join(P["outputs"], "region_funding.csv"), index=False, encoding="utf-8")
    rollup(claims, "site").to_csv(os.path.join(P["outputs"], "site_funding.csv"), index=False, encoding="utf-8")
    rollup(claims, "tutelle").rename(columns={"tutelle": "university"}).to_csv(
        os.path.join(P["outputs"], "university_funding.csv"), index=False, encoding="utf-8")
    df[["grant_id", "pi_name", "resolved_lab", "rnsr_id", "confidence", "source_tier"]].to_csv(
        os.path.join(P["outputs"], "provenance_log.csv"), index=False, encoding="utf-8")
    # reconciliation assertion: fractional region total ~= sum of french portions
    frac_total = claims.amount_frac.sum()
    fr_total = df.apply(french_portion, axis=1).sum()
    print(f"fractional total {frac_total:,.0f} EUR vs sum french-portion {fr_total:,.0f} EUR")
    assert abs(frac_total - fr_total) < 1.0, "fractional attribution does not reconcile"
    lib_erc.runlog(cfg, f"Task 9 attribute: fractional total {frac_total / 1e6:.0f} MEUR")


if __name__ == "__main__":
    main()
