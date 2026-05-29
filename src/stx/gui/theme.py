"""Light / dark theme stylesheets.

The light palette is intentionally **not** stark white -- modern desktop
apps use a soft slate / cool-grey base so cards stand out without
hurting the eyes.  The dark palette is a complementary deep slate.

Both palettes share the same indigo accent so primary buttons feel
consistent across themes.

The theme is applied via ``QApplication.setStyleSheet`` plus a small
``QPalette`` tweak so widgets that don't honour stylesheets (system
file dialogs, message boxes) still pick up the right colours.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# ---------------------------------------------------------------------------
# Palettes -- adjusted for v1.3 (less whitish, more polished)
# ---------------------------------------------------------------------------

LIGHT_PALETTE = {
    # Professional cool-grey.  Clearly not white -- visible tint everywhere.
    "bg":                "#e2e8f0",       # slate-200 -- main canvas
    "surface":           "#f8fafc",       # slate-50 -- cards / group boxes
    "surface_alt":       "#eef2f7",       # between bg and surface
    "surface_raised":    "#ffffff",       # inputs / tooltips only
    "border":            "#e2e8f0",       # slate-200 -- soft, professional (used everywhere)
    "border_strong":     "#94a3b8",       # slate-400 -- only for splitter handles, focus, scrollbars
    "text":              "#1e293b",       # slate-800
    "text_muted":        "#475569",       # slate-600
    "text_subtle":       "#64748b",       # slate-500
    "accent":            "#4338ca",       # indigo-700 -- deep, professional
    "accent_hover":      "#3730a3",       # indigo-800
    "accent_soft":       "#e0e7ff",       # indigo-100
    "sidebar_bg":        "#1e293b",       # slate-800
    "sidebar_text":      "#94a3b8",       # slate-400
    "sidebar_text_active": "#ffffff",
    "sidebar_item_hover":  "#334155",     # slate-700
    "sidebar_item_active": "#4338ca",     # indigo-700
    "danger":            "#b91c1c",       # red-700
    "danger_soft":       "#fef2f2",
    "warning":           "#b45309",       # amber-700
    "warning_soft":      "#fffbeb",
    "success":           "#15803d",       # green-700
    "success_soft":      "#f0fdf4",
    "info":              "#0369a1",       # sky-700
}

DARK_PALETTE = {
    "bg":                "#1e293b",       # slate-800 -- softer than black, professional
    "surface":           "#283449",       # raised surface for cards
    "surface_alt":       "#334155",       # slate-700
    "surface_raised":    "#3f4b5f",       # inputs / tooltips slightly raised
    "border":            "#334155",       # slate-700 -- subtle on dark bg
    "border_strong":     "#64748b",       # slate-500 -- handles, focus, scrollbars
    "text":              "#f1f5f9",       # slate-100
    "text_muted":        "#cbd5e1",       # slate-300
    "text_subtle":       "#94a3b8",       # slate-400
    "accent":            "#818cf8",       # indigo-400 -- bright enough to stand out
    "accent_hover":      "#a5b4fc",       # indigo-300
    "accent_soft":       "#312e81",       # indigo-900
    "sidebar_bg":        "#0f172a",       # slate-900 -- sidebar a touch darker than canvas for separation
    "sidebar_text":      "#cbd5e1",       # slate-300 -- readable on sidebar_bg
    "sidebar_text_active": "#ffffff",
    "sidebar_item_hover":  "#1e293b",     # slate-800
    "sidebar_item_active": "#4338ca",     # indigo-700
    "danger":            "#f87171",
    "danger_soft":       "#7f1d1d",
    "warning":           "#fbbf24",
    "warning_soft":      "#78350f",
    "success":           "#34d399",
    "success_soft":      "#064e3b",
    "info":              "#38bdf8",
}


# Cool blue/teal -- vibrant but easy to look at.  Sky-blue accent.
OCEAN_PALETTE = {
    "bg":                "#e0f2fe",       # sky-100 -- main canvas
    "surface":           "#f0f9ff",       # sky-50  -- cards / group boxes
    "surface_alt":       "#e0f2fe",       # between bg and surface
    "surface_raised":    "#ffffff",       # inputs / tooltips only
    "border":            "#bae6fd",       # sky-200 -- soft
    "border_strong":     "#7dd3fc",       # sky-300 -- handles / focus
    "text":              "#0c4a6e",       # sky-900
    "text_muted":        "#075985",       # sky-800
    "text_subtle":       "#0369a1",       # sky-700
    "accent":            "#0284c7",       # sky-600 -- main accent
    "accent_hover":      "#0369a1",       # sky-700
    "accent_soft":       "#bae6fd",       # sky-200
    "sidebar_bg":        "#0c4a6e",       # sky-900
    "sidebar_text":      "#7dd3fc",       # sky-300
    "sidebar_text_active": "#ffffff",
    "sidebar_item_hover":  "#075985",     # sky-800
    "sidebar_item_active": "#0284c7",     # sky-600
    "danger":            "#b91c1c",
    "danger_soft":       "#fef2f2",
    "warning":           "#b45309",
    "warning_soft":      "#fffbeb",
    "success":           "#15803d",
    "success_soft":      "#f0fdf4",
    "info":              "#0369a1",
}


# Green / earth -- easy on the eyes.  Forest green accent.
FOREST_PALETTE = {
    "bg":                "#f0fdf4",       # green-50  -- main canvas
    "surface":           "#ffffff",       # cards / group boxes
    "surface_alt":       "#dcfce7",       # green-100
    "surface_raised":    "#ffffff",       # inputs / tooltips
    "border":            "#bbf7d0",       # green-200 -- soft
    "border_strong":     "#86efac",       # green-300 -- handles / focus
    "text":              "#14532d",       # green-900
    "text_muted":        "#166534",       # green-800
    "text_subtle":       "#15803d",       # green-700
    "accent":            "#15803d",       # green-700 -- main accent
    "accent_hover":      "#166534",       # green-800
    "accent_soft":       "#bbf7d0",       # green-200
    "sidebar_bg":        "#14532d",       # green-900
    "sidebar_text":      "#86efac",       # green-300
    "sidebar_text_active": "#ffffff",
    "sidebar_item_hover":  "#166534",     # green-800
    "sidebar_item_active": "#15803d",     # green-700
    "danger":            "#b91c1c",
    "danger_soft":       "#fef2f2",
    "warning":           "#b45309",
    "warning_soft":      "#fffbeb",
    "success":           "#15803d",
    "success_soft":      "#f0fdf4",
    "info":              "#0369a1",
}


# Warm amber / orange -- inviting, sunset-y.
SUNSET_PALETTE = {
    "bg":                "#fffbeb",       # amber-50  -- main canvas
    "surface":           "#ffffff",       # cards / group boxes
    "surface_alt":       "#fef3c7",       # amber-100
    "surface_raised":    "#ffffff",       # inputs / tooltips
    "border":            "#fde68a",       # amber-200 -- soft
    "border_strong":     "#fcd34d",       # amber-300 -- handles / focus
    "text":              "#78350f",       # amber-900
    "text_muted":        "#92400e",       # amber-800
    "text_subtle":       "#b45309",       # amber-700
    "accent":            "#b45309",       # amber-700 -- main accent
    "accent_hover":      "#92400e",       # amber-800
    "accent_soft":       "#fde68a",       # amber-200
    "sidebar_bg":        "#78350f",       # amber-900
    "sidebar_text":      "#fcd34d",       # amber-300
    "sidebar_text_active": "#ffffff",
    "sidebar_item_hover":  "#92400e",     # amber-800
    "sidebar_item_active": "#b45309",     # amber-700
    "danger":            "#b91c1c",
    "danger_soft":       "#fef2f2",
    "warning":           "#b45309",
    "warning_soft":      "#fffbeb",
    "success":           "#15803d",
    "success_soft":      "#f0fdf4",
    "info":              "#0369a1",
}
def build_stylesheet(palette: dict) -> str:
    p = palette
    return f"""
    /* ---------- Window + base widgets ---------- */
    QMainWindow, QWidget {{
        background-color: {p["bg"]};
        color: {p["text"]};
        font-size: 13px;
    }}

    /* ---------- Group boxes (cards) ---------- */
    QGroupBox {{
        background-color: {p["surface"]};
        border: 1px solid {p["border"]};
        border-radius: 6px;
        margin-top: 8px;
        padding: 8px 8px 4px 8px;
        font-weight: 600;
        font-size: 12px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 12px;
        top: -2px;
        padding: 0 6px;
        background-color: {p["surface"]};
        color: {p["text_subtle"]};
        text-transform: uppercase;
        letter-spacing: 0.5px;
        font-size: 11px;
    }}

    /* ---------- Labels ---------- */
    QLabel {{
        background: transparent;
        color: {p["text"]};
    }}

    /* ---------- Buttons ---------- */
    QPushButton {{
        background-color: {p["surface_raised"]};
        color: {p["text"]};
        border: 1px solid {p["border"]};
        border-radius: 6px;
        padding: 5px 12px;
        min-height: 20px;
    }}
    QPushButton:hover {{
        background-color: {p["surface_alt"]};
        border-color: {p["border_strong"]};
    }}
    QPushButton:pressed {{
        background-color: {p["surface_alt"]};
    }}
    QPushButton:disabled {{
        color: {p["text_subtle"]};
        background-color: {p["surface_alt"]};
        border-color: {p["border"]};
    }}
    QPushButton[primary="true"] {{
        background-color: {p["accent"]};
        color: white;
        border: 1px solid {p["accent"]};
        font-weight: 600;
    }}
    QPushButton[primary="true"]:hover {{
        background-color: {p["accent_hover"]};
        border-color: {p["accent_hover"]};
    }}
    QPushButton[primary="true"]:pressed {{
        background-color: {p["accent_hover"]};
    }}
    QPushButton[primary="true"]:disabled {{
        background-color: {p["border"]};
        color: {p["text_subtle"]};
        border-color: {p["border"]};
    }}
    QPushButton[danger="true"] {{
        background-color: {p["danger"]};
        color: white;
        border: 1px solid {p["danger"]};
        font-weight: 600;
    }}
    QPushButton[danger="true"]:hover {{
        background-color: {p["danger"]};
    }}

    /* ---------- Inputs ---------- */
    QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background-color: {p["surface_raised"]};
        border: 1px solid {p["border"]};
        border-radius: 6px;
        padding: 3px 6px;
        color: {p["text"]};
        selection-background-color: {p["accent"]};
        selection-color: white;
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
    QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border-color: {p["accent"]};
        outline: none;
    }}
    QLineEdit:read-only, QPlainTextEdit:read-only, QTextEdit:read-only {{
        background-color: {p["surface_raised"]};
        color: {p["text_muted"]};
    }}
    QPlainTextEdit, QTextEdit {{
        font-family: "JetBrains Mono", "Cascadia Code", "Consolas", "Menlo", monospace;
        font-size: 11px;
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {p["surface"]};
        border: 1px solid {p["border"]};
        selection-background-color: {p["accent"]};
        selection-color: white;
        outline: none;
    }}

    /* ---------- Tables ---------- */
    QTableView, QTableWidget {{
        background-color: {p["surface"]};
        alternate-background-color: {p["surface_raised"]};
        gridline-color: {p["border"]};
        border: 1px solid {p["border"]};
        border-radius: 6px;
        selection-background-color: {p["accent"]};
        selection-color: white;
    }}
    QTableView::item, QTableWidget::item {{
        padding: 4px 8px;
    }}
    QHeaderView::section {{
        background-color: {p["surface_alt"]};
        color: {p["text_muted"]};
        border: 0;
        border-right: 1px solid {p["border"]};
        border-bottom: 1px solid {p["border"]};
        padding: 6px 8px;
        font-weight: 600;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}

    /* ---------- Sidebar list ---------- */
    QListWidget {{
        background: transparent;
        border: 0;
        outline: 0;
    }}
    QListWidget::item {{
        padding: 12px 14px;
        margin-bottom: 4px;
        color: {p["sidebar_text"]};
        border-radius: 8px;
    }}
    QListWidget::item:selected {{
        background: {p["sidebar_item_active"]};
        color: {p["sidebar_text_active"]};
        font-weight: 600;
    }}
    QListWidget::item:hover {{
        background: {p["sidebar_item_hover"]};
    }}

    /* ---------- Progress bar ---------- */
    QProgressBar {{
        border: 1px solid {p["border"]};
        border-radius: 6px;
        background-color: {p["surface_alt"]};
        text-align: center;
        color: {p["text"]};
        height: 22px;
        font-weight: 600;
    }}
    QProgressBar::chunk {{
        background-color: {p["accent"]};
        border-radius: 5px;
    }}

    /* ---------- Status bar ---------- */
    QStatusBar {{
        background-color: {p["surface_alt"]};
        color: {p["text_muted"]};
        border-top: 1px solid {p["border"]};
    }}

    /* ---------- Menu bar / menus ---------- */
    QMenuBar {{
        background-color: {p["surface_alt"]};
        color: {p["text"]};
        padding: 2px 4px;
        border-bottom: 1px solid {p["border"]};
    }}
    QMenuBar::item {{
        background: transparent;
        padding: 6px 12px;
        border-radius: 4px;
    }}
    QMenuBar::item:selected {{
        background-color: {p["accent_soft"]};
        color: {p["accent"]};
    }}
    QMenu {{
        background-color: {p["surface"]};
        color: {p["text"]};
        border: 1px solid {p["border"]};
        border-radius: 6px;
        padding: 4px;
    }}
    QMenu::item {{
        padding: 6px 18px 6px 14px;
        border-radius: 4px;
    }}
    QMenu::item:selected {{
        background-color: {p["accent"]};
        color: white;
    }}

    /* ---------- Dock ---------- */
    QDockWidget::title {{
        background-color: {p["surface_alt"]};
        padding: 6px 12px;
        border-bottom: 1px solid {p["border"]};
        color: {p["text_muted"]};
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        font-size: 11px;
    }}

    /* ---------- Tabs ---------- */
    QTabWidget::pane {{
        border: 1px solid {p["border"]};
        border-radius: 6px;
        background-color: {p["surface"]};
        top: -1px;
    }}
    QTabBar::tab {{
        background-color: {p["surface_alt"]};
        color: {p["text_muted"]};
        padding: 8px 18px;
        border: 1px solid {p["border"]};
        border-bottom: 0;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        margin-right: 2px;
        font-weight: 600;
    }}
    QTabBar::tab:selected {{
        background-color: {p["surface"]};
        color: {p["accent"]};
        border-color: {p["border"]};
    }}
    QTabBar::tab:hover:!selected {{
        background-color: {p["surface_raised"]};
    }}

    /* ---------- Frames + separators ---------- */
    QFrame[role="separator"] {{
        background: {p["border"]};
        border: 0;
        max-height: 1px;
    }}
    QFrame[role="card"] {{
        background-color: {p["surface"]};
        border: 1px solid {p["border"]};
        border-radius: 8px;
    }}

    /* ---------- Checkboxes / Radio ---------- */
    QCheckBox, QRadioButton {{
        color: {p["text"]};
        spacing: 8px;
    }}
    QCheckBox::indicator, QRadioButton::indicator {{
        width: 16px;
        height: 16px;
    }}
    QCheckBox::indicator:unchecked {{
        border: 1.5px solid {p["border_strong"]};
        background: {p["surface"]};
        border-radius: 3px;
    }}
    QCheckBox::indicator:checked {{
        border: 1.5px solid {p["accent"]};
        background: {p["accent"]};
        border-radius: 3px;
    }}

    /* ---------- Splitters ----------
       Qt's QSS overrides setHandleWidth() when width/height is set here,
       so this is the *single source of truth* for handle size.  Keep
       handles slim (4px) and quiet by default -- soft "border" colour --
       and only highlight on hover so they don't read as heavy bars.
    */
    QSplitter::handle {{
        background-color: {p["border"]};
    }}
    QSplitter::handle:hover {{
        background-color: {p["accent"]};
    }}
    QSplitter::handle:horizontal {{
        width: 4px;
    }}
    QSplitter::handle:vertical {{
        height: 4px;
    }}

    /* ---------- Scrollbars ---------- */
    QScrollBar:vertical, QScrollBar:horizontal {{
        background: transparent;
        width: 11px;
        height: 11px;
        margin: 0;
    }}
    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
        background: {p["border_strong"]};
        border-radius: 5px;
        min-height: 24px;
        margin: 2px;
    }}
    QScrollBar::handle:hover {{
        background: {p["text_subtle"]};
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{
        height: 0;
        width: 0;
    }}

    /* ---------- ToolTips ---------- */
    QToolTip {{
        background-color: {p["surface_raised"]};
        color: {p["text"]};
        border: 1px solid {p["border_strong"]};
        border-radius: 4px;
        padding: 4px 8px;
    }}
    """


def apply_theme(theme: str = "auto") -> dict:
    """Apply a named theme to the running QApplication.

    Supported names: ``light``, ``dark``, ``ocean``, ``forest``,
    ``sunset``, ``auto``.  ``auto`` follows the OS color scheme and
    resolves to either ``light`` or ``dark``.

    Returns the active palette dict so callers can tint widgets that
    aren't covered by the stylesheet (e.g. dynamic chart colours).
    """
    app = QApplication.instance()
    if app is None:
        return LIGHT_PALETTE

    resolved = theme
    if theme == "auto":
        try:
            hints = app.styleHints()
            scheme = hints.colorScheme()
            from PySide6.QtCore import Qt

            resolved = "dark" if scheme == Qt.ColorScheme.Dark else "light"
        except Exception:  # noqa: BLE001
            resolved = "light"

    palettes = {
        "light":   LIGHT_PALETTE,
        "dark":    DARK_PALETTE,
        "ocean":   OCEAN_PALETTE,
        "forest":  FOREST_PALETTE,
        "sunset":  SUNSET_PALETTE,
    }
    palette = palettes.get(resolved, LIGHT_PALETTE)
    app.setStyleSheet(build_stylesheet(palette))

    # Tweak QPalette so native dialogs follow suit.
    qpal = QPalette()
    qpal.setColor(QPalette.ColorRole.Window, QColor(palette["bg"]))
    qpal.setColor(QPalette.ColorRole.WindowText, QColor(palette["text"]))
    qpal.setColor(QPalette.ColorRole.Base, QColor(palette["surface"]))
    qpal.setColor(QPalette.ColorRole.AlternateBase, QColor(palette["surface_raised"]))
    qpal.setColor(QPalette.ColorRole.Text, QColor(palette["text"]))
    qpal.setColor(QPalette.ColorRole.Button, QColor(palette["surface_raised"]))
    qpal.setColor(QPalette.ColorRole.ButtonText, QColor(palette["text"]))
    qpal.setColor(QPalette.ColorRole.Highlight, QColor(palette["accent"]))
    qpal.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
    qpal.setColor(QPalette.ColorRole.PlaceholderText, QColor(palette["text_subtle"]))
    qpal.setColor(QPalette.ColorRole.ToolTipBase, QColor(palette["surface_raised"]))
    qpal.setColor(QPalette.ColorRole.ToolTipText, QColor(palette["text"]))
    app.setPalette(qpal)
    return palette
