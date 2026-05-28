"""Microsoft Azure Translator backend.

Wraps :class:`deep_translator.MicrosoftTranslator`.  Requires an Azure
subscription key (Cognitive Services -> Translator) plus optionally a
region (defaults to the global endpoint when omitted).

Configuration order:

1. Explicit ``api_key`` / ``region`` arguments to the constructor.
2. ``AZURE_TRANSLATOR_KEY`` and ``AZURE_TRANSLATOR_REGION`` environment
   variables.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

from .base import Translator
from .protect import all_tokens_restored, protect_tokens, restore_tokens

LOGGER = logging.getLogger(__name__)


@dataclass
class AzureTranslator(Translator):
    """Azure Cognitive Services Translator backend."""

    api_key: Optional[str] = None
    region: Optional[str] = None
    retries: int = 3
    base_delay: float = 1.0

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.environ.get("AZURE_TRANSLATOR_KEY")
        self.region = self.region or os.environ.get("AZURE_TRANSLATOR_REGION")
        if not self.api_key:
            raise ValueError(
                "Azure backend requires an API key.  Set AZURE_TRANSLATOR_KEY "
                "or pass api_key= explicitly."
            )

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        if not text or not text.strip():
            return text

        safe, token_map = protect_tokens(text)
        translated = self._call_with_retries(safe, source_lang, target_lang)
        if translated is None:
            return text

        translated = restore_tokens(translated, token_map)
        if not all_tokens_restored(translated, token_map):
            return text

        if translated.strip().lower() == text.strip().lower():
            return text
        return translated

    def _call_with_retries(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
    ) -> Optional[str]:
        from deep_translator import MicrosoftTranslator

        kwargs = {"api_key": self.api_key, "source": source_lang, "target": target_lang}
        if self.region:
            kwargs["region"] = self.region

        for attempt in range(self.retries):
            try:
                result = MicrosoftTranslator(**kwargs).translate(text)
                if result and result.strip():
                    return result
            except Exception as exc:  # noqa: BLE001
                LOGGER.debug(
                    "Azure attempt %d/%d failed: %s",
                    attempt + 1,
                    self.retries,
                    exc,
                )
            time.sleep(self.base_delay * (2 ** attempt))
        return None
