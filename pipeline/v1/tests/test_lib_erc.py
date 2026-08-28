import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import lib_erc


def test_paths_are_absolute_and_snapshot_uses_config_date(tmp_path):
    cfg = {"project_root": str(tmp_path), "snapshot_date": "2026-07-23"}
    p = lib_erc.paths(cfg)
    assert os.path.isabs(p["spine"])
    d = lib_erc.snapshot_dir(cfg, "rnsr")
    assert d.endswith(os.path.join("data", "raw", "rnsr", "2026-07-23"))
    assert os.path.isdir(d)
