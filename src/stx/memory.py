"""Translation Memory (TM) backed by SQLite.

The TM caches every successful ``(source_text, source_lang, target_lang)
-> translation`` triple.  Subsequent runs hit the cache before touching
the network -- saving time, avoiding rate limits, and producing
identical translations across reviews.

Schema
------
A single table ``translations``::

    source TEXT, source_lang TEXT, target_lang TEXT, translation TEXT,
    created_at INTEGER, hits INTEGER  -- (source, source_lang, target_lang) PK

The DB file lives wherever the caller chooses.  The GUI defaults to a
per-user location (``~/.cache/salesforce-translation-handler/tm.sqlite``);
power users can point the CLI at a project-local DB to share a TM
between teammates via VCS.
"""

from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

DEFAULT_TM_FILENAME = "tm.sqlite"


@dataclass
class TranslationMemory:
    """SQLite-backed translation memory."""

    path: Path

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS translations (
                    source TEXT NOT NULL,
                    source_lang TEXT NOT NULL,
                    target_lang TEXT NOT NULL,
                    translation TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    hits INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (source, source_lang, target_lang)
                )
                """
            )
            # PRAGMA tweaks for write throughput on bulk loads.  WAL keeps the
            # DB readable while another process writes.
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, isolation_level=None)  # autocommit
        try:
            yield conn
        finally:
            conn.close()

    # ------------------------------------------------------------------ public

    def get(self, source: str, source_lang: str, target_lang: str) -> Optional[str]:
        """Return the cached translation for the given triple, or ``None``."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT translation FROM translations "
                "WHERE source = ? AND source_lang = ? AND target_lang = ?",
                (source, source_lang, target_lang),
            ).fetchone()
            if row is None:
                return None
            # Update hit count (best effort -- ignore if it fails).
            try:
                conn.execute(
                    "UPDATE translations SET hits = hits + 1 "
                    "WHERE source = ? AND source_lang = ? AND target_lang = ?",
                    (source, source_lang, target_lang),
                )
            except sqlite3.Error:  # pragma: no cover
                pass
            return row[0]

    def put(self, source: str, source_lang: str, target_lang: str, translation: str) -> None:
        """Insert or replace a (source, source_lang, target_lang) -> translation mapping."""
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO translations "
                "(source, source_lang, target_lang, translation, created_at, hits) "
                "VALUES (?, ?, ?, ?, ?, COALESCE("
                "(SELECT hits FROM translations "
                "WHERE source = ? AND source_lang = ? AND target_lang = ?), 0))",
                (
                    source, source_lang, target_lang, translation, int(time.time()),
                    source, source_lang, target_lang,
                ),
            )

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM translations").fetchone()
            return int(row[0]) if row else 0

    def stats(self) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(hits), 0) FROM translations"
            ).fetchone()
            entries = int(row[0]) if row else 0
            total_hits = int(row[1]) if row else 0
        size_bytes = self.path.stat().st_size if self.path.exists() else 0
        return {
            "entries": entries,
            "hits": total_hits,
            "size_bytes": size_bytes,
            "path": str(self.path),
        }

    def clear(self) -> None:
        """Wipe every entry (kept for the "Clear cache" button in settings)."""
        with self._connect() as conn:
            conn.execute("DELETE FROM translations")

    def all_sources(self, source_lang: str, target_lang: str) -> List[Tuple[str, str]]:
        """Return all (source, translation) pairs for a language pair."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT source, translation FROM translations "
                "WHERE source_lang = ? AND target_lang = ?",
                (source_lang, target_lang),
            ).fetchall()
        return [(row[0], row[1]) for row in rows]

    def fuzzy_search(
        self,
        source: str,
        source_lang: str,
        target_lang: str,
        threshold: float = 75.0,
        max_results: int = 5,
        candidates: "Optional[List[Tuple[str, str]]]" = None,
    ) -> "List[FuzzyMatch]":
        """Search the TM for fuzzy matches against *source*.

        Parameters
        ----------
        candidates:
            Optional pre-loaded list of (source, translation) tuples.
            When provided, skips the ``all_sources()`` query (useful for
            caching across multiple calls in a single run).

        Returns matches sorted by score descending, filtered by threshold.
        """
        from .fuzzy import FuzzyMatch, FuzzyMatcher

        if candidates is None:
            candidates = self.all_sources(source_lang, target_lang)
        if not candidates:
            return []
        matcher = FuzzyMatcher(threshold=threshold, max_results=max_results)
        return matcher.find_matches(
            source, candidates, source_lang=source_lang, target_lang=target_lang
        )


def default_tm_path() -> Path:
    """Return a sensible per-user default path for the TM database."""
    return Path.home() / ".cache" / "salesforce-translation-handler" / DEFAULT_TM_FILENAME
