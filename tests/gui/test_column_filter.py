"""Tests for the Phase 4 column-wise (Excel-like) filter proxy.

Exercises the ``_ComponentStatusFilter`` per-column value filtering used
by the header context menu (Issue 8).
"""

from __future__ import annotations

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest

from stx.gui.pages.phase4_review import (
    _APPROVED_COL,
    _EntriesModel,
    _ComponentStatusFilter,
)
from stx.model import Document, Entry

# Column indices mirror _HEADERS = ["#", "Key", "Component", "Status", "Label",
# "Translation", "Approved"].
_COMPONENT_COL = 2
_STATUS_COL = 3


@pytest.fixture
def doc():
    return Document(
        language="Japanese",
        language_code="ja",
        entries=[
            Entry(key="CustomLabel.A", label="Alpha", translation="A-ja"),
            Entry(key="CustomLabel.B", label="Bravo", translation=""),
            Entry(key="CustomField.C.FieldLabel", label="Charlie", translation="C-ja"),
            Entry(key="CustomField.D.FieldLabel", label="Delta", translation=""),
        ],
    )


@pytest.fixture
def proxy(doc, qtbot):
    model = _EntriesModel(doc)
    px = _ComponentStatusFilter()
    px.setSourceModel(model)
    return px


def _visible_keys(proxy):
    keys = []
    for r in range(proxy.rowCount()):
        # Key column is index 1.
        idx = proxy.index(r, 1)
        keys.append(idx.data())
    return keys


def test_no_filter_shows_all_rows(proxy):
    assert proxy.rowCount() == 4


def test_set_column_filter_limits_rows(proxy):
    # Only keep the CustomLabel component.
    proxy.set_column_filter(_COMPONENT_COL, {"CustomLabel"})
    assert proxy.rowCount() == 2
    keys = _visible_keys(proxy)
    assert "CustomLabel.A" in keys
    assert "CustomLabel.B" in keys
    assert "CustomField.C.FieldLabel" not in keys


def test_clear_column_filter_restores_rows(proxy):
    proxy.set_column_filter(_COMPONENT_COL, {"CustomLabel"})
    assert proxy.rowCount() == 2
    proxy.clear_column_filter(_COMPONENT_COL)
    assert proxy.rowCount() == 4


def test_column_filter_accessor(proxy):
    assert proxy.column_filter(_COMPONENT_COL) is None
    assert proxy.has_column_filter(_COMPONENT_COL) is False
    proxy.set_column_filter(_COMPONENT_COL, {"CustomLabel"})
    assert proxy.column_filter(_COMPONENT_COL) == {"CustomLabel"}
    assert proxy.has_column_filter(_COMPONENT_COL) is True


def test_empty_allowed_set_hides_all(proxy):
    proxy.set_column_filter(_COMPONENT_COL, set())
    assert proxy.rowCount() == 0


def test_set_column_filter_none_clears(proxy):
    proxy.set_column_filter(_COMPONENT_COL, {"CustomLabel"})
    assert proxy.rowCount() == 2
    proxy.set_column_filter(_COMPONENT_COL, None)
    assert proxy.rowCount() == 4


def test_filter_on_status_column(proxy):
    # Status column distinguishes Translated vs Untranslated.
    distinct = {
        str(proxy.sourceModel().index(r, _STATUS_COL).data() or "")
        for r in range(proxy.sourceModel().rowCount())
    }
    assert "Translated" in distinct
    proxy.set_column_filter(_STATUS_COL, {"Translated"})
    # Two entries have translations.
    assert proxy.rowCount() == 2


def test_multiple_column_filters_compose(proxy):
    proxy.set_column_filter(_COMPONENT_COL, {"CustomLabel"})
    proxy.set_column_filter(_STATUS_COL, {"Translated"})
    # Only CustomLabel.A is both CustomLabel and Translated.
    assert proxy.rowCount() == 1
    assert _visible_keys(proxy) == ["CustomLabel.A"]
