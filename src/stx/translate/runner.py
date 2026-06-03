"""Drive translation across an entire :class:`Document`.

The runner consumes a :class:`Document`, mutates it in place by filling
in missing translations, and yields progress callbacks suitable for both
CLI progress bars and Qt thread signals.

Three optional integrations layer onto the core loop:

* **Scope** (:class:`stx.scope.Scope`) -- decides whether each row is
  eligible for translation.  An out-of-scope row is left untouched.
* **Translation memory** (:class:`stx.memory.TranslationMemory`) --
  consulted *before* the translator backend; on a hit, the cached
  translation is used and the network call is skipped entirely.
* **Glossary** (:class:`stx.glossary.Glossary`) -- "do not translate"
  terms are wrapped in sentinels prior to translation; "force-translate
  as" rules are applied to the translator's output.

Speed-ups
---------

* **Per-run deduplication** -- two rows with the same source label are
  translated *once*; the second row reuses the first row's result.
  Salesforce metadata is full of repeated labels ("Name", "Created
  Date") so this alone often shrinks runtime by 30-60%.
* **Parallel translation** -- when ``workers > 1`` the unique source
  strings are translated concurrently via :class:`ThreadPoolExecutor`.
  Document order is preserved when reassembling the result.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from typing import Callable, Dict, List, Optional, Tuple

from ..checkpoint import CheckpointStore
from ..glossary import Glossary
from ..memory import TranslationMemory
from ..model import Document, Entry
from ..scope import Scope
from .base import Translator
from .protect import all_tokens_restored, restore_tokens
from .rate_limit import AdaptiveLimiter

LOGGER = logging.getLogger(__name__)

DEFAULT_WORKERS = 4
"""Sensible default concurrency.  Free tier translators rate-limit at
roughly 5-10 concurrent requests so we stay well below that ceiling."""


# ---------------------------------------------------------------------------
# Audit / progress data classes
# ---------------------------------------------------------------------------

@dataclass
class SheetSummary:
    """Per-sheet counts, mirrored into the audit workbook."""

    sheet_name: str
    total_rows: int = 0
    translated_rows: int = 0
    skipped_rows: int = 0
    cached_rows: int = 0  # how many came from the translation memory
    deduped_rows: int = 0  # how many came from in-run dedup

    def as_audit_row(self) -> dict:
        return {
            "Sheet Name": self.sheet_name,
            "Total Rows": self.total_rows,
            "Translated Rows": self.translated_rows,
            "Skipped Rows": self.skipped_rows,
            "TM Hits": self.cached_rows,
            "Dedup Hits": self.deduped_rows,
        }


@dataclass
class StatusEntry:
    """Per-row translation outcome for the audit log."""

    sheet_name: str
    row_index: int
    key: str
    label: str
    translation: str
    status: str

    def as_audit_row(self) -> dict:
        return {
            "Sheet Name": self.sheet_name,
            "Row Index": self.row_index,
            "Key": self.key,
            "Label": self.label,
            "Translation": self.translation,
            "Status": self.status,
        }


@dataclass
class TranslationProgress:
    """Progress event emitted while translating.

    Attributes
    ----------
    completed, total:
        Row counts for percent calculation.
    sheet, key, status:
        Identifying information for the row that just completed.
    source_text, translation_text:
        Actual source label and resulting translation -- enables a
        live "EN -> JA" display in the GUI / CLI.
    eta_seconds, rows_per_second:
        Throughput metrics computed from elapsed time.
    """

    completed: int
    total: int
    sheet: str
    key: str
    status: str
    source_text: str = ""
    translation_text: str = ""
    eta_seconds: Optional[float] = None
    rows_per_second: Optional[float] = None
    from_fuzzy: bool = False

    @property
    def percent(self) -> int:
        return int(self.completed * 100 / self.total) if self.total else 0


@dataclass
class TranslationResult:
    """Outcome of :func:`translate_document`."""

    document: Document
    summaries: List[SheetSummary] = field(default_factory=list)
    statuses: List[StatusEntry] = field(default_factory=list)
    translated_count: int = 0
    skipped_count: int = 0
    cached_count: int = 0   # from persistent translation memory
    deduped_count: int = 0  # from in-run dedup cache
    fuzzy_accepted_count: int = 0  # from fuzzy TM matching
    resumed_count: int = 0  # from checkpoint resume
    imported_reuse_count: int = 0  # from imported translations file
    infile_reuse_count: int = 0   # from in-file translation reuse (same label in same file)
    retranslated_count: int = 0  # rows that had existing translations and were retranslated
    failed_count: int = 0  # rows where _mark_failed was called (fallbacks)
    target_lang: str = ""
    elapsed_seconds: float = 0.0

    @property
    def cache_hit_rate(self) -> float:
        return self.cached_count / self.translated_count if self.translated_count else 0.0


@dataclass
class MultiTargetResult:
    """Output of :func:`translate_document_multi`."""

    by_target: dict[str, TranslationResult] = field(default_factory=dict)


ProgressCallback = Callable[[TranslationProgress], None]


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def translate_document(
    doc: Document,
    translator: Translator,
    *,
    source_lang: str = "en",
    target_lang: str = "ja",
    progress: Optional[ProgressCallback] = None,
    cancel: Optional[Callable[[], bool]] = None,
    scope: Optional[Scope] = None,
    memory: Optional[TranslationMemory] = None,
    glossary: Optional[Glossary] = None,
    checkpoint: Optional[CheckpointStore] = None,
    workers: int = DEFAULT_WORKERS,
    rate_limit_per_second: Optional[float] = 8.0,
    prevent_system_sleep: bool = True,
    fuzzy_threshold: Optional[float] = None,
    fuzzy_max_results: int = 5,
    fuzzy_auto_accept_threshold: float = 90.0,
    imported_translations: Optional[Dict[str, str]] = None,
    infile_translations: Optional[Dict[str, str]] = None,
    retranslate_existing: bool = False,
) -> TranslationResult:
    """Translate every untranslated entry in ``doc`` in place.

    Parameters
    ----------
    doc:
        Document to translate.  Modified in place.
    translator:
        Backend to use.
    source_lang, target_lang:
        Language codes passed verbatim to the translator backend.
    progress:
        Optional callback receiving :class:`TranslationProgress` events.
    cancel:
        Optional predicate; if it returns ``True`` between rows the run
        is aborted gracefully (already-translated rows are kept).
    scope:
        Optional :class:`Scope` filter -- out-of-scope rows are left
        untouched and recorded as ``Out of scope`` in the audit log.
    memory:
        Optional :class:`TranslationMemory`; consulted before the
        translator and updated with every successful translation.
    glossary:
        Optional :class:`Glossary` -- DNT terms are protected and
        forced-translation rules are applied post-translation.
    workers:
        Number of concurrent translation worker threads.  Defaults to
        :data:`DEFAULT_WORKERS`.  Set to ``1`` for strict serial
        execution (useful when a backend rate-limits aggressively).
    rate_limit_per_second:
        Initial token-bucket capacity for the adaptive rate limiter.
        ``None`` disables the limiter (still useful for paid backends
        with high quotas).  Defaults to 8 requests/second which is well
        within the free Google tier.
    prevent_system_sleep:
        If ``True`` (default), hold a cross-platform wake lock for the
        duration of the run so a long translation isn't interrupted by
        idle system sleep.  Has no effect when the laptop lid is
        closed -- closing the lid forces sleep on most systems.
    retranslate_existing:
        If ``True``, rows that already have a translation are
        retranslated instead of skipped.  Imported translations still
        take highest priority regardless of this flag.
    """
    started = time.monotonic()
    runner = _Runner(
        doc=doc,
        translator=translator,
        source_lang=source_lang,
        target_lang=target_lang,
        progress=progress,
        cancel=cancel,
        scope=scope,
        memory=memory,
        glossary=glossary,
        checkpoint=checkpoint,
        workers=max(1, int(workers)),
        rate_limit_per_second=rate_limit_per_second,
        fuzzy_threshold=fuzzy_threshold,
        fuzzy_max_results=fuzzy_max_results,
        fuzzy_auto_accept_threshold=fuzzy_auto_accept_threshold,
        imported_translations=imported_translations,
        infile_translations=infile_translations,
        retranslate_existing=retranslate_existing,
    )
    if prevent_system_sleep:
        from ..wakelock import prevent_sleep

        with prevent_sleep("Salesforce translation in progress"):
            result = runner.run()
    else:
        result = runner.run()
    result.elapsed_seconds = time.monotonic() - started
    return result


def translate_document_multi(
    doc: Document,
    translator: Translator,
    *,
    source_lang: str,
    target_langs: list[str],
    progress: Optional[Callable[[str, TranslationProgress], None]] = None,
    cancel: Optional[Callable[[], bool]] = None,
    scope: Optional[Scope] = None,
    memory: Optional[TranslationMemory] = None,
    glossary: Optional[Glossary] = None,
    workers: int = DEFAULT_WORKERS,
    rate_limit_per_second: Optional[float] = 8.0,
    fuzzy_threshold: Optional[float] = None,
    fuzzy_max_results: int = 5,
    fuzzy_auto_accept_threshold: float = 90.0,
    imported_translations: Optional[Dict[str, str]] = None,
    retranslate_existing: bool = False,
) -> MultiTargetResult:
    """Translate ``doc`` to multiple target languages in sequence.

    Each target language gets its own ``TranslationResult``, leaving the
    original document untouched.  The caller (CLI / GUI) is then
    responsible for writing each result to disk.
    """

    multi = MultiTargetResult()
    for target in target_langs:
        if cancel is not None and cancel():
            break

        # Each language operates on a copy of the source so existing
        # translations from previous runs don't leak across targets.
        per_lang_doc = Document(
            language=doc.language,
            language_code=target,
            stf_type=doc.stf_type,
            translation_type=doc.translation_type,
            entries=[Entry(key=e.key, label=e.label, translation="") for e in doc.entries],
        )

        def _wrap(event: TranslationProgress, target=target) -> None:
            if progress is not None:
                progress(target, event)

        result = translate_document(
            per_lang_doc,
            translator,
            source_lang=source_lang,
            target_lang=target,
            progress=_wrap,
            cancel=cancel,
            scope=scope,
            memory=memory,
            glossary=glossary,
            workers=workers,
            rate_limit_per_second=rate_limit_per_second,
            fuzzy_threshold=fuzzy_threshold,
            fuzzy_max_results=fuzzy_max_results,
            fuzzy_auto_accept_threshold=fuzzy_auto_accept_threshold,
            imported_translations=imported_translations,
            retranslate_existing=retranslate_existing,
        )
        multi.by_target[target] = result

    return multi


# ---------------------------------------------------------------------------
# Internal runner
# ---------------------------------------------------------------------------

class _Runner:
    """Encapsulates a single translation pass.

    Pulled out into a class because the per-run state (dedup cache,
    progress emitter, completed counter) needs to be visible to the
    worker callable without long parameter lists.
    """

    def __init__(
        self,
        *,
        doc: Document,
        translator: Translator,
        source_lang: str,
        target_lang: str,
        progress: Optional[ProgressCallback],
        cancel: Optional[Callable[[], bool]],
        scope: Optional[Scope],
        memory: Optional[TranslationMemory],
        glossary: Optional[Glossary],
        checkpoint: Optional[CheckpointStore] = None,
        workers: int,
        rate_limit_per_second: Optional[float] = None,
        fuzzy_threshold: Optional[float] = None,
        fuzzy_max_results: int = 5,
        fuzzy_auto_accept_threshold: float = 90.0,
        imported_translations: Optional[Dict[str, str]] = None,
        infile_translations: Optional[Dict[str, str]] = None,
        retranslate_existing: bool = False,
    ) -> None:
        self.doc = doc
        self.translator = translator
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.progress = progress
        self.cancel = cancel
        self.scope = scope
        self.memory = memory
        self.glossary = glossary
        self.checkpoint = checkpoint
        self.workers = workers
        self.fuzzy_threshold = fuzzy_threshold
        self.fuzzy_max_results = fuzzy_max_results
        self.fuzzy_auto_accept_threshold = fuzzy_auto_accept_threshold
        self.imported_translations = imported_translations or {}
        self.infile_translations = infile_translations or {}
        self.retranslate_existing = retranslate_existing
        self.limiter: Optional[AdaptiveLimiter] = (
            AdaptiveLimiter(max_capacity=rate_limit_per_second)
            if rate_limit_per_second and rate_limit_per_second > 0
            else None
        )

        # Checkpoint data: loaded once at init for O(1) lookups during classify.
        self._checkpoint_data: Dict[int, dict] = {}
        if self.checkpoint is not None and self.checkpoint.exists():
            self._checkpoint_data = self.checkpoint.load()

        # Run-time state
        self._summaries: Dict[str, SheetSummary] = {}
        self._statuses: List[Optional[StatusEntry]] = [None] * len(doc.entries)
        self._new_entries: List[Optional[Entry]] = [None] * len(doc.entries)
        self._translated = 0
        self._skipped = 0
        self._failed = 0
        self._cached = 0
        self._deduped = 0
        self._fuzzy_accepted = 0
        self._resumed = 0
        self._imported_reuse = 0
        self._infile_reuse = 0
        self._retranslated = 0
        self._completed_for_eta = 0
        self._started = time.monotonic()

        # In-run dedup cache: source -> translated.  Only populated for
        # rows that actually went through the translator (or TM) so we
        # can replay the result onto duplicate rows for free.
        self._dedup: Dict[str, str] = {}
        self._dedup_lock = threading.Lock()
        self._completion_lock = threading.Lock()

        # Cached fuzzy candidates (loaded once per run to avoid repeated
        # full-table scans of the TM on every row miss).
        self._fuzzy_candidates: Optional[List[Tuple[str, str]]] = None

        # Single-shot guard: the runner is one-use.  Attempting to call
        # ``run()`` twice on the same instance raises rather than corrupting
        # the previous result.
        self._run_started = False
        self._run_lock = threading.Lock()

    def run(self) -> TranslationResult:
        # Single-shot guard -- the runner is not reusable.  Caller bug,
        # not user bug, but failing loud is better than corrupt output.
        with self._run_lock:
            if self._run_started:
                raise RuntimeError(
                    "Runner.run() invoked twice on the same instance.  "
                    "Construct a fresh _Runner per pass."
                )
            self._run_started = True

        # First pass (serial): classify every row and queue the ones that
        # actually need translator work.  The rest are filled immediately.
        translation_jobs: List[int] = []  # indices that need translator work

        for index, entry in enumerate(self.doc.entries):
            decision = self._classify(index, entry)
            if decision == "translate":
                translation_jobs.append(index)

        # Second pass: execute translation jobs (with optional concurrency).
        if self.workers <= 1:
            self._run_serial(translation_jobs)
        else:
            self._run_parallel(translation_jobs)

        # ---- Gap-prevention sweep
        # If anything went wrong mid-run (cancellation, executor early-exit,
        # parallel-replay corner case), there could be ``None`` slots left
        # in ``_new_entries`` / ``_statuses``.  Fill them with a documented
        # fallback so the audit log and the document have *no gaps*.
        for index, entry in enumerate(self.doc.entries):
            if self._new_entries[index] is None:
                self._new_entries[index] = entry  # untouched
            if self._statuses[index] is None:
                sheet = entry.logical_sheet_name
                summary = self._summaries.setdefault(sheet, SheetSummary(sheet_name=sheet))
                summary.skipped_rows += 1
                self._skipped += 1
                self._statuses[index] = StatusEntry(
                    sheet_name=sheet,
                    row_index=index + 2,
                    key=entry.key,
                    label=entry.label,
                    translation=entry.translation,
                    status="Not processed (run aborted)",
                )

        # Validate invariants -- if these ever fire we have a real bug.
        assert all(e is not None for e in self._new_entries), "gap in entries"
        assert all(s is not None for s in self._statuses), "gap in statuses"
        assert len(self._new_entries) == len(self.doc.entries), "row count drift"

        self.doc.entries = [e for e in self._new_entries if e is not None]

        statuses = [s for s in self._statuses if s is not None]

        # Clear checkpoint on successful completion (no gaps, no cancel).
        cancelled = self.cancel is not None and self.cancel()
        if self.checkpoint is not None and not cancelled:
            self.checkpoint.clear()

        return TranslationResult(
            document=self.doc,
            summaries=list(self._summaries.values()),
            statuses=statuses,
            translated_count=self._translated,
            skipped_count=self._skipped,
            cached_count=self._cached,
            deduped_count=self._deduped,
            fuzzy_accepted_count=self._fuzzy_accepted,
            resumed_count=self._resumed,
            imported_reuse_count=self._imported_reuse,
            infile_reuse_count=self._infile_reuse,
            retranslated_count=self._retranslated,
            failed_count=self._failed,
            target_lang=self.target_lang,
        )

    # ------------------------------------------------------------------ classify

    def _classify(self, index: int, entry: Entry) -> str:
        """Decide what to do with a row.

        Returns ``"translate"`` if the row needs translator work, or
        ``"done"`` if it's been classified and the slot is filled.
        """
        sheet = entry.logical_sheet_name
        summary = self._summaries.setdefault(sheet, SheetSummary(sheet_name=sheet))
        summary.total_rows += 1

        if self.cancel is not None and self.cancel():
            self._fill(index, entry, sheet, "Cancelled", summary)
            self._skipped += 1
            return "done"

        if self.scope is not None and not self.scope.includes(entry):
            self._fill(index, entry, sheet, "Skipped (out of scope)", summary)
            summary.skipped_rows += 1
            self._skipped += 1
            return "done"

        # Checkpoint resume: if this index was previously translated, restore
        # from checkpoint data and skip re-translation entirely.
        if index in self._checkpoint_data:
            cp = self._checkpoint_data[index]
            translation = cp.get("translation", "")
            new_entry = Entry(key=entry.key, label=entry.label, translation=translation)
            self._new_entries[index] = new_entry
            cp_status = cp.get("status", "")
            if cp_status.startswith("Fallback to original"):
                status = f"Resumed from checkpoint ({cp_status})"
            else:
                status = "Resumed from checkpoint"
            self._statuses[index] = StatusEntry(
                sheet_name=sheet,
                row_index=index + 2,
                key=entry.key,
                label=entry.label,
                translation=translation,
                status=status,
            )
            summary.translated_rows += 1
            self._translated += 1
            self._resumed += 1
            self._emit_progress(index, entry.key, sheet, status, entry.label, translation)
            return "done"

        # Import bypass: if the imported translations dict has a match for
        # this row's label, let it through to _translate_one() regardless of
        # existing translation state.  This allows imported translations to
        # override already-translated rows even when retranslate_existing=False.
        if self.imported_translations and entry.label in self.imported_translations:
            return "translate"

        # In-file translation reuse: if the same label already has a translation
        # elsewhere in THIS file, and retranslate_existing is not requested, skip
        # the API and reuse that translation immediately.
        if (
            self.infile_translations
            and not self.retranslate_existing
            and not entry.translation.strip()   # only for untranslated rows
            and entry.label.strip() in self.infile_translations
        ):
            infile_value = self.infile_translations[entry.label.strip()]
            new_entry = Entry(
                key=entry.key,
                label=entry.label,
                translation=infile_value,
                approved=entry.approved,
            )
            self._new_entries[index] = new_entry
            status = "Reused from file"
            self._statuses[index] = StatusEntry(
                sheet_name=sheet,
                row_index=index + 2,
                key=entry.key,
                label=entry.label,
                translation=infile_value,
                status=status,
            )
            summary.cached_rows += 1   # count as cache hit (no API call)
            self._infile_reuse += 1
            self._translated += 1
            # Also populate the dedup cache so subsequent duplicates in the
            # same run also benefit.
            with self._dedup_lock:
                self._dedup.setdefault(entry.label, infile_value)
            self._emit_progress(index, entry.key, sheet, status, entry.label, infile_value)
            return "done"

        if not entry.label.strip():
            self._fill(index, entry, sheet, "Skipped (blank label)", summary)
            summary.skipped_rows += 1
            self._skipped += 1
            return "done"

        if entry.translation.strip():
            if self.retranslate_existing:
                # Row has an existing translation but user requested retranslation.
                # Let it proceed to _translate_one() where imported_translations
                # can still take priority.
                return "translate"
            self._fill(index, entry, sheet, "Skipped (already translated)", summary)
            summary.skipped_rows += 1
            self._skipped += 1
            return "done"

        return "translate"

    def _fill(
        self,
        index: int,
        entry: Entry,
        sheet: str,
        status: str,
        summary: SheetSummary,
    ) -> None:
        self._new_entries[index] = entry
        self._statuses[index] = StatusEntry(
            sheet_name=sheet,
            row_index=index + 2,
            key=entry.key,
            label=entry.label,
            translation=entry.translation,
            status=status,
        )
        # Emit a progress event for non-translated rows too -- the UI
        # progress bar otherwise stalls when the leading rows are skipped.
        self._emit_progress(index, entry.key, sheet, status, entry.label, entry.translation)

    # ------------------------------------------------------------------ serial / parallel

    def _run_serial(self, indices: List[int]) -> None:
        for index in indices:
            if self.cancel is not None and self.cancel():
                self._mark_cancelled(index)
                continue
            self._translate_one(index)

    def _run_parallel(self, indices: List[int]) -> None:
        # Group indices by their source label so we only dispatch each
        # unique source once (massive speedup on Salesforce metadata).
        source_to_indices: Dict[str, List[int]] = {}
        for index in indices:
            source_to_indices.setdefault(self.doc.entries[index].label, []).append(index)

        # Dispatch one job per unique source.  The first-arrived index for
        # each source becomes the "primary"; duplicates inherit the result
        # via the dedup cache.
        primary_indices = [idxs[0] for idxs in source_to_indices.values()]

        # Track which primaries finished so the duplicate-replay step
        # below knows whether the dedup cache is authoritative.
        completed_primaries: set[int] = set()

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {
                executor.submit(self._translate_one, idx): idx for idx in primary_indices
            }
            try:
                for future in as_completed(futures):
                    primary_idx = futures[future]
                    completed_primaries.add(primary_idx)
                    if self.cancel is not None and self.cancel():
                        # Stop scheduling more work; outstanding futures are
                        # cancelled below.
                        for pending in futures:
                            pending.cancel()
                        break
                    exc = future.exception()
                    if exc is not None:  # pragma: no cover - defensive
                        LOGGER.warning("Translation worker raised: %s", exc)
            finally:
                # Walk every primary slot to be sure it has a status -- a
                # cancelled future never executes its body.
                for idx in primary_indices:
                    if self._statuses[idx] is None:
                        self._mark_cancelled(idx)

        # Replay dedup hits onto duplicate indices.  Every dup must end up
        # with *some* status (translation, dedup hit, or fallback).
        for source, idxs in source_to_indices.items():
            if len(idxs) <= 1:
                continue
            translated = self._dedup.get(source)
            if translated is None:
                # Primary failed or was cancelled -> mark every duplicate
                # consistently.  We never leave a duplicate slot empty.
                for dup in idxs[1:]:
                    if self._statuses[dup] is None:
                        self._mark_failed(dup, "Fallback to original (primary unavailable)")
                continue
            for dup in idxs[1:]:
                if self._statuses[dup] is None:
                    self._fill_translated(dup, translated, "Translated (dedup)", deduped=True)

    # ------------------------------------------------------------------ single-row

    def _translate_one(self, index: int) -> None:
        entry = self.doc.entries[index]
        sheet = entry.logical_sheet_name
        summary = self._summaries[sheet]

        # ---- imported translations (highest priority)
        if self.imported_translations:
            imported = self.imported_translations.get(entry.label)
            if imported is not None:
                with self._dedup_lock:
                    self._dedup[entry.label] = imported
                self._fill_translated(
                    index, imported, "Translated (imported)", from_imported=True
                )
                return

        # ---- in-run dedup
        with self._dedup_lock:
            cached_dedup = self._dedup.get(entry.label)
        if cached_dedup is not None:
            self._fill_translated(index, cached_dedup, "Translated (dedup)", deduped=True)
            return

        # ---- translation memory
        if self.memory is not None:
            try:
                cached = self.memory.get(entry.label, self.source_lang, self.target_lang)
            except Exception:  # noqa: BLE001
                cached = None
            if cached is not None:
                final = self.glossary.apply_forced(cached) if self.glossary else cached
                with self._dedup_lock:
                    self._dedup[entry.label] = final
                self._fill_translated(index, final, "Translated (TM hit)", from_tm=True)
                return

        # ---- fuzzy TM matching
        if self.fuzzy_threshold is not None and self.memory is not None:
            try:
                if self._fuzzy_candidates is None:
                    self._fuzzy_candidates = self.memory.all_sources(
                        self.source_lang, self.target_lang
                    )
                fuzzy_matches = self.memory.fuzzy_search(
                    entry.label,
                    self.source_lang,
                    self.target_lang,
                    threshold=self.fuzzy_threshold,
                    max_results=self.fuzzy_max_results,
                    candidates=self._fuzzy_candidates,
                )
            except Exception:  # noqa: BLE001
                fuzzy_matches = []
            if fuzzy_matches and fuzzy_matches[0].score >= self.fuzzy_auto_accept_threshold:
                best = fuzzy_matches[0]
                final = self.glossary.apply_forced(best.translation) if self.glossary else best.translation
                with self._dedup_lock:
                    self._dedup[entry.label] = final
                self._fill_translated(
                    index, final, "Translated (fuzzy TM)", from_fuzzy=True
                )
                return
            elif fuzzy_matches:
                # Log suggestions that scored between threshold and auto-accept
                # so users can see near-matches even though the network
                # translator is still invoked.
                best = fuzzy_matches[0]
                LOGGER.info(
                    "Fuzzy suggestion for %r: %r (score=%.1f) -- below auto-accept (%.1f)",
                    entry.label,
                    best.source,
                    best.score,
                    self.fuzzy_auto_accept_threshold,
                )

        # ---- glossary DNT protection
        glossary_text = entry.label
        glossary_token_map: list = []
        if self.glossary is not None and self.glossary:
            glossary_text, glossary_token_map = self.glossary.protect(entry.label)

        # ---- network translation
        if self.limiter is not None:
            self.limiter.acquire()

        try:
            translated = self.translator.translate(glossary_text, self.source_lang, self.target_lang)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Translation failed for %s: %s", entry.key, exc)
            if self.limiter is not None:
                self.limiter.report_failure()
            self._mark_failed(index, f"Fallback to original ({exc})")
            return

        if not translated or not translated.strip():
            if self.limiter is not None:
                self.limiter.report_failure()
            self._mark_failed(index, "Fallback to original (empty result)")
            return

        if self.limiter is not None:
            self.limiter.report_success()

        # Restore glossary sentinels and apply forced rules.
        if glossary_token_map:
            restored = restore_tokens(translated, glossary_token_map)
            if all_tokens_restored(restored, glossary_token_map):
                translated = restored
            else:
                self._mark_failed(index, "Fallback to original (glossary token lost)")
                return
        if self.glossary is not None:
            translated = self.glossary.apply_forced(translated)

        # If API returns the same text as the source, it's a valid identity
        # translation (e.g. "URL" stays "URL", numbers stay unchanged).
        # This is NOT a failure — count it as a successful translation.

        # Persist to TM (under the *original* source).
        if self.memory is not None:
            try:
                self.memory.put(entry.label, self.source_lang, self.target_lang, translated)
            except Exception:  # noqa: BLE001
                LOGGER.debug("Failed to write TM entry for %s", entry.key, exc_info=True)

        with self._dedup_lock:
            self._dedup[entry.label] = translated

        self._fill_translated(index, translated, "Translated")

    # ------------------------------------------------------------------ result helpers

    def _fill_translated(
        self,
        index: int,
        translation: str,
        status: str,
        *,
        from_tm: bool = False,
        deduped: bool = False,
        from_fuzzy: bool = False,
        from_imported: bool = False,
    ) -> None:
        entry = self.doc.entries[index]
        new = Entry(key=entry.key, label=entry.label, translation=translation)
        sheet = entry.logical_sheet_name
        summary = self._summaries[sheet]
        with self._completion_lock:
            self._new_entries[index] = new
            self._statuses[index] = StatusEntry(
                sheet_name=sheet,
                row_index=index + 2,
                key=entry.key,
                label=entry.label,
                translation=translation,
                status=status,
            )
            summary.translated_rows += 1
            self._translated += 1
            if from_tm:
                summary.cached_rows += 1
                self._cached += 1
            if deduped:
                summary.deduped_rows += 1
                self._deduped += 1
            if from_fuzzy:
                self._fuzzy_accepted += 1
            if from_imported:
                self._imported_reuse += 1
            # Track retranslated rows: the entry originally had a non-empty
            # translation and retranslate_existing mode caused it to be
            # re-translated (or served from TM/dedup/network).  Imported
            # translations are excluded because applying a known translation
            # from a file is not "retranslating".
            if self.retranslate_existing and entry.translation.strip() and not from_imported:
                self._retranslated += 1
        # Persist to checkpoint after filling the slot.
        if self.checkpoint is not None:
            try:
                self.checkpoint.save_progress(index, entry.key, translation, status)
            except Exception:  # noqa: BLE001
                LOGGER.debug("Checkpoint save failed for index %d", index, exc_info=True)
        self._emit_progress(
            index, entry.key, sheet, status, entry.label, translation, from_fuzzy=from_fuzzy
        )

    def _mark_failed(self, index: int, status: str) -> None:
        entry = self.doc.entries[index]
        sheet = entry.logical_sheet_name
        summary = self._summaries.setdefault(sheet, SheetSummary(sheet_name=sheet))
        # "Fallback to original" means the API couldn't translate — use the
        # source label as the translation so the row isn't left blank.
        fallback_translation = entry.label if entry.label.strip() else entry.translation
        new_entry = Entry(key=entry.key, label=entry.label, translation=fallback_translation)
        with self._completion_lock:
            self._new_entries[index] = new_entry
            self._statuses[index] = StatusEntry(
                sheet_name=sheet,
                row_index=index + 2,
                key=entry.key,
                label=entry.label,
                translation=fallback_translation,
                status=status,
            )
            self._failed += 1
        # Checkpoint permanent failures so they are not retried on resume.
        # Transient errors (network timeouts, rate limits) are left un-checkpointed
        # so they get a fresh attempt on the next run.
        if self.checkpoint is not None and self._is_permanent_failure(status):
            try:
                self.checkpoint.save_progress(index, entry.key, entry.translation, status)
            except Exception:  # noqa: BLE001
                LOGGER.debug("Checkpoint save failed for failed index %d", index, exc_info=True)
        self._emit_progress(index, entry.key, sheet, status, entry.label, entry.translation)

    @staticmethod
    def _is_permanent_failure(status: str) -> bool:
        """Return True if the failure status represents a permanent condition.

        Permanent failures are those where retrying will produce the same
        outcome (e.g., the translator returned the source text verbatim,
        or a glossary token was irrecoverably lost).  Transient errors
        (network issues, rate limits) should be retried on resume.
        """
        permanent_indicators = (
            "no change",
            "glossary token lost",
        )
        status_lower = status.lower()
        return any(indicator in status_lower for indicator in permanent_indicators)

    def _mark_cancelled(self, index: int) -> None:
        entry = self.doc.entries[index]
        sheet = entry.logical_sheet_name
        summary = self._summaries.setdefault(sheet, SheetSummary(sheet_name=sheet))
        with self._completion_lock:
            self._new_entries[index] = entry
            self._statuses[index] = StatusEntry(
                sheet_name=sheet,
                row_index=index + 2,
                key=entry.key,
                label=entry.label,
                translation=entry.translation,
                status="Cancelled",
            )
            summary.skipped_rows += 1
            self._skipped += 1
        self._emit_progress(index, entry.key, sheet, "Cancelled", entry.label, entry.translation)

    # ------------------------------------------------------------------ progress

    def _emit_progress(
        self,
        index: int,
        key: str,
        sheet: str,
        status: str,
        source_text: str,
        translation_text: str,
        from_fuzzy: bool = False,
    ) -> None:
        if self.progress is None:
            return

        with self._completion_lock:
            self._completed_for_eta += 1
            completed = self._completed_for_eta

        total = len(self.doc.entries)
        elapsed = time.monotonic() - self._started
        rate = completed / elapsed if elapsed > 0 else None
        eta = (total - completed) / rate if rate else None

        try:
            self.progress(
                TranslationProgress(
                    completed=completed,
                    total=total,
                    sheet=sheet,
                    key=key,
                    status=status,
                    source_text=source_text,
                    translation_text=translation_text,
                    eta_seconds=eta,
                    rows_per_second=rate,
                    from_fuzzy=from_fuzzy,
                )
            )
        except Exception:  # noqa: BLE001
            LOGGER.debug("Progress callback raised; ignoring", exc_info=True)


# Re-export for convenience.
__all__ = [
    "translate_document",
    "translate_document_multi",
    "TranslationProgress",
    "TranslationResult",
    "MultiTargetResult",
    "SheetSummary",
    "StatusEntry",
    "DEFAULT_WORKERS",
    "asdict",
]
