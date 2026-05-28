"""Translator protocol that every backend must implement."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Translator(Protocol):
    """Translate a single text fragment from ``source_lang`` to ``target_lang``.

    Implementations are expected to be thread-safe enough to be invoked
    sequentially from a worker thread.  Network and rate-limit handling
    (retries, backoff) belongs inside the implementation.
    """

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        ...
