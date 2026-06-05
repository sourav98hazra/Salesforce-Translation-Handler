"""Scope (component / key allowlist / denylist) tests."""

from __future__ import annotations

from pathlib import Path

from stx.model import Document, Entry
from stx.scope import Scope, StatusFilter


def _doc() -> Document:
    return Document(
        entries=[
            Entry(key="CustomLabel.Hello", label="Hello"),
            Entry(key="CustomLabel.Bye", label="Goodbye"),
            Entry(key="CustomApp.Inside", label="Inside Sales"),
            Entry(key="CustomField.Account.Name.FieldLabel", label="Name"),
            Entry(key="CustomField.Account.CreatedDate.FieldLabel", label="Created Date", translation="作成日"),
        ]
    )


def test_default_scope_includes_all_untranslated() -> None:
    scope = Scope()
    doc = _doc()
    assert scope.estimate_count(doc) == 4  # all except the already-translated row


def test_component_filter() -> None:
    doc = _doc()
    scope = Scope(components={"CustomLabel"})
    matches = scope.filter_entries(doc.entries)
    assert len(matches) == 2
    assert all(e.key.startswith("CustomLabel.") for e in matches)


def test_include_keys_exact() -> None:
    doc = _doc()
    scope = Scope(include_keys=["CustomLabel.Hello"])
    matches = scope.filter_entries(doc.entries)
    assert {e.key for e in matches} == {"CustomLabel.Hello"}


def test_include_patterns_glob() -> None:
    doc = _doc()
    scope = Scope(include_patterns=["CustomField.*"])
    matches = scope.filter_entries(doc.entries)
    # CreatedDate is already translated -> excluded by default status filter.
    assert {e.key for e in matches} == {"CustomField.Account.Name.FieldLabel"}


def test_exclude_wins_over_include() -> None:
    doc = _doc()
    scope = Scope(
        include_patterns=["CustomLabel.*"],
        exclude_keys=["CustomLabel.Hello"],
    )
    assert {e.key for e in scope.filter_entries(doc.entries)} == {"CustomLabel.Bye"}


def test_status_filter_translated_only() -> None:
    doc = _doc()
    scope = Scope(status=StatusFilter.TRANSLATED)
    matches = scope.filter_entries(doc.entries)
    assert {e.key for e in matches} == {"CustomField.Account.CreatedDate.FieldLabel"}


def test_round_trip_via_json(tmp_path: Path) -> None:
    scope = Scope(
        components={"CustomLabel", "CustomApp"},
        status=StatusFilter.UNTRANSLATED,
        include_keys=["CustomLabel.Hello"],
        include_patterns=["CustomApp.*"],
        exclude_keys=["CustomLabel.Bye"],
        exclude_patterns=["*.HelpText"],
        name="Test scope",
    )
    path = scope.save(tmp_path / "scope.stxscope.json")
    loaded = Scope.load(path)
    assert loaded.components == scope.components
    assert loaded.status == scope.status
    assert loaded.include_keys == scope.include_keys
    assert loaded.include_patterns == scope.include_patterns
    assert loaded.exclude_keys == scope.exclude_keys
    assert loaded.exclude_patterns == scope.exclude_patterns


def test_discover_finds_neighbouring_scope(tmp_path: Path) -> None:
    source = tmp_path / "input.stf"
    source.write_text("# placeholder\n", encoding="utf-8")
    scope_file = tmp_path / "input.stf.stxscope.json"
    Scope().save(scope_file)
    found = Scope.discover(source)
    assert found is not None
    assert found.resolve() == scope_file.resolve()


def test_all_components_of_helper() -> None:
    doc = _doc()
    scope = Scope.all_components_of(doc)
    assert scope.components == {"CustomLabel", "CustomApp", "CustomField"}
