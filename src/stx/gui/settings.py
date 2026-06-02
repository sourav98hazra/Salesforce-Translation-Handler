"""Persistent settings via :class:`QSettings`.

A thin wrapper that the rest of the GUI uses for reading / writing
preferences such as the last-used target language, default output
folder, theme, recent files, and translator backend choice.

Storage location is platform-default:

* macOS: ``~/Library/Preferences/com.salesforce-translation-handler.plist``
* Windows: ``HKEY_CURRENT_USER\\Software\\SalesforceTranslationHandler``
* Linux: ``~/.config/SalesforceTranslationHandler/SalesforceTranslationHandler.conf``
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QSettings

ORG = "SalesforceTranslationHandler"
APP = "SalesforceTranslationHandler"

_MAX_RECENT = 10


@dataclass
class SettingsKeys:
    """Centralised key names so typos can't drift between callers."""

    target_language: str = "translation/target_language"
    target_language_code: str = "translation/target_language_code"
    source_language_code: str = "translation/source_language_code"
    backend: str = "translation/backend"
    workers: str = "translation/workers"
    output_dir: str = "io/output_dir"
    recent_files: str = "io/recent_files"
    glossary_path: str = "io/glossary_path"
    scope_path: str = "io/scope_path"
    memory_path: str = "io/memory_path"
    theme: str = "ui/theme"
    window_geometry: str = "ui/window_geometry"
    window_state: str = "ui/window_state"
    fuzzy_threshold: str = "translation/fuzzy_threshold"
    fuzzy_max_results: str = "translation/fuzzy_max_results"
    fuzzy_auto_accept: str = "translation/fuzzy_auto_accept"
    import_translations_path: str = "io/import_translations_path"
    import_translations_enabled: str = "io/import_translations_enabled"
    session_enabled: str = "session/enabled"
    # Translation option toggles (Translation menu)
    use_infile_translations: str = "translation/use_infile_translations"
    use_tm_cache: str = "translation/use_tm_cache"
    use_fuzzy_matching: str = "translation/use_fuzzy_matching"
    use_imported_translations: str = "translation/use_imported_translations"
    retranslate_existing: str = "translation/retranslate_existing"
    preflight_skip: str = "translation/preflight_skip"


KEYS = SettingsKeys()


def settings() -> QSettings:
    """Return a fresh :class:`QSettings` instance bound to our org/app names."""
    return QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, ORG, APP)


# ---------------------------------------------------------------------------
# Convenience getters / setters
# ---------------------------------------------------------------------------

def get_str(key: str, default: str = "") -> str:
    val = settings().value(key, default)
    return str(val) if val is not None else default


def set_str(key: str, value: str) -> None:
    settings().setValue(key, value)


def get_int(key: str, default: int = 0) -> int:
    val = settings().value(key, default)
    try:
        return int(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def set_int(key: str, value: int) -> None:
    settings().setValue(key, int(value))


def get_recent_files() -> List[str]:
    raw = settings().value(KEYS.recent_files, [])
    if isinstance(raw, str):
        return [raw] if raw else []
    if isinstance(raw, (list, tuple)):
        return [str(p) for p in raw if p]
    return []


def add_recent_file(path: str | Path) -> None:
    path = str(Path(path).resolve())
    current = get_recent_files()
    # Move-to-front semantics: if it's already there, hoist it to the top.
    if path in current:
        current.remove(path)
    current.insert(0, path)
    settings().setValue(KEYS.recent_files, current[:_MAX_RECENT])


def clear_recent_files() -> None:
    settings().setValue(KEYS.recent_files, [])


_VALID_THEMES = {"light", "dark", "ocean", "forest", "sunset", "auto"}


def get_theme() -> str:
    """Return the active theme name."""
    value = get_str(KEYS.theme, "auto")
    return value if value in _VALID_THEMES else "auto"


def set_theme(name: str) -> None:
    if name in _VALID_THEMES:
        set_str(KEYS.theme, name)


# ---------------------------------------------------------------------------
# Back-compat / typed helpers used by main_window
# ---------------------------------------------------------------------------

def remembered_target_language(default: str = "Japanese") -> str:
    return get_str(KEYS.target_language, default)


def remember_target_language(name: str, code: Optional[str] = None) -> None:
    set_str(KEYS.target_language, name)
    if code:
        set_str(KEYS.target_language_code, code)


def remembered_output_dir(default: str = "") -> str:
    return get_str(KEYS.output_dir, default)


def remember_output_dir(path: str | Path) -> None:
    set_str(KEYS.output_dir, str(path))


# ---------------------------------------------------------------------------
# Session persistence helpers
# ---------------------------------------------------------------------------

def get_session_enabled() -> bool:
    """Return True if session persistence is enabled."""
    val = settings().value(KEYS.session_enabled, "false")
    return str(val).lower() in {"1", "true"}


def set_session_enabled(value: bool) -> None:
    """Set whether session persistence is enabled."""
    settings().setValue(KEYS.session_enabled, "true" if value else "false")


# ---------------------------------------------------------------------------
# Translation option toggles
# ---------------------------------------------------------------------------

def _get_bool(key: str, default: bool = True) -> bool:
    val = settings().value(key, "true" if default else "false")
    return str(val).lower() in {"1", "true"}


def _set_bool(key: str, value: bool) -> None:
    settings().setValue(key, "true" if value else "false")


def get_use_infile_translations() -> bool:
    """Return True (default) if existing translations within the same file should be reused."""
    return _get_bool(KEYS.use_infile_translations, default=True)


def set_use_infile_translations(value: bool) -> None:
    _set_bool(KEYS.use_infile_translations, value)


def get_use_tm_cache() -> bool:
    """Return True (default) if the Translation Memory cache should be used."""
    return _get_bool(KEYS.use_tm_cache, default=True)


def set_use_tm_cache(value: bool) -> None:
    _set_bool(KEYS.use_tm_cache, value)


def get_use_fuzzy_matching() -> bool:
    """Return False (default) if fuzzy TM matching is enabled."""
    return _get_bool(KEYS.use_fuzzy_matching, default=False)


def set_use_fuzzy_matching(value: bool) -> None:
    _set_bool(KEYS.use_fuzzy_matching, value)


def get_use_imported_translations() -> bool:
    """Return True if imported translations are enabled."""
    return _get_bool(KEYS.use_imported_translations, default=False)


def set_use_imported_translations(value: bool) -> None:
    _set_bool(KEYS.use_imported_translations, value)


def get_retranslate_existing() -> bool:
    """Return True if all existing translations should be retranslated."""
    return _get_bool(KEYS.retranslate_existing, default=False)


def set_retranslate_existing(value: bool) -> None:
    _set_bool(KEYS.retranslate_existing, value)


def get_preflight_skip() -> bool:
    """Return True if the pre-flight dialog should be skipped."""
    return _get_bool(KEYS.preflight_skip, default=False)


def set_preflight_skip(value: bool) -> None:
    _set_bool(KEYS.preflight_skip, value)
