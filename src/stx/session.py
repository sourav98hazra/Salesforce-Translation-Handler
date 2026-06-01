"""Session persistence for saving and restoring application state.

Provides a SessionManager that serializes the full application state to
a versioned JSON project file (.stxproj).  This allows users to close
the app and resume exactly where they left off.

The project file is stored under the user's cache directory
(``~/.cache/salesforce-translation-handler/sessions/`` on Linux/macOS,
a platform-equivalent on Windows).  Session isolation is achieved by
hashing the absolute path of the source file.

File format (version 1)::

    {
        "version": 1,
        "source_file_path": "/path/to/input.stf",
        "file_hash": "<sha256-of-absolute-path>",
        "document": { ... },
        "target_language_code": "ja",
        "target_language_name": "Japanese",
        "source_language_code": "en",
        "backend_key": "google",
        "scope_path": null,
        "glossary_path": null,
        "memory_path": null,
        "translation_summaries": [...],
        "translation_statuses": [...],
        "phase_status": [0, 0, 2, 0, 0, 0],
        "undo_commands": [],
        "created_at": "2025-01-01T00:00:00",
        "updated_at": "2025-01-01T00:00:00"
    }

Atomic writes are achieved by writing to a temporary file in the same
directory, then calling :func:`os.replace` (atomic on POSIX and modern
Windows NTFS).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .model import Document, Entry
from .translate.runner import SheetSummary, StatusEntry


def _default_sessions_dir() -> Path:
    """Return the default sessions directory.

    Uses ``~/.cache/salesforce-translation-handler/sessions/``.
    """
    return Path.home() / ".cache" / "salesforce-translation-handler" / "sessions"


def _file_hash(source_path: Path) -> str:
    """Derive a stable hash from the absolute path of the source file."""
    return hashlib.sha256(str(source_path.resolve()).encode()).hexdigest()


def _serialize_document(doc: Document) -> Dict[str, Any]:
    """Serialize a Document to a JSON-compatible dict."""
    entries = []
    for entry in doc.entries:
        entries.append({
            "key": entry.key,
            "label": entry.label,
            "translation": entry.translation,
            "approved": entry.approved,
        })
    return {
        "language": doc.language,
        "language_code": doc.language_code,
        "stf_type": doc.stf_type,
        "translation_type": doc.translation_type,
        "entries": entries,
    }


def _deserialize_document(data: Dict[str, Any]) -> Document:
    """Deserialize a dict back into a Document."""
    entries = []
    for e in data.get("entries", []):
        entries.append(Entry(
            key=e.get("key", ""),
            label=e.get("label", ""),
            translation=e.get("translation", ""),
            approved=e.get("approved", False),
        ))
    return Document(
        language=data.get("language", ""),
        language_code=data.get("language_code", ""),
        stf_type=data.get("stf_type", "Bilingual"),
        translation_type=data.get("translation_type", "Metadata"),
        entries=entries,
    )


def _serialize_sheet_summary(s: SheetSummary) -> Dict[str, Any]:
    """Serialize a SheetSummary to a dict."""
    return {
        "sheet_name": s.sheet_name,
        "total_rows": s.total_rows,
        "translated_rows": s.translated_rows,
        "skipped_rows": s.skipped_rows,
        "cached_rows": s.cached_rows,
        "deduped_rows": s.deduped_rows,
    }


def _deserialize_sheet_summary(d: Dict[str, Any]) -> SheetSummary:
    """Deserialize a dict back into a SheetSummary."""
    return SheetSummary(
        sheet_name=d.get("sheet_name", ""),
        total_rows=d.get("total_rows", 0),
        translated_rows=d.get("translated_rows", 0),
        skipped_rows=d.get("skipped_rows", 0),
        cached_rows=d.get("cached_rows", 0),
        deduped_rows=d.get("deduped_rows", 0),
    )


def _serialize_status_entry(s: StatusEntry) -> Dict[str, Any]:
    """Serialize a StatusEntry to a dict."""
    return {
        "sheet_name": s.sheet_name,
        "row_index": s.row_index,
        "key": s.key,
        "label": s.label,
        "translation": s.translation,
        "status": s.status,
    }


def _deserialize_status_entry(d: Dict[str, Any]) -> StatusEntry:
    """Deserialize a dict back into a StatusEntry."""
    return StatusEntry(
        sheet_name=d.get("sheet_name", ""),
        row_index=d.get("row_index", 0),
        key=d.get("key", ""),
        label=d.get("label", ""),
        translation=d.get("translation", ""),
        status=d.get("status", ""),
    )


def _serialize_undo_command(cmd: Any) -> Dict[str, Any]:
    """Serialize an UndoCommand to a dict."""
    return {
        "row": cmd.row,
        "column": cmd.column,
        "old_value": cmd.old_value,
        "new_value": cmd.new_value,
    }


class SessionManager:
    """Manage session persistence for the application.

    Parameters
    ----------
    sessions_dir:
        Directory in which to store session files.  Defaults to
        :func:`_default_sessions_dir`.
    """

    def __init__(self, sessions_dir: Optional[Path] = None) -> None:
        self._dir = sessions_dir or _default_sessions_dir()

    @property
    def sessions_dir(self) -> Path:
        """Return the sessions directory."""
        return self._dir

    def auto_save_path(self, source_path: Path) -> Path:
        """Return the auto-save path for a given source file.

        The path is deterministic: derived from the SHA-256 hash of the
        source file's absolute path.
        """
        h = _file_hash(source_path)
        return self._dir / f"{h}.stxproj"

    def has_session(self, source_path: Path) -> bool:
        """Return True if an auto-save session exists for source_path."""
        return self.auto_save_path(source_path).is_file()

    def clear_session(self, source_path: Path) -> None:
        """Remove the auto-save session for a source file."""
        path = self.auto_save_path(source_path)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    def clear_all_sessions(self) -> None:
        """Remove all session files from the sessions directory."""
        if self._dir.is_dir():
            shutil.rmtree(self._dir, ignore_errors=True)

    def save(self, state: Any, path: Path) -> None:
        """Serialize application state and write atomically to path.

        Parameters
        ----------
        state:
            An AppState instance (or any object with the expected attributes).
        path:
            Destination file path (.stxproj).
        """
        now = datetime.now(timezone.utc).isoformat()

        # Try to read existing created_at if the file exists
        created_at = now
        if path.is_file():
            try:
                with open(path, encoding="utf-8") as f:
                    existing = json.load(f)
                created_at = existing.get("created_at", now)
            except (json.JSONDecodeError, OSError):
                pass

        # Determine the source file path
        source_file_path = ""
        if state.source_stf_path is not None:
            source_file_path = str(state.source_stf_path.resolve())

        # Serialize document
        doc_data = None
        if state.document is not None:
            doc_data = _serialize_document(state.document)

        # Serialize translation summaries and statuses
        summaries = [_serialize_sheet_summary(s) for s in state.translation_summaries]
        statuses = [_serialize_status_entry(s) for s in state.translation_statuses]

        # Serialize phase_status as list of ints
        phase_status = [int(p) for p in state.phase_status]

        # Serialize undo commands (best-effort)
        undo_commands: List[Dict[str, Any]] = []
        if hasattr(state, "_undo_commands"):
            for cmd in state._undo_commands:
                undo_commands.append(_serialize_undo_command(cmd))

        data = {
            "version": 1,
            "source_file_path": source_file_path,
            "file_hash": _file_hash(Path(source_file_path)) if source_file_path else "",
            "document": doc_data,
            "target_language_code": state.target_language_code,
            "target_language_name": state.target_language_name,
            "source_language_code": state.source_language_code,
            "backend_key": state.backend_key,
            "scope_path": str(state.scope_path) if state.scope_path else None,
            "glossary_path": str(state.glossary_path) if state.glossary_path else None,
            "memory_path": str(state.memory_path) if state.memory_path else None,
            "translation_summaries": summaries,
            "translation_statuses": statuses,
            "phase_status": phase_status,
            "undo_commands": undo_commands,
            "created_at": created_at,
            "updated_at": now,
        }

        # Atomic write
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            suffix=".tmp", prefix="session_", dir=str(path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, str(path))
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def load(self, path: Path) -> Dict[str, Any]:
        """Read and validate a session project file.

        Parameters
        ----------
        path:
            Path to the .stxproj file to load.

        Returns
        -------
        dict
            A dictionary with all session fields.  The caller is
            responsible for reconstructing AppState from this dict.

        Raises
        ------
        FileNotFoundError:
            If the file does not exist.
        ValueError:
            If the file is not valid JSON or has an incompatible version.
        """
        if not path.is_file():
            raise FileNotFoundError(f"Session file not found: {path}")

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise ValueError("Invalid session file: root is not a JSON object")

        version = data.get("version")
        if version != 1:
            raise ValueError(
                f"Incompatible session file version: {version} (expected 1)"
            )

        # Deserialize document if present
        doc_data = data.get("document")
        document = _deserialize_document(doc_data) if doc_data else None

        # Deserialize summaries and statuses
        summaries = [
            _deserialize_sheet_summary(s)
            for s in data.get("translation_summaries", [])
        ]
        statuses = [
            _deserialize_status_entry(s)
            for s in data.get("translation_statuses", [])
        ]

        return {
            "version": data["version"],
            "source_file_path": data.get("source_file_path", ""),
            "file_hash": data.get("file_hash", ""),
            "document": document,
            "target_language_code": data.get("target_language_code", "ja"),
            "target_language_name": data.get("target_language_name", "Japanese"),
            "source_language_code": data.get("source_language_code", "en"),
            "backend_key": data.get("backend_key", "google"),
            "scope_path": data.get("scope_path"),
            "glossary_path": data.get("glossary_path"),
            "memory_path": data.get("memory_path"),
            "translation_summaries": summaries,
            "translation_statuses": statuses,
            "phase_status": data.get("phase_status", [0] * 6),
            "undo_commands": data.get("undo_commands", []),
            "created_at": data.get("created_at", ""),
            "updated_at": data.get("updated_at", ""),
        }
