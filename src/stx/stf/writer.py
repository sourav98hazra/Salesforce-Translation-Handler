"""Writer for Salesforce ``.stf`` translation files.

The output format is byte-compatible with the legacy
``ExcelToSTFV2.ps1`` script:

* UTF-8 encoded.
* ``LF`` line endings (no CRLF, no BOM).
* Three files emitted per run:

    - ``Super_STF_<code>.stf``         -- bilingual full file.
    - ``TranslatedOnly_STF_<code>.stf`` -- translated rows only.
    - ``UntranslatedOnly_STF_<code>.stf`` -- untranslated rows only.

The section separator lines (``------------------TRANSLATED-------------------``
and ``------------------OUTDATED AND UNTRANSLATED-----------------``) are
reproduced character-for-character to preserve interoperability with any
downstream tooling that pattern-matches them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..model import Document, Entry

# These separator strings are intentionally hard-coded (with their exact
# dash counts) to remain byte-compatible with ExcelToSTFV2.ps1.
_TRANSLATED_SEPARATOR = "------------------TRANSLATED-------------------"
_OUTDATED_SEPARATOR = "------------------OUTDATED AND UNTRANSLATED-----------------"

_FULL_HEADER_COLUMNS = "# KEY\tLABEL\tTRANSLATION\tOUT OF DATE"
_UNTRANSLATED_HEADER_COLUMNS = "# KEY\tLABEL"


@dataclass(frozen=True)
class STFWriteResult:
    """Paths of the three files emitted by :func:`write_stf_files`."""

    full: Path
    translated_only: Path
    untranslated_only: Path

    def as_list(self) -> list[Path]:
        return [self.full, self.translated_only, self.untranslated_only]


# ---------------------------------------------------------------------------
# Public rendering helpers (return strings; useful for previews and tests).
# ---------------------------------------------------------------------------

def render_full_stf(doc: Document) -> str:
    """Render the bilingual ``Super_STF`` file content as a string.

    The produced text terminates without a trailing newline, matching the
    legacy script's ``-join "`n"`` behaviour exactly.
    """

    lines: list[str] = []
    lines.append(f"# Language: {doc.language}")
    lines.append(f"Language code: {doc.language_code}")
    lines.append("Type: Bilingual")
    lines.append(f"Translation type: {doc.translation_type or 'Metadata'}")
    lines.append("")
    lines.append(_TRANSLATED_SEPARATOR)
    lines.append(_FULL_HEADER_COLUMNS)

    for entry in doc.entries:
        if entry.translation.strip():
            lines.append(f"{entry.key}\t{entry.label}\t{entry.translation.strip()}\t-")
        else:
            lines.append(f"{entry.key}\t{entry.label}")

    lines.append("")
    lines.append(_OUTDATED_SEPARATOR)
    lines.append("")
    lines.append(_UNTRANSLATED_HEADER_COLUMNS)
    return "\n".join(lines)


def render_translated_only_stf(doc: Document) -> str:
    """Render only the rows that have a non-blank translation."""

    lines: list[str] = [_FULL_HEADER_COLUMNS]
    for entry in doc.translated():
        lines.append(f"{entry.key}\t{entry.label}\t{entry.translation.strip()}\t-")
    return "\n".join(lines)


def render_untranslated_only_stf(doc: Document) -> str:
    """Render only the rows that have no translation."""

    lines: list[str] = [_UNTRANSLATED_HEADER_COLUMNS]
    for entry in doc.untranslated():
        lines.append(f"{entry.key}\t{entry.label}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Disk emission
# ---------------------------------------------------------------------------

def write_stf_files(
    doc: Document,
    output_dir: Path | str,
    language_name: str | None = None,
    language_code: str | None = None,
) -> STFWriteResult:
    """Emit the three STF files to ``output_dir``.

    Parameters
    ----------
    doc:
        Document to render.  Its ``language`` / ``language_code`` are used
        unless overridden by the explicit arguments.
    output_dir:
        Destination directory (created if missing).
    language_name, language_code:
        Optional overrides for the document's metadata.  Useful when the
        caller wants to retarget the export without mutating ``doc``.

    Returns
    -------
    STFWriteResult
        Paths of the three emitted files.
    """

    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    if language_name is not None or language_code is not None:
        doc = Document(
            language=language_name if language_name is not None else doc.language,
            language_code=language_code if language_code is not None else doc.language_code,
            stf_type="Bilingual",
            translation_type=doc.translation_type or "Metadata",
            entries=list(doc.entries),
        )

    code = doc.language_code or "xx"
    full_path = target_dir / f"Super_STF_{code}.stf"
    trans_path = target_dir / f"TranslatedOnly_STF_{code}.stf"
    untrans_path = target_dir / f"UntranslatedOnly_STF_{code}.stf"

    _write_lf_utf8(full_path, render_full_stf(doc))
    _write_lf_utf8(trans_path, render_translated_only_stf(doc))
    _write_lf_utf8(untrans_path, render_untranslated_only_stf(doc))

    return STFWriteResult(full=full_path, translated_only=trans_path, untranslated_only=untrans_path)


def _write_lf_utf8(path: Path, text: str) -> None:
    """Write ``text`` as UTF-8 with LF line endings and no BOM.

    ``Path.write_text`` is intentionally avoided because it honours the
    platform's default newline translation on Windows (``\\r\\n``), which
    would corrupt the output format.
    """
    data = text.encode("utf-8")
    # Belt-and-braces: ensure no embedded CR characters slipped through.
    data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    path.write_bytes(data)


def _iter_lines_for_full(doc: Document) -> Iterable[str]:  # pragma: no cover - kept for symmetry
    yield render_full_stf(doc)
