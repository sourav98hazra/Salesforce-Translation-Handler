"""Translation backends and helpers.

The default backend (:class:`GoogleFreeTranslator`) wraps
``deep_translator.GoogleTranslator`` and reproduces the behaviour of the
legacy ``translate_excel_fixed.py`` script -- token protection for
Salesforce placeholders and ALL-CAPS words, HTML preservation via
BeautifulSoup, and exponential-backoff retries.

Additional backends -- :class:`DeepLTranslator`,
:class:`AzureTranslator`, and :class:`OpenAITranslator` -- are
available via :func:`make_backend` for runs requiring higher quality or
enterprise-grade quotas.

The module is structured around a small :class:`Translator` protocol so
new backends can be slotted in without touching the GUI or CLI.
"""

from __future__ import annotations

from .base import Translator
from .factory import BackendInfo, list_backends, make_backend, register
from .google_free import GoogleFreeTranslator
from .protect import all_tokens_restored, protect_tokens, restore_tokens
from .runner import (
    MultiTargetResult,
    SheetSummary,
    StatusEntry,
    TranslationProgress,
    TranslationResult,
    translate_document,
    translate_document_multi,
)

__all__ = [
    "Translator",
    "GoogleFreeTranslator",
    "BackendInfo",
    "list_backends",
    "make_backend",
    "register",
    "protect_tokens",
    "restore_tokens",
    "all_tokens_restored",
    "translate_document",
    "translate_document_multi",
    "TranslationProgress",
    "TranslationResult",
    "MultiTargetResult",
    "SheetSummary",
    "StatusEntry",
]
