"""Stage 3 tier 1: resolve PI -> host lab via scanR persons (IdRef-anchored). Deterministic, ~0 tokens.
Field paths confirmed by the Step-1 probe; adjust the EXTRACT block if the probe showed different keys.
LIVE — hits scanR ES. Not run until user approves. (Base + field paths verified on first contact.)"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_erc
import requests
import pandas as pd
from dotenv import load_dotenv

lib_erc.setup_stdout()
load_dotenv(os.path.expanduser("~/.siris/.env"))
cfg = lib_erc.load_config()
BASE = cfg["scanr"]["es_base_public"]
AUTH = None  # set to (os.environ["SCANR_ES_USER"], os.environ["SCANR_ES_PASSWORD"]) if probe needed direct base


def scanr_person_lab(pi_name, start_year):
    q = {"size": 3, "query": {"match": {"fullName": pi_name}}}
    r = requests.post(f"{BASE}/{cfg['scanr']['persons_index']}/_search", json=q, auth=AUTH, timeout=30)
    if r.status_code != 200:
        return None
    hits = r.json().get("hits", {}).get("hits", [])
    for h in hits:
        src = h.get("_source", {})
        for aff in src.get("affiliations", []):
            st = aff.get("structure") or {}
            rnsr = st.get("id") or st.get("rnsr")
            if rnsr:  # first lab-level affiliation with an RNSR id
                return {"resolved_lab": st.get("label"), "rnsr_id": rnsr,
                        "city": (st.get("mainAddress") or {}).get("city"),
                        "tutelles": None,  # filled deterministically in Task 8 from RNSR
                        "confidence": 0.85 if len(hits) == 1 else 0.7,
                        "source_tier": "scanr",
                        "source_url": f"https://scanr.enseignementsup-recherche.gouv.fr/authors/{src.get('id', '')}"}
    return None


def main():
    grants = pd.read_parquet(lib_erc.paths(cfg)["spine"])
    rows = []
    for _, g in grants.iterrows():
        if not g.pi_name:
            continue
        hit = scanr_person_lab(g.pi_name, g.start_year)
        if hit:
            rows.append({"grant_id": g.grant_id, **hit})
    out = pd.DataFrame(rows)
    out.to_parquet(os.path.join(cfg["project_root"], "outputs", "resolution_scanr.parquet"),
                   compression="zstd", index=False)
    print(f"scanR resolved {len(out)}/{len(grants)} grants")
    lib_erc.runlog(cfg, f"Task 4 scanR resolved {len(out)}/{len(grants)}")


if __name__ == "__main__":
    main()
