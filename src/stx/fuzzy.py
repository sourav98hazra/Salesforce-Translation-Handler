"""Fuzzy matching for translation memory.

Uses :mod:`rapidfuzz` to find similar source strings in the TM when
an exact match is not available.  This enables reuse of translations
for minor variants (typos, plurals, small edits) without hitting the
network translator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from rapidfuzz import fuzz, process


@dataclass
class FuzzyMatch:
    """A single fuzzy match result from the translation memory."""

    source: str
    translation: str
    score: float  # 0-100
    source_lang: str
    target_lang: str


class FuzzyMatcher:
    """Find approximate matches for a query string against a list of candidates.

    Parameters
    ----------
    threshold:
        Minimum score (0-100) for a match to be included.
    max_results:
        Maximum number of results to return.
    """

    def __init__(self, threshold: float = 75.0, max_results: int = 5) -> None:
        self.threshold = threshold
        self.max_results = max_results

    def find_matches(
        self,
        query: str,
        candidates: List[Tuple[str, str]],
        source_lang: str = "",
        target_lang: str = "",
    ) -> List[FuzzyMatch]:
        """Find the best fuzzy matches for *query* among *candidates*.

        Parameters
        ----------
        query:
            The source string to match against.
        candidates:
            A list of ``(source, translation)`` tuples to compare against.
        source_lang:
            Source language code (carried through to the result).
        target_lang:
            Target language code (carried through to the result).

        Returns
        -------
        A list of :class:`FuzzyMatch` sorted by score descending, limited
        to ``max_results`` entries that score at or above ``threshold``.
        """
        if not query or not candidates:
            return []

        # Build lookup: source -> translation (for duplicates, last wins)
        source_to_translation = {src: trans for src, trans in candidates}
        sources = list(source_to_translation.keys())

        if not sources:
            return []

        results = process.extract(
            query,
            sources,
            scorer=fuzz.WRatio,
            limit=self.max_results,
            score_cutoff=self.threshold,
        )

        matches = []
        for source_text, score, _index in results:
            matches.append(
                FuzzyMatch(
                    source=source_text,
                    translation=source_to_translation[source_text],
                    score=score,
                    source_lang=source_lang,
                    target_lang=target_lang,
                )
            )

        # Already sorted by score desc from rapidfuzz, but ensure it
        matches.sort(key=lambda m: m.score, reverse=True)
        return matches
