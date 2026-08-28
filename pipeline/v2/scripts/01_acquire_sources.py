from __future__ import annotations

import json

from common import V2_ROOT, ensure_v2_path, load_config
from sources import download_cordis_snapshot, download_ods_parquet


cfg = load_config()
date = cfg["snapshot_date"]
raw = ensure_v2_path(V2_ROOT / "data" / "raw")
manifest = {}

for label, key in [("horizon", "cordis_horizon"), ("h2020", "cordis_h2020")]:
    destination = ensure_v2_path(raw / "cordis" / date / label)
    project_file = destination / "project.parquet"
    organisation_file = destination / "organization.parquet"
    if project_file.exists() and organisation_file.exists():
        manifest[f"cordis_{label}"] = {"status": "cached", "project": str(project_file), "organization": str(organisation_file)}
    else:
        manifest[f"cordis_{label}"] = download_cordis_snapshot(cfg["sources"][key], destination, V2_ROOT)

for label, key in [("active", "rnsr_active_dataset"), ("historical", "rnsr_historical_dataset")]:
    destination = ensure_v2_path(raw / "rnsr" / date / f"{label}.parquet")
    if destination.exists():
        manifest[f"rnsr_{label}"] = {"status": "cached", "path": str(destination)}
    else:
        manifest[f"rnsr_{label}"] = download_ods_parquet(cfg["sources"][key], destination, V2_ROOT)

manifest_path = ensure_v2_path(raw / "source_manifest.json")
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(manifest, ensure_ascii=False, indent=2))
