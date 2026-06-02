"""Custom About dialog -- a polished replacement for the bare QMessageBox.

Layout::

    +-------------------------------------------------------+
    | About -- Salesforce Translation Manager         [X]   |
    +-------------------------------------------------------+
    |  [LOGO 64]   Salesforce Translation Manager           |
    |              Version <stx.__version__>                |
    |              Professional desktop app for ...         |
    |  -----------------------------------------------      |
    |  [ Overview | Features | System | Credits ]           |
    |  ... tab content ...                                  |
    |  -----------------------------------------------      |
    |  [User Guide]  [GitHub]                    [Close]    |
    +-------------------------------------------------------+

The User Guide button opens ``USER_GUIDE.md`` *inside the app* (rendered
as Markdown in a scrollable QTextBrowser) so users never get bounced
out to an external editor or browser.  The GitHub button opens the
public repository in the default browser.
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .. import __version__

GITHUB_URL = "https://github.com/sourav98hazra/Salesforce-Translation-Handler"

# Indigo accent used for in-tab headings.  Kept here as a constant so it
# stays in sync with the rest of the theme without hard-coding it
# everywhere.
_HEADING_COLOR = "#4338ca"
_MUTED_COLOR = "#64748b"


# ---------------------------------------------------------------------------
# In-app user guide viewer
# ---------------------------------------------------------------------------

class UserGuideDialog(QDialog):
    """Render ``USER_GUIDE.md`` inside the app via QTextBrowser.

    We deliberately don't shell out to the system's default editor or
    browser -- the guide should feel like part of the application.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("User Guide -- Salesforce Translation Manager")
        from .pages.base import clamp_to_screen
        clamp_to_screen(self, 820, 640)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)

        title = QLabel("User Guide")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: 700; color: {_HEADING_COLOR};"
        )
        layout.addWidget(title)

        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        self._browser.setStyleSheet(
            "QTextBrowser { padding: 12px; font-size: 13px; }"
        )
        layout.addWidget(self._browser, stretch=1)

        # Footer with a single Close button right-aligned.
        footer = QHBoxLayout()
        footer.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        footer.addWidget(close)
        layout.addLayout(footer)

        self._load_guide()

    def _load_guide(self) -> None:
        guide_path = _find_user_guide()
        if guide_path is None or not guide_path.is_file():
            self._browser.setHtml(
                "<p style='padding:24px;color:#475569;'>"
                "The user guide file (<code>USER_GUIDE.md</code>) was not "
                "found alongside this build.<br><br>"
                "You can read the latest version online at "
                f"<a href='{GITHUB_URL}'>{GITHUB_URL}</a>."
                "</p>"
            )
            return
        try:
            text = guide_path.read_text(encoding="utf-8")
        except OSError as exc:
            self._browser.setPlainText(f"Failed to load user guide: {exc}")
            return
        # QTextBrowser supports Markdown natively (Qt 5.14+).
        try:
            self._browser.setMarkdown(text)
        except Exception:  # noqa: BLE001 -- fall back if Markdown unavailable
            self._browser.setPlainText(text)


# ---------------------------------------------------------------------------
# About dialog
# ---------------------------------------------------------------------------

