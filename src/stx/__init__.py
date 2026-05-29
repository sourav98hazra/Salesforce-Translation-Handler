"""Salesforce Translation Handler core package.

A professional toolkit for the Salesforce Translation Workbench (STF) workflow:

    STF -> Excel -> Translate -> Review -> STF

Modules
-------
- :mod:`stx.stf`         -- STF parser and writer (byte-exact format).
- :mod:`stx.excel`       -- Excel exporter / importer (per-component sheets).
- :mod:`stx.translate`   -- Translator backends and token protection.
- :mod:`stx.languages`   -- Salesforce language code map.
- :mod:`stx.cli`         -- Typer-based command line interface.
- :mod:`stx.gui`         -- PySide6 desktop application (optional install).
"""

from __future__ import annotations

__version__ = "1.3.0"

__all__ = ["__version__"]
