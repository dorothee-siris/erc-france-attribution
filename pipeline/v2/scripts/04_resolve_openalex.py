"""OpenAlex free resolver. Runs ONLY on components not already covered by the v1 seed or an accepted
HAL resolution (keeps API volume + Claude cost minimal). For each: try the grant-award route
(awards.funder_award_id); if it yields nothing, try the PI-author route (author's own works reveal the
lab for recent grants with no award-linked works). Disk-cached + resumable; stops on OpenAlex 403/429.
Writes checkpoints/openalex_candidates.parquet (candidates; grading happens in 05, cross-source)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

from common import V2_ROOT, ensure_v2_path, load_config
from openalex import extract_openalex_candidates, extract_author_candidates, pick_fr_author

AUTHORS_URL = "https://api.openalex.org/authors"

cfg = load_config()
load_dotenv(Path.home() / ".siris" / ".env")
api_key = os.environ.get("OPENALEX_API_KEY")
mailto = os.environ.get("OPENALEX_MAILTO")
auth = {k: v for k, v in (("api_key", api_key), ("mailto", mailto)) if v}
sleep = cfg["resolution"]["openalex_sleep_seconds"]

components = pd.read_parquet(ensure_v2_path(V2_ROOT / "outputs" / "french_components.parquet"))


def _done_component_ids() -> set:
    done = set()
    for name, accepted_only in (("v1_candidates.parquet", False), ("hal_resolutions.parquet", True)):
        p = ensure_v2_path(V2_ROOT / "checkpoints" / name)
        if p.exists():
            d = pd.read_parquet(p)
            if accepted_only and "review_status" in d.columns:
                d = d[d.review_status == "auto_accepted"]
            done |= set(d.component_id.astype(str))
    return done


def _get(url, params, cache_path):
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8")), True
    r = requests.get(url, params={**params, **auth}, timeout=60)
    if r.status_code in (403, 429):
        raise RuntimeError(f"OpenAlex throttle/budget HTTP {r.status_code} — STOP")
    r.raise_for_status()
    cache_path.write_text(json.dumps(r.json(), ensure_ascii=False), encoding="utf-8")
    time.sleep(sleep)
    return r.json(), False


done = _done_component_ids()
todo = components[~components.component_id.astype(str).isin(done) & components.pi_name.notna()].copy()
grant_cache = ensure_v2_path(V2_ROOT / "checkpoints" / "cache" / "openalex_grants"); grant_cache.mkdir(parents=True, exist_ok=True)
auth_cache = ensure_v2_path(V2_ROOT / "checkpoints" / "cache" / "openalex_authors"); auth_cache.mkdir(parents=True, exist_ok=True)
candidates = []
print(f"OpenAlex todo: {len(todo)} components (skipping {len(done)} v1/HAL-covered)")

for index, c in enumerate(todo.itertuples(index=False), 1):
    sy = pd.Timestamp(c.start_date).year
    try:
        # 1) grant-award route
        payload, _ = _get(cfg["sources"]["openalex_works"],
                          {"filter": f"awards.funder_award_id:{c.grant_id}", "per_page": 100,
                           "select": "id,publication_year,authorships"},
                          ensure_v2_path(grant_cache / f"{c.grant_id}.json"))
        ext = extract_openalex_candidates(c.grant_id, c.pi_name, sy, payload)
        # 2) PI-author fallback
        if ext.empty:
            asearch, _ = _get(AUTHORS_URL,
                              {"search": c.pi_name, "per_page": 5,
                               "select": "id,display_name,last_known_institutions"},
                              ensure_v2_path(auth_cache / f"{c.component_id.replace(':', '_')}_a.json"))
            aid = pick_fr_author(asearch, c.pi_name)
            if aid:
                works, _ = _get(cfg["sources"]["openalex_works"],
                                {"filter": f"authorships.author.id:{aid}", "per_page": 100,
                                 "sort": "publication_date:desc",
                                 "select": "id,publication_year,authorships"},
                                ensure_v2_path(auth_cache / f"{aid}_w.json"))
                ext = extract_author_candidates(c.grant_id, c.pi_name, sy, works)
    except RuntimeError as e:
        print(f"[{index}] {e}")
        break
    if not ext.empty:
        ext["component_id"] = c.component_id
        ext["source_family"] = "openalex"
        candidates.extend(ext.to_dict("records"))
    if index % 50 == 0:
        pd.DataFrame(candidates).to_parquet(ensure_v2_path(V2_ROOT / "checkpoints" / "openalex_candidates.parquet"), compression="zstd", index=False)
        print(f"  {index}/{len(todo)} processed, {len(candidates)} candidates")

pd.DataFrame(candidates).to_parquet(ensure_v2_path(V2_ROOT / "checkpoints" / "openalex_candidates.parquet"), compression="zstd", index=False)
print(f"OpenAlex candidates written: {len(candidates)}")
