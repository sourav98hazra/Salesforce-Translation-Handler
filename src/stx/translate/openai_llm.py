"""OpenAI LLM-based translation backend.

Uses the chat-completions API (model defaults to ``gpt-4o-mini``).  The
backend prompts the model to:

* Return *only* the translation, no commentary.
* Preserve sentinel tokens, HTML tags, Salesforce IDs, placeholders.

Useful when the source contains terminology that machine translators
mis-translate (acronyms, idioms, brand voice).  Significantly slower
and more expensive than DeepL / Google -- recommended for review-grade
runs, not for the entire 36k-row export.
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

_DEFAULT_MODEL = "gpt-4o-mini"

_SYSTEM_PROMPT = """You translate strings from a Salesforce metadata export.

Rules (these are non-negotiable):
1. Reply with ONLY the translation, no quotes, no commentary, no preamble.
2. Preserve every sentinel token of the form __XXX_NN__ verbatim.
3. Preserve HTML tags, attributes (href, style), and self-closing tags.
4. Preserve Salesforce record IDs (15- or 18-character base-62 strings).
5. Preserve Apex MessageFormat tokens like {0}, {1}, {name}.
6. Preserve URLs and email addresses.
7. Keep the same overall punctuation and HTML structure as the source.
"""


@dataclass
class OpenAITranslator(Translator):
    """OpenAI chat-completions translator."""

    api_key: Optional[str] = None
    model: str = _DEFAULT_MODEL
    retries: int = 3
    base_delay: float = 2.0
    timeout: float = 30.0

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI backend requires an API key. Set the OPENAI_API_KEY "
                "environment variable, pass api_key= explicitly, or enter "
                "the key in Edit -> Settings -> Translation."
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
        # Local import so the package stays usable without the openai sdk.
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - guarded by extras
            raise RuntimeError(
                "The OpenAI backend requires the 'openai' package.  "
                "Install with: pip install openai"
            ) from exc

        client = OpenAI(api_key=self.api_key)

        user_prompt = (
            f"Source language: {source_lang}\n"
            f"Target language: {target_lang}\n"
            f"Source text:\n{text}"
        )

        for attempt in range(self.retries):
            try:
                response = client.chat.completions.create(
                    model=self.model,
                    timeout=self.timeout,
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.0,
                )
                content = response.choices[0].message.content or ""
                if content.strip():
                    return content.strip()
            except Exception as exc:  # noqa: BLE001
                LOGGER.debug(
                    "OpenAI attempt %d/%d failed: %s",
                    attempt + 1,
                    self.retries,
                    exc,
                )
            time.sleep(self.base_delay * (2 ** attempt))
        return None
