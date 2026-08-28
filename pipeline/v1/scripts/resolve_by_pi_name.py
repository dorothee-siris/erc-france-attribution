"""Step A resolver: PI name -> OpenAlex author -> career publications -> French host lab.
Resolves residual grants that HAVE a PI name but were missed by the grant->works (awards) route
(the grant may have no linked works yet, but the PI's own publications reveal their lab).

Pure Python + OpenAlex API — costs OpenAlex quota, NOT Claude session tokens. Checkpoints to disk
(outputs/resolution_piauthor.parquet), so it resumes across sessions: rerun and it skips done grants.
Respects the ~$1/day OpenAlex budget — stops + warns on a Retry-After stall.
"""
import os
import sys
import time
import importlib
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_erc
import pandas as pd

oa = importlib.import_module("03b_resolve_openalex")  # reuse _get, _extract_lab, _is_rto_only, UMR_RE, _has_lab_kw
lib_erc.setup_stdout()
cfg = lib_erc.load_config()
P = lib_erc.paths(cfg)
CKPT = os.path.join(P["outputs"], "resolution_piauthor.parquet")


def _done_ids():
    done = set(pd.read_parquet(os.path.join(P["outputs"], "resolution_openalex.parquet")).grant_id.astype(str))
    for f in ("resolution_llm_100.parquet", "resolution_harvest.parquet", "resolution_piauthor.parquet"):
        p = os.path.join(P["outputs"], f)
        if os.path.exists(p):
            r = pd.read_parquet(p)
            done |= set(r[r.resolved_lab.notna()].grant_id.astype(str))
    return done


def author_lab(pi_name):
    j = oa._get("https://api.openalex.org/authors",
                {"search": pi_name, "per_page": 5,
                 "select": "id,display_name,last_known_institutions,affiliations"})
    results = j.get("results", [])
    if not results:
        return None
    # prefer an author with a French last-known institution
    author = next((a for a in results
                   if any((i or {}).get("country_code") == "FR"
                          for i in (a.get("last_known_institutions") or []))), results[0])
    aid = author["id"].split("/")[-1]
    w = oa._get("https://api.openalex.org/works",
                {"filter": f"authorships.author.id:{aid}", "per_page": 50, "sort": "publication_date:desc",
                 "select": "authorships,publication_year"})
    lab_strings, inst_names = Counter(), Counter()
    for work in w.get("results", []):
        for a in work.get("authorships", []):
            if not ((a.get("author") or {}).get("id") or "").endswith(aid):
                continue
            fr_inst = [i for i in (a.get("institutions") or []) if i.get("country_code") == "FR"]
            for s in a.get("raw_affiliation_strings", []) or []:
                if "france" not in s.lower() and not fr_inst:
                    continue
                (lab_strings if oa._has_lab_kw(s) else Counter())[s.strip()] += 1
            for i in fr_inst:
                if i.get("display_name"):
                    inst_names[i["display_name"]] += 1
    lab, conf = None, 0.0
    if lab_strings:
        best = lab_strings.most_common(1)[0][0]
        cand = oa._extract_lab(best)
        if cand and not oa._is_rto_only(cand):
            lab, conf = cand, 0.65
    if not lab:
        non_rto = [n for n, _ in inst_names.most_common() if not oa._is_rto_only(n)]
        if non_rto:
            lab, conf = non_rto[0], 0.4
        else:
            return None
    return {"resolved_lab": lab, "rnsr_id": None,
            "tutelles": ";".join(n for n, _ in inst_names.most_common(4)) or None,
            "city": None, "confidence": conf, "source_tier": "openalex-piauthor",
            "source_url": author["id"]}


def main():
    spine = pd.read_parquet(P["spine"]).copy()
    spine["grant_id"] = spine.grant_id.astype(str)
    todo = spine[~spine.grant_id.isin(_done_ids()) & spine.pi_name.notna()]
    print(f"Step A: {len(todo)} residual grants with a PI name (~{2*len(todo)} OpenAlex calls)")
    saved = pd.read_parquet(CKPT) if os.path.exists(CKPT) else pd.DataFrame()
    rows = saved.to_dict("records")
    seen = set(saved.grant_id.astype(str)) if len(saved) else set()
    for i, (_, g) in enumerate(todo.iterrows(), 1):
        if g.grant_id in seen:
            continue
        try:
            hit = author_lab(g.pi_name)
        except RuntimeError as e:
            print(f"[{i}] {e}"); break
        if hit:
            rows.append({"grant_id": g.grant_id, **hit})
        if i % 25 == 0:
            pd.DataFrame(rows).to_parquet(CKPT, compression="zstd", index=False)  # periodic checkpoint
            print(f"  {i}/{len(todo)} processed, {len(rows)} resolved (checkpointed)")
        time.sleep(0.12)
    pd.DataFrame(rows).to_parquet(CKPT, compression="zstd", index=False)
    print(f"Step A done: {len(rows)} resolved -> {CKPT}")


if __name__ == "__main__":
    main()
