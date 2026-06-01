"""CLI tests using Typer's CliRunner."""
from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from stx.cli import app
from stx.model import Document, Entry
from stx.stf import render_full_stf

runner = CliRunner()


def _write_sample_stf(tmp_path: Path) -> Path:
    doc = Document(
        language="Japanese",
        language_code="ja",
        stf_type="Bilingual",
        translation_type="Metadata",
        entries=[
            Entry(key="CustomLabel.A", label="Hello", translation="Konnichiwa"),
            Entry(key="CustomLabel.B", label="World"),
        ],
    )
    path = tmp_path / "test.stf"
    path.write_text(render_full_stf(doc), encoding="utf-8")
    return path


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "stx" in result.output


def test_info(tmp_path):
    stf = _write_sample_stf(tmp_path)
    result = runner.invoke(app, ["info", str(stf)])
    assert result.exit_code == 0
    assert "Japanese" in result.output
    assert "2" in result.output  # total rows


def test_stf2xlsx(tmp_path):
    stf = _write_sample_stf(tmp_path)
    xlsx = tmp_path / "output.xlsx"
    result = runner.invoke(app, ["stf2xlsx", str(stf), str(xlsx)])
    assert result.exit_code == 0
    assert xlsx.exists()


def test_validate_clean(tmp_path):
    """Clean document -> exit code 0."""
    doc = Document(
        language="Japanese", language_code="ja",
        entries=[
            Entry(key="CustomLabel.A", label="Hello", translation="Konnichiwa"),
        ],
    )
    path = tmp_path / "clean.stf"
    path.write_text(render_full_stf(doc), encoding="utf-8")
    result = runner.invoke(app, ["validate", str(path)])
    assert result.exit_code == 0


def test_validate_errors_exit_code(tmp_path):
    """Document with duplicate keys -> exit code 1."""
    doc = Document(
        language="Japanese", language_code="ja",
        entries=[
            Entry(key="CustomLabel.A", label="Hello", translation="Konnichiwa"),
            Entry(key="CustomLabel.A", label="World", translation="Sekai"),
        ],
    )
    path = tmp_path / "dupes.stf"
    path.write_text(render_full_stf(doc), encoding="utf-8")
    result = runner.invoke(app, ["validate", str(path)])
    assert result.exit_code == 1


def test_backends():
    result = runner.invoke(app, ["backends"])
    assert result.exit_code == 0
    assert "google" in result.output
    assert "deepl" in result.output
    assert "azure" in result.output
    assert "openai" in result.output


def test_scope_new_and_show(tmp_path):
    stf = _write_sample_stf(tmp_path)
    scope_file = tmp_path / "scope.stxscope.json"

    result = runner.invoke(app, ["scope", "new", str(stf), str(scope_file)])
    assert result.exit_code == 0
    assert scope_file.exists()

    result = runner.invoke(app, ["scope", "show", str(scope_file)])
    assert result.exit_code == 0


def test_xlsx2stf(tmp_path):
    stf = _write_sample_stf(tmp_path)
    xlsx = tmp_path / "output.xlsx"
    runner.invoke(app, ["stf2xlsx", str(stf), str(xlsx)])

    out_dir = tmp_path / "stf_out"
    result = runner.invoke(app, ["xlsx2stf", str(xlsx), str(out_dir), "--language", "Japanese", "--code", "ja"])
    assert result.exit_code == 0
    assert (out_dir / "Super_STF_ja.stf").exists()


def test_missing_file():
    result = runner.invoke(app, ["info", "/nonexistent/file.stf"])
    assert result.exit_code != 0
