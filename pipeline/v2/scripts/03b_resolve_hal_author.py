"""Tier-1 free resolver: HAL AUTHOR-name route for the residual. Queries HAL by the PI's name
(French deposits) rather than the grant reference, extracts the PI's primary structure, and links it
to RNSR via HAL's structure referential. Disk-cached + resumable. source_kind='hal_author' (Grade B
via >=2-deposit corroboration, or Grade A if it agrees with another source in 05)."""
from __future__ import annotations

import json
import time

import pandas as pd
import requests

from common import V2_ROOT, ensure_v2_path, load_config
from hal import extract_hal_author_candidates

cfg = load_config()
components = pd.read_parquet(ensure_v2_path(V2_ROOT / "outputs" / "french_components.parquet"))
# ALL PI-name components (stable set, independent of prior hal_author acceptance): also lets HAL author
# corroborate already-resolved labs -> cross-source Grade-A upgrades. Cache makes re-runs cheap.
todo = components[components.pi_name.notna()].copy()
todo["sy"] = pd.to_datetime(todo.start_date, errors="coerce").dt.year

cache_dir = ensure_v2_path(V2_ROOT / "checkpoints" / "cache" / "hal_authors"); cache_dir.mkdir(parents=True, exist_ok=True)
struct_cache = ensure_v2_path(V2_ROOT / "checkpoints" / "cache" / "hal_structures"); struct_cache.mkdir(parents=True, exist_ok=True)
sleep = cfg["resolution"]["hal_sleep_seconds"]
candidates = []
print(f"HAL author route on {len(todo)} residual components with a PI name")


def _cached_get(url, params, path):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    last = None
    for attempt in range(5):
        try:
            r = requests.get(url, params=params, timeout=60)
            r.raise_for_status()
            path.write_text(json.dumps(r.json(), ensure_ascii=False), encoding="utf-8")
            time.sleep(sleep)
            return r.json()
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
            last = e
            time.sleep(2 * (attempt + 1))  # backoff on transient HAL drops / throttling
    raise last


for i, c in enumerate(todo.itertuples(index=False), 1):
    cpath = ensure_v2_path(cache_dir / f"{str(c.component_id).replace(':', '_')}.json")
    payload = _cached_get(cfg["sources"]["hal_search"],
                          {"q": f'authFullName_t:"{c.pi_name}"', "fq": "country_s:fr",
                           "fl": "docid,producedDateY_i,authIdHasPrimaryStructure_fs,labStructId_i",
                           "rows": 100, "wt": "json"}, cpath)
    ext = extract_hal_author_candidates(c.grant_id, c.pi_name, c.sy, payload)
    if ext.empty:
        continue
    ext["component_id"] = c.component_id
    for row in ext.to_dict("records"):
        sid = row.get("structure_id")
        ref = _cached_get(cfg["sources"]["hal_structure"],
                          {"q": f"docid:{sid}", "fl": "docid,label_s,address_s,country_s,rnsr_s", "rows": 1, "wt": "json"},
                          ensure_v2_path(struct_cache / f"{sid}.json"))
        docs = ref.get("response", {}).get("docs", [])
        if docs:
            rnsr = docs[0].get("rnsr_s")
            row["rnsr_id"] = rnsr[0] if isinstance(rnsr, list) and rnsr else rnsr
            row["city"] = docs[0].get("address_s")
        candidates.append(row)
    if i % 50 == 0:
        pd.DataFrame(candidates).to_parquet(ensure_v2_path(V2_ROOT / "checkpoints" / "hal_author_candidates.parquet"), compression="zstd", index=False)
        print(f"  {i}/{len(todo)} processed, {len(candidates)} candidates")

pd.DataFrame(candidates).to_parquet(ensure_v2_path(V2_ROOT / "checkpoints" / "hal_author_candidates.parquet"), compression="zstd", index=False)
print(f"HAL author candidates: {len(candidates)}")
