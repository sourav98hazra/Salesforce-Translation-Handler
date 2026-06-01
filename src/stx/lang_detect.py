"""Auto-detect source language from document labels.

Uses the ``langdetect`` library to inspect source strings and estimate
the source language.  Maps ISO 639-1 codes to Salesforce language codes.
"""

from __future__ import annotations

import random
from collections import Counter
from typing import List, Optional, Tuple

from .languages import CODE_TO_LANGUAGE_NAME, LANGUAGE_NAME_TO_CODE

# ISO 639-1 -> Salesforce code mapping.
# langdetect returns ISO 639-1 two-letter codes; Salesforce uses a mix of
# two-letter and regional codes.  We map to the most common Salesforce variant.
_ISO_TO_SALESFORCE: dict[str, str] = {
    "ar": "ar",
    "bg": "bg",
    "zh-cn": "zh_CN",
    "zh-tw": "zh_TW",
    "hr": "hr",
    "cs": "cs",
    "da": "da",
    "nl": "nl",
    "en": "en_US",
    "fi": "fi",
    "fr": "fr",
    "de": "de",
    "el": "el",
    "he": "iw",
    "hi": "hi",
    "hu": "hu",
    "id": "in",
    "it": "it",
    "ja": "ja",
    "ko": "ko",
    "no": "no",
    "pl": "pl",
    "pt": "pt_BR",
    "ro": "ro",
    "ru": "ru",
    "sk": "sk",
    "sl": "sl",
    "es": "es",
    "sv": "sv",
    "th": "th",
    "tr": "tr",
    "uk": "uk",
    "vi": "vi",
}


def detect_source_language(
    texts: List[str], top_n: int = 3
) -> List[Tuple[str, float]]:
    """Detect the most likely source language from a list of text samples.

    Parameters
    ----------
    texts:
        Source strings to analyse (e.g. the label column of a document).
    top_n:
        Maximum number of language candidates to return.

    Returns
    -------
    A list of ``(iso_code, confidence)`` tuples sorted by confidence
    (highest first).  Confidence is a float between 0.0 and 1.0.
    Returns an empty list if detection fails or langdetect is not installed.
    """
    try:
        from langdetect import detect_langs
        from langdetect import DetectorFactory
    except ImportError:
        return []

    # Filter to non-empty strings
    candidates = [t.strip() for t in texts if t and t.strip()]
    if not candidates:
        return []

    # Sample up to 50 strings for efficiency and reproducibility
    DetectorFactory.seed = 42
    if len(candidates) > 50:
        rng = random.Random(42)
        candidates = rng.sample(candidates, 50)

    # Run detection on each string and aggregate
    lang_scores: Counter[str] = Counter()
    total_weight = 0.0

    for text in candidates:
        try:
            results = detect_langs(text)
            for result in results:
                lang_scores[result.lang] += result.prob
                total_weight += result.prob
        except Exception:  # noqa: BLE001
            continue

    if not lang_scores or total_weight == 0:
        return []

    # Normalize to 0..1
    normalized: list[tuple[str, float]] = [
        (lang, score / total_weight)
        for lang, score in lang_scores.most_common(top_n)
    ]

    return normalized


# Minimum confidence required to accept an auto-detection result.
# Below this threshold callers should fall back to the default language.
CONFIDENCE_THRESHOLD = 0.60


def map_detected_to_salesforce(detected_code: str) -> Optional[str]:
    """Map an ISO 639-1 code from langdetect to the Salesforce language code.

    Parameters
    ----------
    detected_code:
        The language code returned by langdetect (e.g. ``"en"``, ``"ja"``).

    Returns
    -------
    The corresponding Salesforce code (e.g. ``"en_US"``, ``"ja"``), or
    ``None`` if no mapping exists.
    """
    if not detected_code:
        return None
    normalized = detected_code.strip().lower()
    # Direct lookup in our mapping table
    sf_code = _ISO_TO_SALESFORCE.get(normalized)
    if sf_code is not None:
        return sf_code
    # If the code is already a valid Salesforce code, return it as-is
    if normalized in CODE_TO_LANGUAGE_NAME:
        return normalized
    return None
