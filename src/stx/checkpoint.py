"""Checkpoint persistence for resumable translation runs.

After each row is translated, the checkpoint is updated on disk so that
a crash or interrupt can be recovered from the last known state.  The
file is removed automatically on successful completion of a full run.

The checkpoint is a simple JSON file stored under the user's cache
directory (``~/.cache/salesforce-translation-handler/checkpoints/`` on
Linux/macOS, a platform-equivalent on Windows).

File format (version 1)::

    {
        "version": 1,
        "source_file": "/path/to/input.xlsx",
        "target_lang": "ja",
        "entries": {
            "0": {"key": "CustomLabel.Greeting", "translation": "...", "status": "..."},
            "3": {"key": "ButtonOrLink.Save", "translation": "...", "status": "..."}
        }
    }

Atomic writes are achieved by writing to a temporary file in the same
directory, then calling :func:`os.replace` (atomic on POSIX and modern
Windows NTFS).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Dict, Optional


def default_checkpoint_dir() -> Path:
    """Return the default checkpoint directory.

    Uses ``~/.cache/salesforce-translation-handler/checkpoints/``.
    """
    return Path.home() / ".cache" / "salesforce-translation-handler" / "checkpoints"


def _run_id(source_file: str, target_lang: str) -> str:
    """Derive a stable run ID from source file path and target language."""
    raw = f"{source_file}::{target_lang}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class CheckpointStore:
    """Persist translation progress to disk for crash recovery.

    Parameters
    ----------
    source_file:
        Absolute path (as string) to the source file being translated.
    target_lang:
        Target language code (e.g. ``"ja"``).
    checkpoint_dir:
        Directory in which to store checkpoint files.  Defaults to
        :func:`default_checkpoint_dir`.
    """

    def __init__(
        self,
        source_file: str,
        target_lang: str,
        checkpoint_dir: Optional[Path] = None,
    ) -> None:
        self.source_file = source_file
        self.target_lang = target_lang
        self._dir = checkpoint_dir or default_checkpoint_dir()
        self._run_id = _run_id(source_file, target_lang)
        self._path = self._dir / f"{self._run_id}.json"
        # In-memory cache of loaded entries (populated lazily by load()).
        self._loaded: Optional[Dict[int, dict]] = None

    @property
    def path(self) -> Path:
        """Path to the checkpoint file."""
        return self._path

    def exists(self) -> bool:
        """Return True if a checkpoint file exists for this run."""
        return self._path.is_file()

    def load(self) -> Dict[int, dict]:
        """Load checkpoint data from disk.

        Returns a dict mapping entry index (int) to a dict with keys
        ``key``, ``translation``, and ``status``.  Returns an empty dict
        if the checkpoint file does not exist or is invalid.
        """
        if self._loaded is not None:
            return self._loaded

        if not self._path.is_file():
            self._loaded = {}
            return self._loaded

        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            self._loaded = {}
            return self._loaded

        if not isinstance(data, dict) or data.get("version") != 1:
            self._loaded = {}
            return self._loaded

        entries = data.get("entries", {})
        self._loaded = {int(k): v for k, v in entries.items() if isinstance(v, dict)}
        return self._loaded

    def save_progress(self, index: int, key: str, translation: str, status: str) -> None:
        """Record a completed entry and persist to disk atomically.

        Parameters
        ----------
        index:
            Entry index in the document.
        key:
            The entry's key (for human-readable inspection of the file).
        translation:
            The resulting translation text.
        status:
            Status string (e.g. ``"Translated"``, ``"Translated (TM hit)"``).
        """
        # Ensure the in-memory cache is initialized.
        if self._loaded is None:
            self.load()
        assert self._loaded is not None

        self._loaded[index] = {
            "key": key,
            "translation": translation,
            "status": status,
        }
        self._write()

    def clear(self) -> None:
        """Remove the checkpoint file (called on successful completion)."""
        try:
            self._path.unlink(missing_ok=True)
        except OSError:
            pass
        self._loaded = None

    def _write(self) -> None:
        """Atomically write the current state to disk."""
        self._dir.mkdir(parents=True, exist_ok=True)

        data = {
            "version": 1,
            "source_file": self.source_file,
            "target_lang": self.target_lang,
            "entries": {str(k): v for k, v in (self._loaded or {}).items()},
        }

        # Write to a temp file in the same directory, then atomically rename.
        fd, tmp_path = tempfile.mkstemp(
            suffix=".tmp", prefix=self._run_id + "_", dir=str(self._dir)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, str(self._path))
        except BaseException:
            # Clean up temp file on failure.
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
