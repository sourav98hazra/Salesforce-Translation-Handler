"""Project file (.stxproject) tests."""

from __future__ import annotations

from pathlib import Path

from stx.project import StxProject


def test_round_trip(tmp_path: Path) -> None:
    project_path = tmp_path / "x.stxproject"
    p = StxProject(
        name="Test",
        source_stf_path=str(tmp_path / "src.stf"),
        organized_xlsx_path=str(tmp_path / "out.xlsx"),
        target_language_code="ja",
        target_language_name="Japanese",
        backend="deepl",
        target_languages_batch=["fr", "de"],
    )
    p.save(project_path)
    loaded = StxProject.load(project_path)
    assert loaded.name == "Test"
    assert loaded.target_language_code == "ja"
    assert loaded.backend == "deepl"
    assert loaded.target_languages_batch == ["fr", "de"]
    # Paths resolve back to absolute on load.
    assert Path(loaded.source_stf_path).is_absolute()


def test_relative_paths_round_trip(tmp_path: Path) -> None:
    """Sibling paths should be persisted relative and re-resolve to absolute."""
    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    src = proj_dir / "input.stf"
    src.write_text("placeholder\n", encoding="utf-8")
    project_path = proj_dir / "p.stxproject"

    p = StxProject(name="rel", source_stf_path=str(src))
    p.save(project_path)
    saved_text = project_path.read_text(encoding="utf-8")
    # Saved as relative path, not absolute.
    assert "input.stf" in saved_text
    assert str(tmp_path) not in saved_text or "../" in saved_text  # tolerant

    loaded = StxProject.load(project_path)
    assert Path(loaded.source_stf_path).resolve() == src.resolve()


def test_unknown_fields_are_ignored(tmp_path: Path) -> None:
    """Older project files with unknown keys should still load."""
    path = tmp_path / "p.stxproject"
    path.write_text(
        '{"name": "x", "target_language_code": "ja", "future_field": 42}',
        encoding="utf-8",
    )
    loaded = StxProject.load(path)
    assert loaded.name == "x"
    assert loaded.target_language_code == "ja"
