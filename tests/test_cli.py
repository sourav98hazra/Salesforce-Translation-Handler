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


# ---------------------------------------------------------------------------
# Replace command tests
# ---------------------------------------------------------------------------


def test_replace_plain(tmp_path):
    """Plain text find and replace in translations."""
    stf = _write_sample_stf(tmp_path)
    result = runner.invoke(
        app, ["replace", str(stf), "--find", "Konnichiwa", "--replace", "Hello-JP"]
    )
    assert result.exit_code == 0
    assert "1" in result.output  # 1 occurrence replaced
    # Verify the file was actually modified
    from stx.stf import parse_stf

    doc = parse_stf(stf)
    assert doc.entries[0].translation == "Hello-JP"


def test_replace_regex(tmp_path):
    """Regex-based find and replace."""
    doc = Document(
        language="Japanese",
        language_code="ja",
        entries=[
            Entry(key="CustomLabel.A", label="Hello", translation="Test 123"),
            Entry(key="CustomLabel.B", label="World", translation="Test 456"),
        ],
    )
    from stx.stf import render_full_stf

    stf = tmp_path / "regex.stf"
    stf.write_text(render_full_stf(doc), encoding="utf-8")

    result = runner.invoke(
        app, ["replace", str(stf), "--find", r"Test \d+", "--replace", "Result", "--regex"]
    )
    assert result.exit_code == 0
    assert "2" in result.output

    from stx.stf import parse_stf

    updated = parse_stf(stf)
    assert updated.entries[0].translation == "Result"
    assert updated.entries[1].translation == "Result"


def test_replace_case_sensitive(tmp_path):
    """Case-sensitive replacement only matches exact case."""
    doc = Document(
        language="Japanese",
        language_code="ja",
        entries=[
            Entry(key="CustomLabel.A", label="Hello", translation="hello world"),
            Entry(key="CustomLabel.B", label="World", translation="Hello World"),
        ],
    )
    from stx.stf import render_full_stf

    stf = tmp_path / "case.stf"
    stf.write_text(render_full_stf(doc), encoding="utf-8")

    result = runner.invoke(
        app,
        ["replace", str(stf), "--find", "Hello", "--replace", "Hi", "--case-sensitive"],
    )
    assert result.exit_code == 0
    assert "1" in result.output  # only "Hello World" matches

    from stx.stf import parse_stf

    updated = parse_stf(stf)
    assert updated.entries[0].translation == "hello world"  # unchanged
    assert updated.entries[1].translation == "Hi World"


def test_replace_no_matches(tmp_path):
    """When nothing matches, print a message and do not error."""
    stf = _write_sample_stf(tmp_path)
    result = runner.invoke(
        app, ["replace", str(stf), "--find", "NONEXISTENT", "--replace", "X"]
    )
    assert result.exit_code == 0
    assert "No matches" in result.output


def test_replace_scope_label(tmp_path):
    """Replace in label field using --scope label."""
    doc = Document(
        language="Japanese",
        language_code="ja",
        entries=[
            Entry(key="CustomLabel.A", label="Hello World", translation="Konnichiwa"),
            Entry(key="CustomLabel.B", label="Hello Again", translation="Hello"),
        ],
    )
    from stx.stf import render_full_stf

    stf = tmp_path / "scope.stf"
    stf.write_text(render_full_stf(doc), encoding="utf-8")

    result = runner.invoke(
        app, ["replace", str(stf), "--find", "Hello", "--replace", "Hi", "--scope", "label"]
    )
    assert result.exit_code == 0
    assert "2" in result.output

    from stx.stf import parse_stf

    updated = parse_stf(stf)
    assert updated.entries[0].label == "Hi World"
    assert updated.entries[1].label == "Hi Again"
    # Translation with "Hello" should NOT be changed (wrong scope)
    assert updated.entries[1].translation == "Hello"


def test_validate_export_report_csv(tmp_path):
    """--export-report with .csv extension writes a CSV file."""
    doc = Document(
        language="Japanese", language_code="ja",
        entries=[
            Entry(key="CustomLabel.A", label="Hello", translation="Konnichiwa"),
            Entry(key="CustomLabel.A", label="World", translation="Sekai"),
        ],
    )
    stf = tmp_path / "dupes.stf"
    stf.write_text(render_full_stf(doc), encoding="utf-8")
    report_path = tmp_path / "report.csv"
    result = runner.invoke(app, ["validate", str(stf), "--export-report", str(report_path)])
    # exit code 1 because there are errors, but report still written
    assert result.exit_code == 1
    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "severity" in content
    assert "duplicate_key" in content


def test_validate_export_report_json(tmp_path):
    """--export-report with .json extension writes valid JSON."""
    import json

    doc = Document(
        language="Japanese", language_code="ja",
        entries=[
            Entry(key="CustomLabel.A", label="Hello", translation="Konnichiwa"),
            Entry(key="CustomLabel.A", label="World", translation="Sekai"),
        ],
    )
    stf = tmp_path / "dupes.stf"
    stf.write_text(render_full_stf(doc), encoding="utf-8")
    report_path = tmp_path / "report.json"
    result = runner.invoke(app, ["validate", str(stf), "--export-report", str(report_path)])
    assert result.exit_code == 1
    assert report_path.exists()
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["summary"]["errors"] >= 1
    assert "duplicate_key" in data["issues_by_category"]
