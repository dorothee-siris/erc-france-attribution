from __future__ import annotations

import json
import shutil
from pathlib import Path

from common import PROJECT_ROOT, V2_ROOT, ensure_v2_path, load_config, sha256_file
from preservation import create_manifest_once, verify_manifest


cfg = load_config()
manifest_path = ensure_v2_path(V2_ROOT / "docs" / "v1_preservation_manifest.csv")
manifest = create_manifest_once(PROJECT_ROOT, manifest_path)
differences = verify_manifest(PROJECT_ROOT, manifest)
if not differences.empty:
    raise SystemExit(f"Refusing initialization: v1 differs from baseline:\n{differences.to_string(index=False)}")

source = (V2_ROOT / cfg["sources"]["dashboard"]).resolve()
snapshot_dir = ensure_v2_path(V2_ROOT / "data" / "raw" / "dashboard" / cfg["snapshot_date"])
snapshot_dir.mkdir(parents=True, exist_ok=True)
snapshot = ensure_v2_path(snapshot_dir / source.name)
if not snapshot.exists():
    shutil.copy2(source, snapshot)
elif sha256_file(source) != sha256_file(snapshot):
    raise SystemExit("Dashboard snapshot exists but differs from the source workbook")

hashes = {
    "source": str(source),
    "snapshot": str(snapshot),
    "source_sha256": sha256_file(source),
    "snapshot_sha256": sha256_file(snapshot),
    "v1_manifest_rows": len(manifest),
}
(snapshot_dir / "snapshot_manifest.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
print(json.dumps(hashes, indent=2))
