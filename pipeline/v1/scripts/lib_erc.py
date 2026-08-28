"""Shared helpers for the ERC->France attribution pipeline. Copy-in, no external deps on SIRIS tools."""
import os
import sys
import yaml


def setup_stdout():
    """Windows console is cp1252; force utf-8 so accented lab names don't crash mid-run."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def load_config(path=None):
    here = os.path.dirname(os.path.abspath(__file__))
    path = path or os.path.join(here, "..", "config.yaml")
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg.setdefault("project_root", os.path.abspath(os.path.join(here, "..")))
    return cfg


def paths(cfg):
    root = cfg["project_root"]
    out = os.path.join(root, "outputs")
    return {
        "root": root,
        "raw": os.path.join(root, "data", "raw"),
        "spine": os.path.join(out, "grants.parquet"),
        "resolution": os.path.join(out, "resolution.parquet"),
        "enriched": os.path.join(out, "grants_enriched.parquet"),
        "outputs": out,
        "overrides": os.path.join(root, "overrides", "manual_overrides.csv"),
    }


def snapshot_dir(cfg, source):
    """data/raw/<source>/<snapshot_date>/ ; date comes from config, NOT a live clock (reproducibility)."""
    d = os.path.join(cfg["project_root"], "data", "raw", source, cfg["snapshot_date"])
    os.makedirs(d, exist_ok=True)
    return d


def runlog(cfg, msg):
    out = os.path.join(cfg["project_root"], "outputs")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "RUNLOG.md"), "a", encoding="utf-8") as f:
        f.write(f"- {cfg['snapshot_date']} {msg}\n")
