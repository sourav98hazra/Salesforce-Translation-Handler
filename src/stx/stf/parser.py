"""Parser for Salesforce ``.stf`` translation files.

The parser is tolerant of all STF flavours produced by Salesforce:

* "Outdated and untranslated" exports (``KEY\\tLABEL`` rows).
* "Bilingual" exports (``KEY\\tLABEL\\tTRANSLATION\\tOUT_OF_DATE`` rows).
* Mixed files containing both ``------------------TRANSLATED-------------------``
  and ``------------------OUTDATED AND UNTRANSLATED-----------------`` sections.

The header block (``# Language: ...``, ``Language code: ...``, ``Type: ...``,
``Translation type: ...``) is captured into the resulting
:class:`stx.model.Document`.  Comment lines (``#`` prefix) and section
separator lines (``-`` prefix) are skipped.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Union

from ..model import Document, Entry

# Lines beginning with ``#`` or ``-`` are comments / section markers and never
# represent data rows.
_SKIP_LINE_RE = re.compile(r"^[\-#]")

# Header metadata patterns.  ``# Language:`` is comment-style, the rest are
# bare ``key: value`` lines emitted by Salesforce.
_LANGUAGE_RE = re.compile(r"^\s*#\s*Language\s*:\s*(.+?)\s*$", re.IGNORECASE)
_LANGUAGE_CODE_RE = re.compile(r"^\s*Language code\s*:\s*(.+?)\s*$", re.IGNORECASE)
_TYPE_RE = re.compile(r"^\s*Type\s*:\s*(.+?)\s*$", re.IGNORECASE)
_TRANSLATION_TYPE_RE = re.compile(r"^\s*Translation type\s*:\s*(.+?)\s*$", re.IGNORECASE)


def parse_stf(source: Union[str, Path]) -> Document:
    """Parse an STF file from disk.

    Parameters
    ----------
    source:
        Path to a ``.stf`` file (UTF-8 encoded).

    Returns
    -------
    Document
        The parsed document, with metadata header and entries populated
        in original order.
    """

    path = Path(source)
    text = path.read_text(encoding="utf-8")
    return parse_stf_text(text)


def parse_stf_text(text: str) -> Document:
    """Parse STF content from an in-memory string.

    Useful for tests and for re-parsing the contents of a file already
    held in memory (e.g. when uploaded through the GUI).
    """

    return _parse_lines(text.splitlines())


def _parse_lines(lines: Iterable[str]) -> Document:
    doc = Document()

    for raw_line in lines:
        # Empty / whitespace-only lines carry no information.
        if not raw_line.strip():
            continue

        # Capture metadata from header comments before they are skipped.
        if raw_line.lstrip().startswith("#"):
            _maybe_capture_metadata(raw_line, doc)
            continue

        # Section separators (e.g. "-----TRANSLATED-----").
        if _SKIP_LINE_RE.match(raw_line):
            continue

        # Bare ``key: value`` metadata (Salesforce emits these without a ``#``).
        if _maybe_capture_metadata(raw_line, doc):
            continue

        # Otherwise treat the line as a tab-separated data row.
        parts = raw_line.split("\t")
        if len(parts) < 2:
            # Not a recognisable row -- skip silently to mirror the legacy
            # PowerShell parser's tolerance.
            continue

        key = parts[0]
        label = parts[1]
        translation = parts[2] if len(parts) >= 3 else ""

        # The 4th column is "OUT OF DATE" (typically "-"), which we drop --
        # the writer regenerates it deterministically from translation status.
        doc.entries.append(Entry(key=key, label=label, translation=translation))

    return doc


def _maybe_capture_metadata(line: str, doc: Document) -> bool:
    """Attempt to capture a metadata field from ``line`` into ``doc``.

    Returns ``True`` if the line was recognised as metadata.
    """
    m = _LANGUAGE_RE.match(line)
    if m:
        doc.language = m.group(1)
        return True

    m = _LANGUAGE_CODE_RE.match(line)
    if m:
        doc.language_code = m.group(1)
        return True

    m = _TYPE_RE.match(line)
    if m:
        doc.stf_type = m.group(1)
        return True

    m = _TRANSLATION_TYPE_RE.match(line)
    if m:
        doc.translation_type = m.group(1)
        return True

    return False
