from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parent


class PathEscapeError(ValueError):
    pass


def ensure_v2_path(path: Path | str, root: Path | str = V2_ROOT) -> Path:
    candidate = Path(path).resolve()
    safe_root = Path(root).resolve()
    if candidate != safe_root and safe_root not in candidate.parents:
        raise PathEscapeError(f"write target escapes v2 root: {candidate}")
    return candidate


def load_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or V2_ROOT / "config.yaml"
    with open(config_path, encoding="utf-8") as stream:
        cfg = yaml.safe_load(stream)
    cfg["v2_root"] = str(V2_ROOT)
    cfg["project_root"] = str(PROJECT_ROOT)
    return cfg


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_grant_id(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").astype("Int64")
    return numeric.astype("string")


def write_dataframe(frame: pd.DataFrame, path: Path | str) -> Path:
    target = ensure_v2_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() == ".parquet":
        frame.to_parquet(target, compression="zstd", index=False)
    elif target.suffix.lower() == ".csv":
        frame.to_csv(target, index=False, encoding="utf-8")
    else:
        raise ValueError(f"unsupported dataframe format: {target.suffix}")
    return target


def write_json(value: Any, path: Path | str) -> Path:
    target = ensure_v2_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return target
