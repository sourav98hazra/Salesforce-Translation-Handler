"""Light / dark theme stylesheets.

The theme is applied via ``QApplication.setStyleSheet`` with a small
palette tweak so widgets that don't honour stylesheets (system file
dialogs, QMessageBox) still pick up the right colours.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# ---------------------------------------------------------------------------
# Palettes
# ---------------------------------------------------------------------------

LIGHT_PALETTE = {
    "bg": "#f8fafc",
    "surface": "#ffffff",
    "surface_alt": "#f1f5f9",
    "border": "#e2e8f0",
    "text": "#0f172a",
    "text_muted": "#475569",
    "accent": "#2563eb",
    "accent_hover": "#1d4ed8",
    "sidebar_bg": "#0f172a",
    "sidebar_text": "#cbd5e1",
    "sidebar_text_active": "#ffffff",
    "sidebar_item_hover": "#1e293b",
    "sidebar_item_active": "#1e40af",
    "danger": "#dc2626",
    "warning": "#d97706",
    "success": "#16a34a",
}

DARK_PALETTE = {
    "bg": "#0f172a",
    "surface": "#1e293b",
    "surface_alt": "#0b1322",
    "border": "#334155",
    "text": "#f1f5f9",
    "text_muted": "#94a3b8",
    "accent": "#3b82f6",
    "accent_hover": "#60a5fa",
    "sidebar_bg": "#020617",
    "sidebar_text": "#94a3b8",
    "sidebar_text_active": "#ffffff",
    "sidebar_item_hover": "#1e293b",
    "sidebar_item_active": "#1d4ed8",
    "danger": "#f87171",
    "warning": "#fbbf24",
    "success": "#34d399",
}


# ---------------------------------------------------------------------------
# Stylesheet builder
# ---------------------------------------------------------------------------

def build_stylesheet(palette: dict) -> str:
    p = palette
    return f"""
    QMainWindow, QWidget {{
        background-color: {p["bg"]};
        color: {p["text"]};
    }}
    QGroupBox {{
        background-color: {p["surface"]};
        border: 1px solid {p["border"]};
        border-radius: 6px;
        margin-top: 16px;
        padding-top: 8px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 4px;
        color: {p["text_muted"]};
    }}
    QLabel {{
        background: transparent;
    }}
    QPushButton {{
        background-color: {p["surface_alt"]};
        color: {p["text"]};
        border: 1px solid {p["border"]};
        border-radius: 6px;
        padding: 6px 14px;
        min-height: 24px;
    }}
    QPushButton:hover {{
        background-color: {p["surface"]};
    }}
    QPushButton:disabled {{
        color: {p["text_muted"]};
        background-color: {p["surface_alt"]};
    }}
    QPushButton[primary="true"] {{
        background-color: {p["accent"]};
        color: white;
        border: 1px solid {p["accent"]};
    }}
    QPushButton[primary="true"]:hover {{
        background-color: {p["accent_hover"]};
    }}
    QPushButton[primary="true"]:disabled {{
        background-color: {p["border"]};
        color: {p["text_muted"]};
    }}
    QPushButton[danger="true"] {{
        background-color: {p["danger"]};
        color: white;
        border: 1px solid {p["danger"]};
    }}
    QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox {{
        background-color: {p["surface"]};
        border: 1px solid {p["border"]};
        border-radius: 4px;
        padding: 4px 6px;
        color: {p["text"]};
    }}
    QPlainTextEdit, QTextEdit {{
        font-family: "JetBrains Mono", "Consolas", "Menlo", monospace;
        font-size: 11px;
    }}
    QTableView, QTableWidget {{
        background-color: {p["surface"]};
        alternate-background-color: {p["surface_alt"]};
        gridline-color: {p["border"]};
        border: 1px solid {p["border"]};
        selection-background-color: {p["accent"]};
        selection-color: white;
    }}
    QHeaderView::section {{
        background-color: {p["surface_alt"]};
        color: {p["text_muted"]};
        border: 0;
        border-right: 1px solid {p["border"]};
        border-bottom: 1px solid {p["border"]};
        padding: 6px;
        font-weight: 600;
    }}
    QListWidget {{
        background: transparent;
        border: 0;
        outline: 0;
    }}
    QListWidget::item {{
        padding: 12px;
        margin-bottom: 4px;
        color: {p["sidebar_text"]};
        border-radius: 6px;
    }}
    QListWidget::item:selected {{
        background: {p["sidebar_item_active"]};
        color: {p["sidebar_text_active"]};
    }}
    QListWidget::item:hover {{
        background: {p["sidebar_item_hover"]};
    }}
    QProgressBar {{
        border: 1px solid {p["border"]};
        border-radius: 4px;
        background-color: {p["surface_alt"]};
        text-align: center;
        color: {p["text"]};
    }}
    QProgressBar::chunk {{
        background-color: {p["accent"]};
        border-radius: 3px;
    }}
    QStatusBar {{
        background-color: {p["surface_alt"]};
        color: {p["text_muted"]};
        border-top: 1px solid {p["border"]};
    }}
    QMenuBar {{
        background-color: {p["surface_alt"]};
        color: {p["text"]};
    }}
    QMenuBar::item:selected {{
        background-color: {p["accent"]};
        color: white;
    }}
    QMenu {{
        background-color: {p["surface"]};
        color: {p["text"]};
        border: 1px solid {p["border"]};
    }}
    QMenu::item:selected {{
        background-color: {p["accent"]};
        color: white;
    }}
    QDockWidget::title {{
        background-color: {p["surface_alt"]};
        padding: 6px;
        border-bottom: 1px solid {p["border"]};
        color: {p["text_muted"]};
    }}
    QFrame[role="separator"] {{
        background: {p["border"]};
    }}
    QCheckBox, QRadioButton {{
        color: {p["text"]};
        spacing: 8px;
    }}
    QScrollBar:vertical, QScrollBar:horizontal {{
        background: {p["surface_alt"]};
        width: 10px;
        height: 10px;
        margin: 0;
    }}
    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
        background: {p["border"]};
        border-radius: 5px;
        min-height: 20px;
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{
        height: 0;
        width: 0;
    }}
    """


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def apply_theme(theme: str = "auto") -> dict:
    """Apply ``light`` / ``dark`` / ``auto`` to the running QApplication.

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
        except Exception:
            resolved = "light"

    palette = DARK_PALETTE if resolved == "dark" else LIGHT_PALETTE
    app.setStyleSheet(build_stylesheet(palette))

    # Tweak the QPalette so QMessageBox / native dialogs follow suit.
    qpal = QPalette()
    qpal.setColor(QPalette.ColorRole.Window, QColor(palette["bg"]))
    qpal.setColor(QPalette.ColorRole.WindowText, QColor(palette["text"]))
    qpal.setColor(QPalette.ColorRole.Base, QColor(palette["surface"]))
    qpal.setColor(QPalette.ColorRole.Text, QColor(palette["text"]))
    qpal.setColor(QPalette.ColorRole.Button, QColor(palette["surface_alt"]))
    qpal.setColor(QPalette.ColorRole.ButtonText, QColor(palette["text"]))
    qpal.setColor(QPalette.ColorRole.Highlight, QColor(palette["accent"]))
    qpal.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
    app.setPalette(qpal)
    return palette
