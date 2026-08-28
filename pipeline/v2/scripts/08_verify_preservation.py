from __future__ import annotations

import json

import pandas as pd

from common import PROJECT_ROOT, V2_ROOT, ensure_v2_path
from preservation import verify_manifest


manifest_path = ensure_v2_path(V2_ROOT / "docs" / "v1_preservation_manifest.csv")
manifest = pd.read_csv(manifest_path, dtype={"relative_path": str, "sha256": str})
differences = verify_manifest(PROJECT_ROOT, manifest)
output = ensure_v2_path(V2_ROOT / "comparisons" / "v1_preservation_check.csv")
output.parent.mkdir(parents=True, exist_ok=True)
differences.to_csv(output, index=False, encoding="utf-8")
summary = {"manifest_files": len(manifest), "differences": len(differences), "v1_unchanged": differences.empty}
print(json.dumps(summary, indent=2))
if not differences.empty:
    print(differences.to_string(index=False))
    raise SystemExit(1)
