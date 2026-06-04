"""DeepL translator backend.

Wraps :class:`deep_translator.DeeplTranslator` with the same retry +
token-protection behaviour as the Google backend.  Requires a DeepL API
key (free or paid tier; the free tier suffices for most teams) supplied
via the ``api_key`` argument or the ``DEEPL_API_KEY`` environment
variable.

DeepL is significantly higher-quality than Google free for European
languages and Japanese, so this backend is the recommended default for
production runs once a key is available.
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
class DeepLTranslator(Translator):
    """DeepL backend.  Falls back to source on transient failure."""

    api_key: Optional[str] = None
    use_free_api: bool = True
    retries: int = 3
    base_delay: float = 1.0

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.environ.get("DEEPL_API_KEY")
        if not self.api_key:
            raise ValueError(
                "DeepL backend requires an API key. Set the DEEPL_API_KEY "
                "environment variable, pass api_key= explicitly, or enter "
                "the key in Edit -> Settings -> Translation."
            )

    # ------------------------------------------------------------------ API

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        if not text or not text.strip() or text.strip().lower() in {"nan", "none"}:
            return text

        safe, token_map = protect_tokens(text)
        if not _has_translatable_content(safe):
            return text

        translated = self._call_with_retries(safe, source_lang, target_lang)
        if translated is None:
            return text

        translated = restore_tokens(translated, token_map)
        if not all_tokens_restored(translated, token_map):
            return text

        if translated.strip().lower() == text.strip().lower():
            return text
        return translated

    # ------------------------------------------------------------------ network

    def _call_with_retries(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
    ) -> Optional[str]:
        from deep_translator import DeeplTranslator

        for attempt in range(self.retries):
            try:
                result = DeeplTranslator(
                    api_key=self.api_key,
                    source=source_lang,
                    target=target_lang,
                    use_free_api=self.use_free_api,
                ).translate(text)
                if result and result.strip():
                    return result
            except Exception as exc:  # noqa: BLE001
                LOGGER.debug(
                    "DeepL attempt %d/%d failed: %s",
                    attempt + 1,
                    self.retries,
                    exc,
                )
            time.sleep(self.base_delay * (2 ** attempt))
        return None


def _has_translatable_content(text: str) -> bool:
    import re

    stripped = re.sub(r"__[A-Z]+_\d+__", "", text)
    return bool(stripped.strip())
