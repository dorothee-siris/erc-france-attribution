from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import requests

from common import V2_ROOT, ensure_v2_path, load_config
from hal import extract_hal_candidates
from resolution import choose_resolution


cfg = load_config()
components = pd.read_parquet(ensure_v2_path(V2_ROOT / "outputs" / "french_components.parquet"))
cache_dir = ensure_v2_path(V2_ROOT / "checkpoints" / "cache" / "hal_grants")
structure_cache = ensure_v2_path(V2_ROOT / "checkpoints" / "cache" / "hal_structures")
cache_dir.mkdir(parents=True, exist_ok=True)
structure_cache.mkdir(parents=True, exist_ok=True)
candidates = []

for index, component in enumerate(components.itertuples(index=False), 1):
    cache_path = ensure_v2_path(cache_dir / f"{component.grant_id}.json")
    payload = None
    if cache_path.exists():
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = None  # corrupt cache (e.g. from an interrupted write) -> re-fetch
    if payload is None:
        params = {
            "q": f"europeanProjectReference_s:{component.grant_id}",
            "fl": "docid,producedDateY_i,authIdHasPrimaryStructure_fs,labStructId_i,labStructName_s",
            "rows": 100,
            "wt": "json",
        }
        response = requests.get(cfg["sources"]["hal_search"], params=params, timeout=60)
        response.raise_for_status()
        payload = response.json()
        cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        time.sleep(cfg["resolution"]["hal_sleep_seconds"])
    extracted = extract_hal_candidates(component.grant_id, component.pi_name, component.start_date.year, payload)
    if extracted.empty:
        continue
    extracted["component_id"] = component.component_id
    for row in extracted.to_dict("records"):
        structure_id = row.get("structure_id")
        ref_path = ensure_v2_path(structure_cache / f"{structure_id}.json")
        ref = None
        if ref_path.exists():
            try:
                ref = json.loads(ref_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                ref = None
        if ref is None:
            response = requests.get(
                cfg["sources"]["hal_structure"],
                params={"q": f"docid:{structure_id}", "fl": "docid,label_s,address_s,country_s,rnsr_s,parentDocid_i", "rows": 1, "wt": "json"},
                timeout=60,
            )
            response.raise_for_status()
            ref = response.json()
            ref_path.write_text(json.dumps(ref, ensure_ascii=False), encoding="utf-8")
            time.sleep(cfg["resolution"]["hal_sleep_seconds"])
        docs = ref.get("response", {}).get("docs", [])
        if docs:
            structure = docs[0]
            rnsr = structure.get("rnsr_s")
            row["rnsr_id"] = rnsr[0] if isinstance(rnsr, list) and rnsr else rnsr
            row["lab_address"] = structure.get("address_s")
        candidates.append(row)
    if index % 50 == 0:
        pd.DataFrame(candidates).to_parquet(ensure_v2_path(V2_ROOT / "checkpoints" / "hal_candidates.parquet"), compression="zstd", index=False)

candidate_frame = pd.DataFrame(candidates)
candidate_path = ensure_v2_path(V2_ROOT / "checkpoints" / "hal_candidates.parquet")
candidate_frame.to_parquet(candidate_path, compression="zstd", index=False)
resolutions = choose_resolution(candidate_frame) if not candidate_frame.empty else pd.DataFrame()
resolutions.to_parquet(ensure_v2_path(V2_ROOT / "checkpoints" / "hal_resolutions.parquet"), compression="zstd", index=False)
print(f"HAL candidates={len(candidate_frame)} accepted={(resolutions.review_status == 'auto_accepted').sum() if len(resolutions) else 0}")
