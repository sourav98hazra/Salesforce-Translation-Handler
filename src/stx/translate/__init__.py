"""Translation backends and helpers.

The default backend (:class:`GoogleFreeTranslator`) wraps
``deep_translator.GoogleTranslator`` and reproduces the behaviour of the
legacy ``translate_excel_fixed.py`` script -- token protection for
Salesforce placeholders and ALL-CAPS words, HTML preservation via
BeautifulSoup, and exponential-backoff retries.

The module is structured around a small :class:`Translator` protocol so
additional backends (DeepL, Azure, OpenAI, ...) can be slotted in later
without touching the GUI or CLI.
"""

from __future__ import annotations

from .base import Translator
from .google_free import GoogleFreeTranslator
from .protect import protect_tokens, restore_tokens
from .runner import (
    SheetSummary,
    StatusEntry,
    TranslationProgress,
    TranslationResult,
    translate_document,
)

__all__ = [
    "Translator",
    "GoogleFreeTranslator",
    "protect_tokens",
    "restore_tokens",
    "translate_document",
    "TranslationProgress",
    "TranslationResult",
    "SheetSummary",
    "StatusEntry",
]