class AboutDialog(QDialog):
    """Custom About modal with a four-tab layout."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("About -- Salesforce Translation Manager")
        self.setMinimumSize(QSize(600, 500))
        from .pages.base import clamp_to_screen
        clamp_to_screen(self, 640, 540)
        self.setModal(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 16)
        outer.setSpacing(14)

        outer.addLayout(self._build_header())
        outer.addWidget(self._make_separator())

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_overview_tab(), "Overview")
        self._tabs.addTab(self._build_features_tab(), "Features")
        self._tabs.addTab(self._build_system_tab(), "System")
        self._tabs.addTab(self._build_credits_tab(), "Credits")
        outer.addWidget(self._tabs, stretch=1)

        outer.addWidget(self._make_separator())
        outer.addLayout(self._build_footer())

    # ------------------------------------------------------------------ pieces

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(16)
        row.setContentsMargins(0, 0, 0, 0)
        row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Logo (64x64) -- rendered from the bundled SVG when available.
        logo_label = QLabel()
        logo_label.setFixedSize(64, 64)
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = _render_logo(64)
        if pixmap is not None:
            logo_label.setPixmap(pixmap)
        else:
            logo_label.setText("\u2b22")
            logo_label.setStyleSheet(
                "font-size: 44px; color: #818cf8;"
            )
        row.addWidget(logo_label, alignment=Qt.AlignmentFlag.AlignTop)

        # Title block -- name, version, tagline.
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.setContentsMargins(0, 0, 0, 0)

        name = QLabel("Salesforce Translation Manager")
        name.setStyleSheet("font-size: 18px; font-weight: 700;")
        text_col.addWidget(name)

        version = QLabel(f"Version {__version__}")
        version.setStyleSheet(f"font-size: 12px; color: {_MUTED_COLOR};")
        text_col.addWidget(version)

        tagline = QLabel(
            "Professional desktop app for managing Salesforce Translation "
            "Workbench (.stf) files with a six-phase pipeline, auto-translation, "
            "validation, and one-click export."
        )
        tagline.setWordWrap(True)
        tagline.setStyleSheet(f"font-size: 12px; color: {_MUTED_COLOR};")
        text_col.addWidget(tagline)
        text_col.addStretch(1)

        row.addLayout(text_col, stretch=1)
        return row

    def _build_footer(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        row.setContentsMargins(0, 0, 0, 0)

        guide_btn = QPushButton("\U0001f4d6  User Guide")
        guide_btn.setToolTip("Open the in-app user guide (F1)")
        guide_btn.clicked.connect(self._on_user_guide)
        row.addWidget(guide_btn)

        github_btn = QPushButton("\U0001f310  GitHub")
        github_btn.setToolTip("Open the project repository on GitHub")
        github_btn.clicked.connect(self._on_github)
        row.addWidget(github_btn)

        row.addStretch(1)

        close_btn = QPushButton("Close")
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.reject)
        row.addWidget(close_btn)
        return row

    def _make_separator(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setStyleSheet("color: #cbd5e1;")
        line.setFixedHeight(1)
        return line

    # ------------------------------------------------------------------ tabs

    def _build_overview_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 14, 8, 8)
        layout.setSpacing(10)

        layout.addWidget(_heading("What it does"))
        layout.addWidget(_body(
            "Salesforce Translation Manager streamlines the Translation "
            "Workbench round-trip with a six-phase pipeline that you can "
            "walk end-to-end -- or jump into at any single step."
        ))

        layout.addWidget(_heading("The 6-phase pipeline"))
        layout.addWidget(_body(
            "1. Import STF -- pick the source .stf file you exported from "
            "Salesforce.\n"
            "2. STF \u2192 Excel -- convert the flat file into an organised "
            "workbook with one sheet per component type.\n"
            "3. Translate -- auto-translate untranslated rows with the "
            "configured backend (Google free by default).\n"
            "4. Browse & Review -- view, search, and edit translations; "
            "re-upload an externally-translated workbook here.\n"
            "5. Validate & Fix -- detect issues (length overflow, "
            "lost placeholders, duplicate keys) and apply deterministic "
            "auto-fixes.\n"
            "6. Export STF -- write the final .stf file (byte-exact format) "
            "ready to upload back to Salesforce."
        ))

        layout.addWidget(_heading("Key benefits"))
        layout.addWidget(_body(
            "\u2022 Salesforce IDs (15/18 char), {!Placeholders}, MessageFormat "
            "tokens, and HTML are sentinel-protected -- never altered by the "
            "translator.\n"
            "\u2022 Translation Memory caches every translation across runs, "
            "saving time and API quota.\n"
            "\u2022 Glossary support keeps brand and product names consistent.\n"
            "\u2022 Deterministic auto-fix means the same input always yields "
            "the same output -- great for diffs and code review.\n"
            "\u2022 Each phase works on its own input or as part of the "
            "end-to-end flow -- both modes are first-class.\n"
            "\u2022 Five themes (light, dark, ocean, forest, sunset) plus "
            "auto, with soft borders and rounded panels for a calm, modern "
            "look.\n"
            "\u2022 Screen-aware window sizing -- the app never opens wider "
            "than your display, the sidebar is resizable, and the editor "
            "splitter in Phase 4 / 5 drags freely so the text areas grow "
            "to whatever height you want."
        ))

        layout.addStretch(1)
        return _wrap_scrollable(widget)

    def _build_features_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 14, 8, 8)
        layout.setSpacing(10)

        layout.addWidget(_heading("Translation Engine"))
        layout.addWidget(_bullets([
            "Google Translate (free tier) -- default, no API key required",
            "DeepL, Azure, OpenAI -- when API keys are configured "
            "(Translation \u2192 Settings)",
            "Translation Memory (SQLite) -- caches translations across "
            "runs for speed",
            "In-file translation reuse -- if label 'Save' is already "
            "translated elsewhere in the same file, that translation is "
            "reused without any API call (Translation menu toggle)",
            "Glossary support -- protect brand and product terms from "
            "modification",
            "In-run deduplication -- the same string is translated only once",
            "Fuzzy TM matching -- finds approximate matches in the TM "
            "(configurable threshold)",
            "Adaptive rate limiting -- auto-tunes to backend tolerance",
            "Checkpoint resume -- interruptions save progress; the next "
            "run continues where it left off",
        ]))

        layout.addWidget(_heading("Translation menu"))
        layout.addWidget(_bullets([
            "Use in-file translations (default on) -- reuse existing "
            "translations from the same file before calling the API",
            "Use Translation Memory cache (default on)",
            "Use Fuzzy matching (default on)",
            "Use imported translations (default off) -- apply an external "
            "Excel with highest priority",
            "Retranslate all (overwrite existing) (default off) -- override all rows",
            "Pre-flight confirmation dialog -- summarises active options "
            "before every run; dismissable with 'Don't show again'",
        ]))

        layout.addWidget(_heading("Safety & Protection"))
        layout.addWidget(_bullets([
            "Salesforce IDs (15 / 18 char) -- sentinel-protected",
            "{!Placeholders} -- sentinel-protected",
            "{0}, {1} MessageFormat tokens -- sentinel-protected",
            "HTML tags & attributes -- walked tag-by-tag, never altered",
            "URLs and email addresses -- preserved verbatim",
            "Escape sequences (\\n, \\t) -- preserved",
        ]))

        layout.addWidget(_heading("Workflow"))
        layout.addWidget(_bullets([
            "Each phase works independently or as part of the end-to-end "
            "pipeline",
            "Validation with auto-fix (length trimming, placeholder "
            "restoration, deduplication)",
            "Pop-out any panel into a separate window for side-by-side "
            "comparison",
            "Drag-and-drop file loading anywhere in the window",
            "Recent files menu and persistent settings",
            "Multi-language batch translation",
            "Column-wise filtering (Excel-like header right-click menus) "
            "in Phase 4 -- sort, filter by distinct values",
            "App-wide action history (Ctrl+Shift+Z / Ctrl+Shift+Y) for "
            "undoing major actions like file loads and translations",
            "Professional filename generation with date and language code",
            "Reset Session / Reset Phase for controlled state management",
            "Previous Phase navigation (Ctrl+B) for quick back-stepping",
            "Workflow override confirmation when loading a new file into "
            "an active workflow",
        ]))

        layout.addWidget(_heading("Look & feel"))
        layout.addWidget(_bullets([
            "Five themes -- light, dark, ocean, forest, sunset -- plus auto",
            "Soft borders and rounded panels for a calm, professional look",
            "Screen-aware window sizing -- never opens wider than your "
            "display",
            "Resizable sidebar (220-280 px) with status badges per phase",
            "Draggable splitter between table and editor in Phase 4 / 5 "
            "so the Source / Translation text areas grow to any height",
        ]))

        layout.addWidget(_heading("Performance"))
        layout.addWidget(_bullets([
            "Parallel translation workers (configurable)",
            "Wake-lock prevents the system from idle-sleeping during long "
            "runs",
            "Per-row gap-prevention sweep -- no rows are ever lost",
            "Multi-click protection -- you can't double-start or "
            "double-cancel a long-running job",
        ]))

        layout.addStretch(1)
        return _wrap_scrollable(widget)

    def _build_system_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 14, 8, 8)
        layout.setSpacing(10)

        layout.addWidget(_heading("Runtime"))
        form = QFormLayout()
        form.setHorizontalSpacing(20)
        form.setVerticalSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        for label_text, value_text in _collect_system_info():
            form.addRow(_form_label(label_text), _form_value(value_text))
        layout.addLayout(form)

        layout.addStretch(1)
        return _wrap_scrollable(widget)

    def _build_credits_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 14, 8, 8)
        layout.setSpacing(10)

        layout.addWidget(_heading("Credits"))
        layout.addWidget(_body(
            "Author: Sourav Hazra\n"
            "License: MIT"
        ))

        layout.addWidget(_heading("Built with"))
        layout.addWidget(_bullets([
            "PySide6 -- Qt for Python (LGPL)",
            "openpyxl -- Excel read/write (MIT)",
            "deep-translator -- backend abstraction (MIT)",
            "beautifulsoup4 -- HTML walking (MIT)",
        ]))

        layout.addWidget(_heading("Repository"))
        repo_link = QLabel(f"<a href='{GITHUB_URL}'>{GITHUB_URL}</a>")
        repo_link.setOpenExternalLinks(True)
        repo_link.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        repo_link.setStyleSheet("font-size: 12px;")
        layout.addWidget(repo_link)

        layout.addSpacing(4)
        tagline = QLabel(
            "Made with care for translators and developers."
        )
        tagline.setStyleSheet(
            f"font-size: 12px; color: {_MUTED_COLOR}; font-style: italic;"
        )
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(tagline)

        layout.addStretch(1)
        return _wrap_scrollable(widget)

    # ------------------------------------------------------------------ slots

    def _on_user_guide(self) -> None:
        """Show the user guide *in-app* (no external app launch)."""
        # Prefer the parent window's hook -- it already knows the on-disk
        # path of USER_GUIDE.md and may render it through whatever flow the
        # rest of the app uses.
        parent = self.parent()
        if parent is not None and hasattr(parent, "_show_user_guide"):
            try:
                parent._show_user_guide()  # type: ignore[attr-defined]
                return
            except Exception:  # noqa: BLE001 -- fall back to local viewer
                pass

        # Fallback -- render USER_GUIDE.md ourselves in a modal dialog.
        viewer = UserGuideDialog(self)
        viewer.exec()

    def _on_github(self) -> None:
        QDesktopServices.openUrl(QUrl(GITHUB_URL))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _heading(text: str) -> QLabel:
    """Indigo-accented section heading used inside tabs."""
    label = QLabel(text)
    label.setStyleSheet(
        f"color: {_HEADING_COLOR}; font-size: 13px; font-weight: 700; "
        "margin-top: 4px;"
    )
    return label


def _body(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setStyleSheet("font-size: 12px; line-height: 1.45;")
    return label


def _bullets(items) -> QLabel:
    """Render a list as a single bullet block.

    A QLabel is enough -- no need for QListWidget / fancy widgets here.
    """
    bullet = "\u2022"
    body = "\n".join(f"  {bullet}  {item}" for item in items)
    label = QLabel(body)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setStyleSheet("font-size: 12px; line-height: 1.5;")
    return label


def _form_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(f"color: {_MUTED_COLOR}; font-size: 12px;")
    return label


def _form_value(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setStyleSheet("font-size: 12px;")
    label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    return label


def _wrap_scrollable(widget: QWidget) -> QWidget:
    """Wrap a tab page in a QScrollArea so long content scrolls.

    Lazy import keeps this module light when widgets aren't needed.
    """
    from PySide6.QtWidgets import QScrollArea

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(widget)
    return scroll


def _render_logo(size: int) -> Optional[QPixmap]:
    """Render the bundled SVG logo at ``size``x``size`` -- or ``None``."""
    svg_path = Path(__file__).parent / "assets" / "logo.svg"
    if not svg_path.is_file():
        return None
    try:
        from PySide6.QtSvg import QSvgRenderer
    except ImportError:
        return None
    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        return None
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        renderer.render(painter)
    finally:
        painter.end()
    return pixmap


def _find_user_guide() -> Optional[Path]:
    """Locate ``USER_GUIDE.md`` relative to the installed package."""
    here = Path(__file__).resolve()
    # src/stx/gui/about_dialog.py -> repo root is parents[3]
    candidates = [
        here.parent.parent.parent.parent / "USER_GUIDE.md",   # src layout
        here.parent.parent.parent / "USER_GUIDE.md",          # flat layout
        Path.cwd() / "USER_GUIDE.md",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def _collect_system_info() -> list[tuple[str, str]]:
    """Build the list of (label, value) rows shown on the System tab."""
    info: list[tuple[str, str]] = []

    # Python
    info.append(("Python", _short_python_version()))

    # PySide6 + Qt
    try:
        import PySide6  # type: ignore
        info.append(("PySide6", getattr(PySide6, "__version__", "unknown")))
    except ImportError:  # pragma: no cover -- PySide6 is required at runtime
        info.append(("PySide6", "not available"))
    try:
        from PySide6 import QtCore  # type: ignore
        info.append(("Qt", getattr(QtCore, "__version__", "unknown")))
    except ImportError:  # pragma: no cover
        info.append(("Qt", "not available"))

    # OS
    info.append((
        "Operating system",
        f"{platform.system()} {platform.release()}".strip(),
    ))

    # App data dir (where QSettings + recent files live)
    info.append(("App data directory", _app_data_dir()))

    # Active translator backend (read from QSettings, falling back to default)
    info.append(("Active translator", _active_backend_label()))

    # Translation memory entry count and path
    tm_path, tm_entries = _tm_summary()
    info.append(("Translation memory", f"{tm_entries:,} entries"))
    info.append(("TM database", tm_path))

    return info


def _short_python_version() -> str:
    # ``sys.version`` has the build / compiler tail -- keep just the line
    # the user actually cares about: "3.11.6 (main, ...)".  We use the
    # parsed version_info plus the impl name for readability.
    impl = platform.python_implementation()
    v = sys.version_info
    return f"{impl} {v.major}.{v.minor}.{v.micro}"


def _app_data_dir() -> str:
    try:
        from . import settings as gui_settings  # type: ignore

        s = gui_settings.settings()
        path = s.fileName()
        # fileName() returns the settings file path; the directory is what
        # the user really wants to look at on disk.
        return str(Path(path).parent) if path else "(unavailable)"
    except Exception:  # noqa: BLE001
        return "(unavailable)"


def _active_backend_label() -> str:
    try:
        from . import settings as gui_settings  # type: ignore
        from ..translate import list_backends  # type: ignore

        key = gui_settings.get_str(gui_settings.KEYS.backend, "google")
        for info in list_backends():
            if info.key == key:
                return info.label
        return key or "google"
    except Exception:  # noqa: BLE001
        return "Google Translate (free)"


def _tm_summary() -> tuple[str, int]:
    """Return ``(path_str, entry_count)`` for the active TM, defensively."""
    try:
        from . import settings as gui_settings  # type: ignore
        from ..memory import TranslationMemory, default_tm_path  # type: ignore

        configured = gui_settings.get_str(gui_settings.KEYS.memory_path, "")
        path = Path(configured) if configured else default_tm_path()
        if not path.exists():
            return (f"{path}  (not yet created)", 0)
        try:
            tm = TranslationMemory(path)
            return (str(path), tm.count())
        except Exception:  # noqa: BLE001 -- corrupt or locked DB
            return (str(path), 0)
    except Exception:  # noqa: BLE001
        return ("(unavailable)", 0)
