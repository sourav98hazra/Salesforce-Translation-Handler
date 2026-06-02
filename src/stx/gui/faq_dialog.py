"""Searchable FAQ dialog for the Salesforce Translation Manager."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .pages.base import clamp_to_screen

# ---------------------------------------------------------------------------
# FAQ data — (category, question, answer)
# ---------------------------------------------------------------------------

_FAQ: list[tuple[str, str, str]] = [
    # -- Getting started --
    (
        "Getting started",
        "How do I install the app?",
        "On Windows, double-click setup_desktop_app.bat the first time — it creates a virtual "
        "environment, installs all dependencies, and adds a desktop shortcut you can use from then on. "
        "(launch.bat works too if you just want to run it without a shortcut.) "
        "On macOS double-click launch.command; on Linux run chmod +x launch.sh then double-click it.",
    ),
    (
        "Getting started",
        "Is there a standalone installer or .exe I can share with non-technical users?",
        "Yes. On Windows run 'python build_secure_setup.py --exe' to produce a single self-contained "
        ".exe (no Python needed on the target machine), or 'python build_secure_setup.py' to build a "
        "full Setup installer (requires Inno Setup 6). Both emit a matching .sha256 file so recipients "
        "can verify the download with 'certutil -hashfile <file> SHA256'. See docs/INSTALLER.md.",
    ),
    (
        "Getting started",
        "Why does launch.bat say Python was not found?",
        "Python 3.9 or newer must be installed and added to PATH. Download it from "
        "python.org/downloads and tick 'Add Python to PATH' during installation.",
    ),
    (
        "Getting started",
        "How do I get the latest version of the app?",
        "Open a terminal in the project folder, run git pull, then delete the .venv folder "
        "(rmdir /s /q .venv on Windows) and double-click launch.bat again. "
        "From now on the launcher will reinstall automatically when code changes.",
    ),
    (
        "Getting started",
        "What is the overall workflow?",
        "The app has six phases: (1) Import STF — load your Salesforce STF file. "
        "(2) STF to Excel — convert to an organised workbook. "
        "(3) Translate — auto-translate untranslated rows. "
        "(4) Review — browse, edit, approve translations. "
        "(5) Validate & Fix — catch and fix errors. "
        "(6) Export STF — write the final STF files back to Salesforce.",
    ),
    (
        "Getting started",
        "Can I start from any phase without going through Phase 1?",
        "Yes. Every phase has a Load button. Click any phase in the sidebar, then load the "
        "appropriate file (STF or Excel) directly into that phase.",
    ),
    # -- Phase 1 --
    (
        "Phase 1 — Import STF",
        "What is the difference between 'Translation language' and 'Label language'?",
        "'Translation language' is the language the STF translates INTO (e.g. Japanese). "
        "It is read from the STF header. "
        "'Label language' is the language the source labels are written in (usually English). "
        "It is auto-detected from the label text. Both can be changed in the dropdowns.",
    ),
    (
        "Phase 1 — Import STF",
        "Why does auto-detection show low confidence?",
        "The langdetect library needs a reasonable number of text samples. If the STF labels are "
        "very short, numeric, or mostly proper nouns/IDs, detection may be unreliable. "
        "Simply select the correct language from the dropdown manually.",
    ),
    (
        "Phase 1 — Import STF",
        "My STF has both translated and untranslated rows. How are existing translations handled?",
        "By default only blank/untranslated rows are translated — existing translations are kept "
        "untouched. There is no checkbox for this in Phase 1; the behaviour is controlled in Phase 3 "
        "via the Translation menu:\n"
        "• 'Use in-file translations' (on by default) reuses a translation already present "
        "elsewhere in the same file for matching labels.\n"
        "• 'Retranslate all (overwrite existing)' (off by default) sends ALL rows — including translated "
        "ones — to the backend, overwriting them. In Phase 3 this also appears as the "
        "'Retranslate all (overwrite existing)' checkbox when the file already has translated rows.",
    ),
    (
        "Phase 1 — Import STF",
        "Can I preview the STF before converting to Excel?",
        "Yes. The Preview panel shows the first 100 rows. Click the pop-out icon (↗) in the "
        "top-right of the Preview group to open it in a larger resizable window.",
    ),
    # -- Phase 2 --
    (
        "Phase 2 — STF to Excel",
        "What does the organised Excel look like?",
        "Each component type (CustomLabel, ButtonOrLink, etc.) gets its own sheet. "
        "There is also a Content Details index sheet. "
        "Columns are: Key, Label, Translation.",
    ),
    (
        "Phase 2 — STF to Excel",
        "What is a component type?",
        "Salesforce metadata is grouped by type — CustomLabel, CustomField, Flow, etc. "
        "The first part of each key (before the first dot) is the component type.",
    ),
    # -- Phase 3 --
    (
        "Phase 3 — Translate",
        "What is the Translation menu?",
        "The Translation menu in the menu bar groups all translation behaviour toggles:\n"
        "• Use in-file translations (default on) — reuse translations already present in the same file\n"
        "• Use Translation Memory cache (default on) — reuse from previous runs\n"
        "• Use Fuzzy matching (default off) — approximate TM matches\n"
        "• Use imported translations (default off) — apply an external Excel at highest priority\n"
        "• Retranslate all (overwrite existing) (default off) — send ALL rows to the backend\n"
        "All toggles persist between sessions. Open Settings... (Ctrl+,) for advanced options.",
    ),
    (
        "Phase 3 — Translate",
        "What is the pre-flight confirmation dialog?",
        "Before every translation run, a summary dialog shows the current translation options "
        "so you can review them before committing. It shows: which options are on/off, the "
        "backend, workers, and how many rows will be translated.\n"
        "Tick 'Don't show this dialog again' to skip it in future runs.\n"
        "Re-enable it via Translation → Re-enable pre-flight confirmation.",
    ),
    (
        "Phase 3 — Translate",
        "What does 'Use in-file translations' mean?",
        "If the same label text (e.g. 'Save') is already translated elsewhere in the same "
        "STF or Excel file, that translation is reused for untranslated rows with the same "
        "label — without any API call. This is on by default.\n"
        "Example: CustomLabel.SaveButton has translation '保存'. "
        "CustomLabel.SaveAction (untranslated) has the same label 'Save' — it gets '保存' "
        "automatically.\n"
        "When Retranslate all (overwrite existing) is on, in-file reuse is skipped.",
    ),
    (
        "Phase 3 — Translate",
        "What does 'Retranslate all (overwrite existing)' do?",
        "When checked in the Translation menu, ALL rows in the document — including those "
        "already translated — are sent to the backend. Existing translations are overwritten.\n"
        "Default is off (only blank rows are translated). "
        "Use this when existing translations are outdated or inconsistent and you want a "
        "completely fresh pass.",
    ),
    (
        "Phase 3 — Translate",
        "The live feed shows 'Reused from file' — what does that mean?",
        "The row's label text matched an already-translated label elsewhere in the same file. "
        "The existing translation was reused directly — no API call was made. "
        "This is controlled by the 'Use in-file translations' toggle in the Translation menu.",
    ),
    (
        "Phase 3 — Translate",
        "Why is translation not starting?",
        "Check that a document is loaded (complete Phase 1-2 or click Load .xlsx). "
        "Also verify the backend is ready in Edit → Settings — if using a paid backend "
        "(DeepL/Azure/OpenAI) an API key is required.",
    ),
    (
        "Phase 3 — Translate",
        "What does Trans/TM/Dedup mean in the live feed?",
        "Trans = row was sent to the translation API and translated. "
        "TM = row was found in the Translation Memory cache from a previous run — no API call made. "
        "Dedup = the same label appeared multiple times; translated once and reused for duplicates.",
    ),
    (
        "Phase 3 — Translate",
        "What is the Translation Memory (TM)?",
        "The TM is a local SQLite database that caches every successful translation. "
        "On future runs, rows with identical source text are reused from the cache — "
        "no API call, no quota consumed, and much faster. "
        "Configure the TM path in Edit → Settings → Resources.",
    ),
    (
        "Phase 3 — Translate",
        "What does Dedup mean?",
        "Deduplication: within a single run, if the same source label appears in multiple rows, "
        "it is translated only once. All duplicate rows are filled with the same result. "
        "This reduces API calls significantly for large Salesforce orgs.",
    ),
    (
        "Phase 3 — Translate",
        "Translation is slow — how do I speed it up?",
        "Increase Workers in Edit → Settings (try 8). Switch to a paid backend like DeepL or Azure "
        "which have higher rate limits. Make sure Translation Memory is enabled so repeated "
        "translations are served from cache.",
    ),
    (
        "Phase 3 — Translate",
        "I get 429 Too Many Requests errors.",
        "Google's free tier is aggressively rate-limited. Try reducing Workers to 1-2 in "
        "Edit → Settings. Wait a minute and try again. For production use, switch to a paid "
        "backend (DeepL, Azure Translator, or OpenAI) in Edit → Settings.",
    ),
    (
        "Phase 3 — Translate",
        "How do I use DeepL, Azure, or OpenAI instead of Google?",
        "Open Edit → Settings → Translation. Choose the backend from the dropdown and enter "
        "your API key. The app validates the key before starting. "
        "Set rate limit to 0 (unlimited) for paid backends.",
    ),
    (
        "Phase 3 — Translate",
        "Can I resume a translation that was interrupted?",
        "Yes. The checkpoint feature saves progress after each row. If you cancel or the app "
        "crashes, restarting will continue from where it left off. "
        "Click 'Clear progress' to start fresh instead of resuming.",
    ),
    (
        "Phase 3 — Translate",
        "What happens when I cancel a running translation?",
        "A choice dialog appears with two options:\n"
        "- 'Finish in-flight rows' — waits for active API requests to complete, then stops cleanly. "
        "Progress is checkpointed so you can resume later.\n"
        "- 'Stop immediately' — disconnects all signals and halts instantly with no further progress "
        "updates. Use this if you need to stop urgently.\n"
        "In both cases, rows already translated are preserved.",
    ),
    (
        "Phase 3 — Translate",
        "What is the 'Clear progress' button?",
        "The 'Clear progress' button deletes any saved checkpoint/resume data for the current file. "
        "Use it when you want to start translation completely fresh instead of resuming from where "
        "a previous run left off.",
    ),
    (
        "Phase 3 — Translate",
        "What happens when the API fails for a specific row?",
        "If a row fails all retries, the app applies a 'fallback to original' strategy: the translation "
        "field is filled with the source label text (not left blank). This ensures no rows end up with "
        "empty translations. The row is counted under 'Rows failed' in the final summary.",
    ),
    (
        "Phase 3 — Translate",
        "What does the translation summary show when complete?",
        "After translation finishes, the live feed shows a structured summary:\n"
        "- 'Rows processed successfully' — total rows that have a valid translation, with a tree "
        "breakdown showing how each was obtained (API, Translation Memory, fuzzy match, dedup, "
        "imported file, already-translated kept as-is).\n"
        "- 'Rows failed' — rows where the API failed and fallback was applied.\n"
        "- Elapsed time and translation rate (rows/second).",
    ),
    (
        "Phase 3 — Translate",
        "What is fuzzy matching in the Translation Memory?",
        "Fuzzy matching finds similar (but not identical) source strings in the TM. "
        "For example 'Save record' may fuzzy-match 'Save Record'. "
        "Configure the threshold and auto-accept score in Edit → Settings → Resources.",
    ),
    (
        "Phase 3 — Translate",
        "How do I reuse translations from a previously translated Excel file?",
        "Click 'Import existing translations...' and select the Excel. "
        "Imported translations are applied with highest priority — before the TM and before "
        "the API. Check 'Use imports' to enable them.",
    ),
    (
        "Phase 3 — Translate",
        "Can I translate only certain component types?",
        "Yes. Click 'Filter Components...' to select which types to include. "
        "The estimate next to the button shows how many rows will be translated.",
    ),
    # -- Phase 4 --
    (
        "Phase 4 — Review",
        "How do I edit a translation?",
        "Click a row in the table to select it. The source label and translation appear in the "
        "editor pane below. Edit the translation text and click Apply (or press Ctrl+Enter).",
    ),
    (
        "Phase 4 — Review",
        "How do I undo an edit?",
        "Press Ctrl+Z to undo the last translation edit. Press Ctrl+Y to redo. "
        "The Edit menu also has Undo/Redo entries.",
    ),
    (
        "Phase 4 — Review",
        "How do I find and replace text across all translations?",
        "Press Ctrl+H or click Edit → Find & Replace. Enter find and replace text, "
        "choose options (case sensitive, regex), and click Replace All. "
        "All replacements are undoable with Ctrl+Z.",
    ),
    (
        "Phase 4 — Review",
        "What does the Approved column do?",
        "Marking a row as Approved means it has been reviewed and accepted. "
        "Approved rows are skipped during Phase 5 validation checks (they are trusted). "
        "Use the Status filter to show only Approved rows.",
    ),
    (
        "Phase 4 — Review",
        "How do I filter the table?",
        "Use the Component dropdown to filter by component type, the Status dropdown to filter "
        "by Translated/Untranslated/Approved, and the search box to filter by key or label text. "
        "Right-click a column header to filter by specific values (like Excel auto-filter).",
    ),
    (
        "Phase 4 — Review",
        "I edited the Excel externally. How do I bring it back?",
        "Click 'Load reviewed Excel...' at the top of Phase 4. The uploaded workbook replaces "
        "the in-memory document and becomes the active version for all subsequent phases.",
    ),
    # -- Phase 5 --
    (
        "Phase 5 — Validate & Fix",
        "What does Auto-fix all do?",
        "It runs deterministic fixers over all flagged rows: restores missing placeholders "
        "({!Foo}, {0}, etc.), truncates translations that exceed Salesforce length limits, "
        "clears whitespace-only translations, removes duplicate keys, and restores missing "
        "HTML tag pairs.",
    ),
    (
        "Phase 5 — Validate & Fix",
        "What are the validation categories?",
        "duplicate_key: the same key appears more than once. "
        "length_limit: translation exceeds Salesforce's character limit for this component. "
        "token_drift: a placeholder ({!Name}, {0}) is in the source but missing from the translation. "
        "html_mismatch: the HTML tag structure differs between source and translation. "
        "empty_translation: the translation is blank or whitespace-only.",
    ),
    (
        "Phase 5 — Validate & Fix",
        "How do I export a validation report?",
        "Click 'Export Report' in Phase 5. Choose CSV (for spreadsheets), "
        "JSON (for programmatic use), or HTML (for sharing in a browser).",
    ),
    (
        "Phase 5 — Validate & Fix",
        "A row keeps failing validation even after auto-fix.",
        "Some issues require manual attention. Double-click the row (or click 'Jump to Phase 4') "
        "to open it in the editor with full context. The auto-fixer notes why it could not help "
        "in the message column.",
    ),
    # -- Phase 6 --
    (
        "Phase 6 — Export STF",
        "How many STF files does the export produce?",
        "Three files: Bilingual_<code>.stf (full bilingual file), "
        "Translated_<code>.stf (translated rows only), "
        "Untranslated_<code>.stf (untranslated rows only). "
        "All are UTF-8 with LF line endings, compatible with Salesforce Translation Workbench.",
    ),
    (
        "Phase 6 — Export STF",
        "Can I convert a hand-translated Excel directly to STF without using earlier phases?",
        "Yes. Open Phase 6 from the sidebar, click 'Load translated Excel...', select your "
        "workbook, set the language and code, then click Export.",
    ),
    # -- Settings --
    (
        "Settings",
        "Where do I set my DeepL / Azure / OpenAI API key?",
        "Edit → Settings → Translation tab. Enter the key in the API key field. "
        "The app uses the OS credential store (keyring) to save it securely — "
        "it is never stored in plaintext.",
    ),
    (
        "Settings",
        "What does session persistence do?",
        "When enabled (Edit → Settings → Resources → Session), the app saves your current "
        "project state (document, phase progress, translations) when you close it. "
        "Next time you open the same STF file, it offers to restore where you left off.",
    ),
    (
        "Settings",
        "How do I reset the app completely?",
        "File → Reset Session clears all loaded documents, paths, phase statuses, "
        "undo history, and imported translations. The app returns to a blank Phase 1.",
    ),
    (
        "Settings",
        "How do I reset only the current phase?",
        "File → Reset Current Phase resets the current phase and all downstream phases, "
        "without clearing Phase 1-2 data.",
    ),
    # -- Glossary --
    (
        "Glossary",
        "What is the glossary for?",
        "The glossary (Edit → Settings → Resources) is a CSV file with three columns: "
        "source, target, do_not_translate. "
        "Use do_not_translate=true to protect brand names (Bayer, ATLS, etc.) from being changed. "
        "Use target to force a specific translation for a term.",
    ),
    (
        "Glossary",
        "What format should the glossary CSV be?",
        "Three columns: source, target, do_not_translate. Example rows:\n"
        "  Bayer,,true  (protects 'Bayer' from translation)\n"
        "  case,ケース,   (forces 'case' to always translate to 'ケース')",
    ),
    # -- Troubleshooting --
    (
        "Troubleshooting",
        "The app crashes immediately on Windows with no error.",
        "Check %TEMP%\\stx_crash.log for the error message. "
        "Common causes: missing libGL.so / Visual C++ runtime, or a pip install failure. "
        "Delete .venv and re-run launch.bat to reinstall.",
    ),
    (
        "Troubleshooting",
        "I get 'libGL.so.1: cannot open shared object file' on Linux.",
        "Install Qt runtime libraries:\n"
        "  Debian/Ubuntu: sudo apt install libgl1 libegl1 libxkbcommon0 libdbus-1-3\n"
        "  Fedora/RHEL: sudo dnf install mesa-libGL mesa-libEGL libxkbcommon",
    ),
    (
        "Troubleshooting",
        "Salesforce import fails with 'duplicate key'.",
        "Run Phase 5 Validate & Fix and click Auto-fix all. The deduplicator removes earlier "
        "occurrences of duplicated keys (keeping the last, which matches Salesforce behaviour).",
    ),
    (
        "Troubleshooting",
        "A translation lost a placeholder like {!User.Name}.",
        "Phase 5 flags this as token_drift. Click Auto-fix this row to restore the placeholder. "
        "If it persists, open the row in Phase 4 and add the placeholder back manually.",
    ),
    (
        "Troubleshooting",
        "The window opens larger than my screen.",
        "The app clamps itself to your available screen size on launch. If it still overflows, "
        "drag the window edge to resize, or use the View menu to switch themes which triggers a "
        "re-layout. Pop-out dialogs also center on screen.",
    ),
    (
        "Troubleshooting",
        "Translation worked but the resulting STF causes Salesforce errors.",
        "Check Phase 5 first — run validation and fix any errors. The most common causes are "
        "duplicate keys, missing placeholders, and HTML mismatches.",
    ),
    # -- Keyboard shortcuts --
    (
        "Keyboard shortcuts",
        "What are the keyboard shortcuts?",
        "Ctrl+0..5: Jump to Phase 1-6\n"
        "Ctrl+O: Open file\n"
        "Ctrl+S: Save current phase\n"
        "Ctrl+Z / Ctrl+Y: Undo / Redo (Phase 4 per-edit)\n"
        "Ctrl+Shift+Z / Ctrl+Shift+Y: App-wide Undo / Redo (major actions)\n"
        "Ctrl+H: Find & Replace (Phase 4)\n"
        "Ctrl+B: Previous phase\n"
        "Ctrl+,: Settings\n"
        "Ctrl+L: Toggle status log\n"
        "F1: User Guide\n"
        "Ctrl+Q: Quit",
    ),
]


class FaqDialog(QDialog):
    """Searchable FAQ dialog."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Frequently Asked Questions")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        clamp_to_screen(self, 800, 700)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Search bar
        search_row = QHBoxLayout()
        search_icon = QLabel("\U0001f50d")
        search_icon.setStyleSheet("font-size: 16px;")
        search_row.addWidget(search_icon)
        self._search = QLineEdit()
        self._search.setPlaceholderText(
            "Search questions and answers... (e.g. 'translation memory', 'duplicate key')"
        )
        self._search.setMinimumHeight(34)
        self._search.textChanged.connect(self._apply_filter)
        search_row.addWidget(self._search, stretch=1)
        layout.addLayout(search_row)

        self._count_label = QLabel(f"{len(_FAQ)} questions")
        self._count_label.setStyleSheet("color: #64748b; font-size: 11px;")
        layout.addWidget(self._count_label)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        self._container = QWidget()
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setSpacing(4)
        self._container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self._container)
        layout.addWidget(scroll, stretch=1)

        # Build FAQ items
        self._items: list[tuple[str, str, str, QWidget]] = []
        current_category = None

        for category, question, answer in _FAQ:
            if category != current_category:
                current_category = category
                cat_lbl = QLabel(category)
                cat_lbl.setStyleSheet(
                    "font-size: 13px; font-weight: 700; color: #1e3a5f; "
                    "padding: 12px 0 4px 0;"
                )
                self._container_layout.addWidget(cat_lbl)

            item_widget = self._make_item(question, answer)
            self._container_layout.addWidget(item_widget)
            self._items.append((category, question, answer, item_widget))

        self._container_layout.addStretch(1)

    def _make_item(self, question: str, answer: str) -> QWidget:
        """Build a single collapsible FAQ item."""
        widget = QWidget()
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        vbox = QVBoxLayout(widget)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # Question row (click to expand)
        q_btn = QPushButton(f"  Q: {question}")
        q_btn.setStyleSheet(
            "QPushButton { text-align: left; font-weight: 600; font-size: 12px; "
            "padding: 8px 12px; border: 1px solid #e2e8f0; border-radius: 4px; "
            "background: #f8fafc; color: #1e293b; } "
            "QPushButton:hover { background: #e0e7ff; border-color: #6366f1; } "
            "QPushButton:checked { background: #eef2ff; border-color: #6366f1; }"
        )
        q_btn.setCheckable(True)
        q_btn.setChecked(False)
        q_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        # Answer label (hidden by default)
        a_lbl = QLabel(answer)
        a_lbl.setWordWrap(True)
        a_lbl.setStyleSheet(
            "padding: 8px 16px 12px 20px; color: #374151; font-size: 12px; "
            "background: #fafafa; border: 1px solid #e2e8f0; "
            "border-top: none; border-radius: 0 0 4px 4px;"
        )
        a_lbl.setTextFormat(Qt.TextFormat.PlainText)
        a_lbl.setVisible(False)
        a_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        def _toggle(checked: bool, lbl=a_lbl, btn=q_btn) -> None:
            lbl.setVisible(checked)
            icon = "▲" if checked else "▶"
            text = btn.text()
            # Update the leading icon
            if text.startswith("  ▲") or text.startswith("  ▶"):
                btn.setText(f"  {icon}" + text[3:])
            else:
                btn.setText(f"  {icon}" + text[2:])

        q_btn.toggled.connect(_toggle)
        # Set initial icon
        q_btn.setText(f"  ▶ {question}")

        vbox.addWidget(q_btn)
        vbox.addWidget(a_lbl)
        widget._q_btn = q_btn  # type: ignore[attr-defined]
        widget._a_lbl = a_lbl  # type: ignore[attr-defined]
        return widget

    def _apply_filter(self, text: str) -> None:
        """Show/hide FAQ items based on search text — with synonym matching."""
        needle = text.strip().lower()
        visible_count = 0

        # Synonym / keyword expansion — maps common user terms to canonical search words
        _SYNONYMS: dict[str, list[str]] = {
            "slow": ["speed", "performance", "rate limit", "workers", "429", "quota"],
            "fast": ["speed", "performance", "workers"],
            "speed": ["workers", "rate limit", "dedup", "tm", "cache"],
            "error": ["fail", "crash", "not working", "issue", "problem"],
            "crash": ["error", "fail", "close", "stx_crash"],
            "api": ["key", "backend", "deepl", "azure", "openai", "google"],
            "key": ["api", "backend", "deepl", "azure", "openai", "secret"],
            "backend": ["google", "deepl", "azure", "openai", "translator"],
            "cache": ["tm", "translation memory", "dedup", "reuse"],
            "dedup": ["duplicate", "same label", "repeat", "reuse"],
            "reuse": ["dedup", "cache", "tm", "infile", "existing"],
            "existing": ["reuse", "keep", "mixed", "already translated"],
            "mixed": ["existing", "partial", "some translated", "untranslated"],
            "approved": ["review", "mark", "accept", "validate"],
            "undo": ["undo", "revert", "ctrl+z", "ctrl z"],
            "find": ["find", "replace", "search", "ctrl+h"],
            "replace": ["find", "replace", "bulk", "global"],
            "export": ["stf", "output", "save", "write", "download"],
            "import": ["load", "upload", "open", "bring in"],
            "validate": ["check", "error", "warning", "fix", "issue"],
            "install": ["setup", "launch", "run", "start"],
            "update": ["upgrade", "latest", "git pull", "new version"],
            "glossary": ["brand", "term", "do not translate", "dnt", "forced"],
            "shortcut": ["keyboard", "ctrl", "hotkey", "key combination"],
            "phase": ["step", "stage", "workflow", "pipeline"],
            "session": ["save", "restore", "resume", "persist"],
            "reset": ["clear", "start over", "fresh", "clean"],
            "cancel": ["stop", "abort", "interrupt", "finish in-flight"],
            "summary": ["done", "complete", "finished", "result", "report", "total"],
            "fallback": ["fail", "error", "blank", "original", "source"],
            "progress": ["checkpoint", "resume", "clear", "restart"],
        }

        # Expand the needle with synonyms
        expanded_terms = {needle}
        for keyword, synonyms in _SYNONYMS.items():
            if keyword in needle:
                expanded_terms.update(synonyms)
            for syn in synonyms:
                if syn in needle:
                    expanded_terms.add(keyword)
                    expanded_terms.update(synonyms)

        cat_visible: dict[str, bool] = {}

        for category, question, answer, widget in self._items:
            if not needle:
                widget.setVisible(True)
                cat_visible[category] = True
                visible_count += 1
            else:
                # Check if any expanded term matches question, answer, or category
                haystack = f"{question} {answer} {category}".lower()
                matches = any(term in haystack for term in expanded_terms if term)
                widget.setVisible(matches)
                if matches:
                    widget._q_btn.setChecked(True)  # type: ignore[attr-defined]
                    cat_visible[category] = True
                    visible_count += 1

        # Update category header visibility
        for i in range(self._container_layout.count()):
            item = self._container_layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if isinstance(w, QLabel) and not hasattr(w, '_q_btn'):
                    cat_name = w.text()
                    w.setVisible(cat_visible.get(cat_name, False))

        # Collapse all when search cleared
        if not needle:
            for _cat, _q, _a, widget in self._items:
                widget._q_btn.setChecked(False)  # type: ignore[attr-defined]

        self._count_label.setText(
            f"{visible_count} of {len(_FAQ)} questions"
            if needle else f"{len(_FAQ)} questions"
        )


# Avoid importing QPushButton at top level to keep the import order clean
from PySide6.QtWidgets import QPushButton  # noqa: E402
