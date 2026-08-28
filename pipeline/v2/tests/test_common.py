from pathlib import Path

import pytest

from common import PathEscapeError, ensure_v2_path


def test_ensure_v2_path_accepts_descendant(tmp_path: Path):
    root = tmp_path / "v2"
    target = root / "outputs" / "spine.parquet"
    assert ensure_v2_path(target, root) == target.resolve()


def test_ensure_v2_path_rejects_parent_escape(tmp_path: Path):
    root = tmp_path / "v2"
    with pytest.raises(PathEscapeError):
        ensure_v2_path(root / ".." / "outputs" / "grants.parquet", root)
