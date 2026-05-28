"""Google Translate (free tier) backend via ``deep_translator``.

Behaviour highlights:

* **Token protection** -- every fragment in :mod:`stx.translate.protect`
  (URLs, emails, Salesforce IDs, placeholders, CAPS acronyms) is replaced
  with an opaque sentinel before the translator is invoked, then
  restored afterwards.
* **Rich text / HTML** -- when the input looks like HTML, only text
  nodes are sent to the translator.  Tags, attributes (including
  ``href`` / ``src`` / inline ``style``), and HTML entities round-trip
  unchanged.
* **Resilience** -- transient errors are retried with exponential
  backoff and we fall back to the original string if the translator
  persists in returning empty / invalid output.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

from .base import Translator
from .protect import all_tokens_restored, protect_tokens, restore_tokens

LOGGER = logging.getLogger(__name__)

# Google Translate's free endpoint accepts up to ~5000 characters per call.
# We stay well below that to leave headroom for sentinel inflation and to
# avoid silent server-side truncation.
_MAX_CHARS_PER_CALL = 4500

# ``<word>`` or ``<word ...>`` or ``<word/>`` -- a much tighter check than
# ``"<" in text and ">" in text`` so we don't trigger HTML mode for plain
# text that happens to contain a less-than sign.
_HTML_TAG_RE = re.compile(r"<[A-Za-z][^>]*>")
# HTML entities that indicate the input is rich text even if no full tag
# is present (rare but seen with snippets like ``A &amp; B``).
_HTML_ENTITY_RE = re.compile(r"&[#A-Za-z0-9]+;")


@dataclass
class GoogleFreeTranslator(Translator):
    """Free-tier Google translator.

    Parameters
    ----------
    retries:
        Number of attempts before falling back to the original text.
    base_delay:
        Initial backoff (seconds), doubled on each retry.
    preserve_html:
        Walk the DOM via BeautifulSoup and translate only text nodes.
        Tags and attributes are left untouched.
    """

    retries: int = 3
    base_delay: float = 1.0
    preserve_html: bool = True

    # ------------------------------------------------------------------ API

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        if text is None:
            return text
        stripped = text.strip()
        if not stripped or stripped.lower() in {"nan", "none"}:
            return text

        if self.preserve_html and self._looks_like_html(text):
            return self._translate_html(text, source_lang, target_lang)
        return self._translate_plain(text, source_lang, target_lang)

    # ------------------------------------------------------------------ plain

    def _translate_plain(self, text: str, source_lang: str, target_lang: str) -> str:
        # Empty / whitespace-only nodes contribute no information; preserving
        # them verbatim avoids "translating" pure formatting whitespace.
        if not text.strip():
            return text

        safe, token_map = protect_tokens(text)

        # If the entire text reduced to nothing but tokens, skip the network
        # round-trip -- there's nothing to translate.
        if not _has_translatable_content(safe):
            return text

        # Long labels (rich-text help, etc.) are split into sentence-sized
        # chunks before invoking the translator, then re-joined.  This avoids
        # silent server-side truncation on the free Google endpoint.
        if len(safe) > _MAX_CHARS_PER_CALL:
            translated = self._translate_in_chunks(safe, source_lang, target_lang)
        else:
            translated = self._call_with_retries(safe, source_lang, target_lang)

        if translated is None:
            return text

        translated = restore_tokens(translated, token_map)

        # Integrity check: if the translator dropped a placeholder, ID, URL,
        # or escape sequence, fall back to the source rather than shipping
        # corrupt data.
        if not all_tokens_restored(translated, token_map):
            LOGGER.debug("Token loss detected; falling back to source for %r", text[:40])
            return text

        # If the translator returned the same text (case-insensitive), keep
        # the original to preserve casing nuances (e.g. brand names).
        if translated.strip().lower() == text.strip().lower():
            return text
        return translated

    def _translate_in_chunks(self, text: str, source_lang: str, target_lang: str) -> Optional[str]:
        """Split ``text`` on sentence/whitespace boundaries and translate each piece.

        We never split inside a sentinel (sentinels contain no whitespace),
        so token protection remains intact across chunk boundaries.
        """

        chunks = _split_for_translation(text, _MAX_CHARS_PER_CALL)
        translated_pieces: list[str] = []
        for chunk in chunks:
            piece = self._call_with_retries(chunk, source_lang, target_lang)
            if piece is None:
                return None
            translated_pieces.append(piece)
        return " ".join(translated_pieces)

    # ------------------------------------------------------------------ html

    def _translate_html(self, text: str, source_lang: str, target_lang: str) -> str:
        # BeautifulSoup is imported lazily so users without rich-text content
        # don't pay the import cost.
        from bs4 import BeautifulSoup, NavigableString
        from bs4.element import Comment

        # ``html.parser`` is forgiving and (importantly) does NOT mangle
        # standalone ``&`` / ``<`` characters that already appear escaped.
        soup = BeautifulSoup(f"<stxroot>{text}</stxroot>", "html.parser")

        for node in list(soup.descendants):
            if isinstance(node, Comment):
                # Comments are non-visible -- never translate.
                continue
            if not isinstance(node, NavigableString):
                continue
            if node.parent is None:
                continue

            # Skip text nodes inside ``<script>`` / ``<style>`` -- those are
            # code, not user-visible content.
            parent_name = (node.parent.name or "").lower()
            if parent_name in {"script", "style"}:
                continue

            original = str(node)
            if not original.strip():
                continue

            translated = self._translate_plain(original, source_lang, target_lang)
            if translated != original:
                node.replace_with(translated)

        # Strip our synthetic root wrapper -- ``decode_contents`` preserves
        # entities and self-closing tags as written.
        root = soup.find("stxroot")
        if root is None:
            return str(soup)
        return root.decode_contents()

    # ------------------------------------------------------------------ network

    def _call_with_retries(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
    ) -> Optional[str]:
        # Imported lazily so the package stays importable in environments
        # where deep_translator isn't installed.  Callers only see the
        # ImportError when they actually attempt to translate.
        from deep_translator import GoogleTranslator

        for attempt in range(self.retries):
            try:
                result = GoogleTranslator(source=source_lang, target=target_lang).translate(text)
                if result and result.strip():
                    return result
            except Exception as exc:  # noqa: BLE001 -- intentional swallow + retry
                LOGGER.debug(
                    "Translate attempt %d/%d failed: %s",
                    attempt + 1,
                    self.retries,
                    exc,
                )
            time.sleep(self.base_delay * (2 ** attempt))
        return None

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _looks_like_html(text: str) -> bool:
        return bool(_HTML_TAG_RE.search(text) or _HTML_ENTITY_RE.search(text))


def _has_translatable_content(text: str) -> bool:
    """Return True if ``text`` contains anything other than sentinel tokens."""

    stripped = re.sub(r"__[A-Z]+_\d+__", "", text)
    return bool(stripped.strip())


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?\u3002\uff01\uff1f])\s+")


def _split_for_translation(text: str, max_chars: int) -> list[str]:
    """Split ``text`` into chunks no larger than ``max_chars`` characters.

    First splits on sentence terminators (``.``, ``!``, ``?`` and their
    full-width CJK equivalents); falls back to whitespace if a single
    "sentence" still exceeds the limit; falls back to hard-cut as a last
    resort.
    """

    if len(text) <= max_chars:
        return [text]

    sentences = _SENTENCE_SPLIT_RE.split(text) or [text]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if not sentence:
            continue
        # Single sentence exceeds the budget -> recursively split on whitespace.
        if len(sentence) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_on_whitespace(sentence, max_chars))
            continue

        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _split_on_whitespace(text: str, max_chars: int) -> list[str]:
    parts: list[str] = []
    while len(text) > max_chars:
        cut = text.rfind(" ", 0, max_chars)
        if cut <= 0:
            cut = max_chars  # hard cut, no whitespace available
        parts.append(text[:cut].strip())
        text = text[cut:].lstrip()
    if text:
        parts.append(text)
    return parts
