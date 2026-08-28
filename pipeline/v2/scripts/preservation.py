from __future__ import annotations

from pathlib import Path

import pandas as pd

from common import sha256_file


EXCLUDED_PARTS = {".git", ".pytest_cache", "__pycache__", "v2", "TO DELETE"}


def _production_files(project_root: Path):
    for path in sorted(project_root.rglob("*")):
        if not path.is_file() or any(part in EXCLUDED_PARTS for part in path.relative_to(project_root).parts):
            continue
        yield path


def build_manifest(project_root: Path) -> pd.DataFrame:
    root = project_root.resolve()
    rows = []
    for path in _production_files(root):
        rows.append(
            {
                "relative_path": path.relative_to(root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return pd.DataFrame(rows, columns=["relative_path", "size_bytes", "sha256"])


def create_manifest_once(project_root: Path, destination: Path) -> pd.DataFrame:
    if destination.exists():
        return pd.read_csv(destination, dtype={"relative_path": str, "sha256": str})
    manifest = build_manifest(project_root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(destination, index=False, encoding="utf-8")
    return manifest


def verify_manifest(project_root: Path, manifest: pd.DataFrame) -> pd.DataFrame:
    root = project_root.resolve()
    rows = []
    expected_paths = set(manifest.relative_path)
    for record in manifest.itertuples(index=False):
        path = root / record.relative_path
        if not path.exists():
            status, actual = "missing", None
        else:
            actual = sha256_file(path)
            status = "unchanged" if actual == record.sha256 else "changed"
        if status != "unchanged":
            rows.append({"relative_path": record.relative_path, "status": status, "expected_sha256": record.sha256, "actual_sha256": actual})
    for path in _production_files(root):
        relative = path.relative_to(root).as_posix()
        if relative not in expected_paths:
            rows.append({"relative_path": relative, "status": "added", "expected_sha256": None, "actual_sha256": sha256_file(path)})
    return pd.DataFrame(rows, columns=["relative_path", "status", "expected_sha256", "actual_sha256"])
