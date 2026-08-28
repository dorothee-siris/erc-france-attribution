from pathlib import Path

from preservation import build_manifest, create_manifest_once, verify_manifest


def test_manifest_excludes_v2_and_detects_changed_v1_file(tmp_path: Path):
    root = tmp_path / "project"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "v1.py").write_text("original", encoding="utf-8")
    (root / "v2" / "docs").mkdir(parents=True)
    (root / "v2" / "docs" / "new.md").write_text("new", encoding="utf-8")
    manifest = build_manifest(root)
    assert manifest.relative_path.tolist() == ["scripts/v1.py"]
    assert verify_manifest(root, manifest).empty
    (root / "scripts" / "v1.py").write_text("changed", encoding="utf-8")
    result = verify_manifest(root, manifest)
    assert result.status.tolist() == ["changed"]


def test_create_manifest_once_does_not_refresh_baseline_after_change(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    original = root / "README.md"
    original.write_text("original", encoding="utf-8")
    destination = root / "v2" / "docs" / "manifest.csv"
    first = create_manifest_once(root, destination)
    original.write_text("changed", encoding="utf-8")
    second = create_manifest_once(root, destination)
    assert first.sha256.tolist() == second.sha256.tolist()
    assert verify_manifest(root, second).status.tolist() == ["changed"]
