from __future__ import annotations

import json

import pandas as pd

from common import PROJECT_ROOT, V2_ROOT, ensure_v2_path, load_config
from cordis import normalize_organisations
from pipeline import build_local_outputs


cfg = load_config()
date = cfg["snapshot_date"]
dashboard_path = ensure_v2_path(V2_ROOT / "data" / "raw" / "dashboard" / date / "bulk_data_erc_dashboard.xlsx")
dashboard = pd.read_excel(dashboard_path)

organisation_frames = []
project_frames = []
for programme in ("horizon", "h2020"):
    path = ensure_v2_path(V2_ROOT / "data" / "raw" / "cordis" / date / programme / "organization.parquet")
    if path.exists():
        organisation_frames.append(normalize_organisations(pd.read_parquet(path)))
    project_path = ensure_v2_path(V2_ROOT / "data" / "raw" / "cordis" / date / programme / "project.parquet")
    if project_path.exists():
        project_frames.append(pd.read_parquet(project_path))
organisations = pd.concat(organisation_frames, ignore_index=True).drop_duplicates() if organisation_frames else pd.DataFrame()
projects = pd.concat(project_frames, ignore_index=True).drop_duplicates(subset=["id"]) if project_frames else pd.DataFrame()
v1_spine = pd.read_parquet(PROJECT_ROOT / "outputs" / "grants.parquet")

report = build_local_outputs(
    dashboard,
    organisations,
    V2_ROOT,
    cfg["perimeter"]["start_inclusive"],
    cfg["perimeter"]["end_exclusive"],
    cordis_projects=projects,
    v1_spine=v1_spine,
)
print(json.dumps(report, indent=2))
