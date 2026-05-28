"""Salesforce language name <-> code mapping.

This is a curated subset matching the legacy ``ExcelToSTFV2.ps1`` map,
extended with the most commonly encountered Salesforce locales.  Codes
follow the ``xx`` / ``xx_YY`` convention used by Translation Workbench.
"""

from __future__ import annotations

# Display name -> Salesforce code.
LANGUAGE_NAME_TO_CODE: dict[str, str] = {
    "Arabic": "ar",
    "Bulgarian": "bg",
    "Chinese (Simplified)": "zh_CN",
    "Chinese (Traditional)": "zh_TW",
    "Croatian": "hr",
    "Czech": "cs",
    "Danish": "da",
    "Dutch": "nl",
    "English": "en_US",
    "English (UK)": "en_GB",
    "Finnish": "fi",
    "French": "fr",
    "French (Canadian)": "fr_CA",
    "German": "de",
    "Greek": "el",
    "Hebrew": "iw",
    "Hindi": "hi",
    "Hungarian": "hu",
    "Indonesian": "in",
    "Italian": "it",
    "Japanese": "ja",
    "Korean": "ko",
    "Norwegian": "no",
    "Polish": "pl",
    "Portuguese (Brazilian)": "pt_BR",
    "Portuguese (European)": "pt_PT",
    "Romanian": "ro",
    "Russian": "ru",
    "Slovak": "sk",
    "Slovenian": "sl",
    "Spanish": "es",
    "Spanish (Mexican)": "es_MX",
    "Swedish": "sv",
    "Thai": "th",
    "Turkish": "tr",
    "Ukrainian": "uk",
    "Vietnamese": "vi",
}

# Reverse mapping built once at import time.
CODE_TO_LANGUAGE_NAME: dict[str, str] = {
    code: name for name, code in LANGUAGE_NAME_TO_CODE.items()
}

# Salesforce uses some non-standard codes (e.g. "iw" for Hebrew, "in" for
# Indonesian).  When invoking Google Translate we need to translate these
# to the underlying ISO codes.
SALESFORCE_TO_GOOGLE_CODE: dict[str, str] = {
    "iw": "he",
    "in": "id",
    "no": "no",
    "zh_CN": "zh-CN",
    "zh_TW": "zh-TW",
    "pt_BR": "pt",
    "pt_PT": "pt",
    "fr_CA": "fr",
    "es_MX": "es",
    "en_US": "en",
    "en_GB": "en",
}


def code_for_language(name: str) -> str | None:
    """Return the Salesforce code for ``name`` (case-insensitive), or ``None``."""

    if not name:
        return None
    needle = name.strip().lower()
    for display, code in LANGUAGE_NAME_TO_CODE.items():
        if display.lower() == needle:
            return code
    return None


def language_for_code(code: str) -> str | None:
    """Return the human-readable name for ``code``, or ``None``."""

    if not code:
        return None
    return CODE_TO_LANGUAGE_NAME.get(code.strip())


def to_google_code(salesforce_code: str) -> str:
    """Translate a Salesforce language code into the code Google Translate expects."""

    if not salesforce_code:
        return salesforce_code
    return SALESFORCE_TO_GOOGLE_CODE.get(salesforce_code, salesforce_code.split("_", 1)[0])


def supported_language_names() -> list[str]:
    """Return supported display names, sorted for UI presentation."""

    return sorted(LANGUAGE_NAME_TO_CODE)
