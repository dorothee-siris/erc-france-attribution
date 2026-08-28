"""Group the RTO-hosted residual by (institution, call_year, scheme) — each group == one annual
ERC-laureate announcement page. Non-RTO residual is left for per-grant Haiku (03d).
Writes outputs/harvest_groups.json and outputs/residual_nonrto.json."""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_erc
import pandas as pd

lib_erc.setup_stdout()
cfg = lib_erc.load_config()
P = lib_erc.paths(cfg)

RTO = {
    "Centre national de la recherche scientifique": "CNRS",
    "Institut national de la santé et de la recherche médicale": "INSERM",
    "Commissariat à l'énergie atomique et aux énergies alternatives": "CEA",
    "Institut national de recherche en sciences et technologies du numérique": "Inria",
    "Institut national de recherche pour l'agriculture, l'alimentation et l'environnement": "INRAE",
    "Institut de recherche pour le développement": "IRD",
    "Centre de coopération internationale en recherche agronomique pour le développement": "CIRAD",
}


def load_residual():
    spine = pd.read_parquet(P["spine"]).copy()
    spine["grant_id"] = spine.grant_id.astype(str)
    done = set(pd.read_parquet(os.path.join(P["outputs"], "resolution_openalex.parquet")).grant_id.astype(str))
    for f in ("resolution_llm_100.parquet", "resolution_piauthor.parquet", "resolution_harvest.parquet"):
        p = os.path.join(P["outputs"], f)
        if os.path.exists(p):
            r = pd.read_parquet(p)
            done |= set(r[r.resolved_lab.notna()].grant_id.astype(str))
    return spine[~spine.grant_id.isin(done)]


def main():
    res = load_residual()
    res = res.copy()
    res["rto"] = res.host_entity.map(RTO)
    rto = res[res.rto.notna()]
    nonrto = res[res.rto.isna()]

    groups = []
    for (inst, yr, scheme), sub in rto.groupby(["rto", "call_year", "scheme"]):
        groups.append({
            "institution": [k for k, v in RTO.items() if v == inst][0],
            "inst_short": inst, "year": int(yr), "scheme": scheme,
            "grants": [{"grant_id": r.grant_id, "acronym": str(r.acronym),
                        "panel": None if pd.isna(r.panel) else str(r.panel)}
                       for _, r in sub.iterrows()],
        })
    json.dump(groups, open(os.path.join(P["outputs"], "harvest_groups.json"), "w", encoding="utf-8"),
              ensure_ascii=False)

    nr = [{"grant_id": r.grant_id, "acronym": str(r.acronym), "host_entity": str(r.host_entity),
           "pi_name": None if pd.isna(r.pi_name) else str(r.pi_name), "scheme": str(r.scheme),
           "start_year": int(r.start_year) if pd.notna(r.start_year) else None,
           "panel": None if pd.isna(r.panel) else str(r.panel),
           "abstract": (str(r.abstract)[:140] if pd.notna(r.abstract) else "")}
          for _, r in nonrto.iterrows()]
    json.dump(nr, open(os.path.join(P["outputs"], "residual_nonrto.json"), "w", encoding="utf-8"),
              ensure_ascii=False)

    print(f"residual: {len(res)} | RTO {len(rto)} -> {len(groups)} harvest groups | non-RTO {len(nonrto)} -> per-grant Haiku")
    print(f"grants/group: median {int(pd.Series([len(g['grants']) for g in groups]).median())}, "
          f"max {max(len(g['grants']) for g in groups)}")


if __name__ == "__main__":
    main()
