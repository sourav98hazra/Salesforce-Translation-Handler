# Salesforce Translation Handler

A professional cross-platform desktop application for the Salesforce
Translation Workbench (STF) workflow:

```
  Salesforce STF  ─►  Organized Excel  ─►  Auto-Translate  ─►  Review  ─►  STF
```

Every phase produces a downloadable artifact (`.xlsx` or `.stf`) so you
can verify the output independently of the GUI, and re-enter the
workflow at any phase by loading a saved file.

The output formats are **byte-compatible** with the legacy
`stftoexcel_v2.ps1`, `translate_excel_fixed.py`, and `ExcelToSTFV2.ps1`
scripts that the application replaces — so existing tooling and
Salesforce import behaviour are unchanged.

---

## Why this exists

The previous workflow required two scripting languages (PowerShell +
Python), interactive prompts, manual file shuffling between phases, and
no validation before Salesforce import. This application unifies the
pipeline under one Python codebase with three usable surfaces:

| Surface | Audience | Use when |
|---|---|---|
| **Desktop GUI** (`stx-app`) | Translators / reviewers | You want a guided wizard with save points |
| **CLI** (`stx`) | Developers / CI | You want to script the pipeline |
| **Library** (`import stx`) | Other Python tools | You want to embed the pipeline |

---

## What it protects from corruption

Translators happily mangle anything that looks like text. This app
shields the following from translation:

- **Translation Workbench placeholders**  `{!$Label.Foo}`, `{!Record.Id}`
- **Apex MessageFormat tokens**            `{0}`, `{1}`, `{name}`
- **Salesforce record IDs**                15- and 18-character base-62 IDs
- **URLs**                                  `https://help.salesforce.com/...`
- **Email addresses**                       `support@example.com`
- **ALL-CAPS acronyms**                     `API`, `URL`, `WO`, etc.
- **Literal escape sequences**              `\n`, `\t`, `\r` in label values
- **HTML tags & attributes**                rich-text fields are walked tag-by-tag

Plus a **token-loss check** that rolls a row back to its source label if
the translator drops a sentinel mid-flight.

## What it validates before you ship

Phase 5 runs a structured validation report that flags:

- **Duplicate keys** that would cause Salesforce import failures
- **Length-limit violations** per component type
- **Token drift** — placeholders or message-format tokens missing in the translation
- **HTML mismatch** — tag structure differs between source and translation
- **Empty/whitespace-only translations** that would re-import as untranslated
- **Excel formula injection** — labels starting with `=`, `+`, `-`, `@` are guarded on export

---

## Installation

### Prerequisites

- **Python 3.9 or newer** (3.11+ recommended).
  Check with `python --version` (Linux/Mac) or `py --version` (Windows).
- An internet connection for the auto-translate phase.

### 1. Clone the repository

```bash
git clone https://github.com/sourav98hazra/Salesforce-Translation-Handler.git
cd Salesforce-Translation-Handler
```

### 2. Create a virtual environment (recommended)

#### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
```

#### Windows (PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install

#### Full install (GUI + CLI + library)

```bash
pip install -e ".[gui]"
```

#### CLI / library only (skip the PySide6 download)

```bash
pip install -e .
```

#### Developer install (adds tests + linters)

```bash
pip install -e ".[gui,dev]"
```

After install, two commands appear on your `PATH`:

| Command | Purpose |
|---|---|
| `stx`     | Command line interface |
| `stx-app` | Launch the desktop GUI |

---

## Running the desktop GUI

There are three ways to launch the app — pick whichever fits your situation:

### Option 1: Double-click launcher (easiest, after `pip install`)

After running `pip install -e ".[gui]"` once, just **double-click** the launcher for your OS in the project folder:

| OS | File to double-click | Notes |
|---|---|---|
| **Windows** | `launch.bat` | Auto-creates the venv on first run if needed |
| **macOS**   | `launch.command` | Right-click → Open the first time (Gatekeeper) |
| **Linux**   | `launch.sh` | Run `chmod +x launch.sh` once, then double-click in your file manager |

These launchers detect the virtual environment, set it up automatically on first run if it doesn't exist, then start the GUI. They're safe to commit / share with non-technical users — they handle the install for them.

For Linux desktop integration, the included `SalesforceTranslationHandler.desktop` file can be copied to `~/.local/share/applications/` after editing the `Exec=` path, giving you a Start Menu / launcher entry.

### Option 2: Standalone executable (no Python needed on target machine)

For distributing to non-technical users who don't have Python at all, build a single self-contained binary:

```bash
pip install -e ".[gui]" pyinstaller
python build_exe.py
```

This produces:

| OS | Output |
|---|---|
| Windows | `dist\SalesforceTranslationHandler.exe` |
| macOS   | `dist/SalesforceTranslationHandler.app` |
| Linux   | `dist/SalesforceTranslationHandler` (ELF binary) |

The artifact is fully self-contained (~65MB on Linux): it bundles Python, all dependencies, and the application. End users just **double-click and go** — no installation, no Python, no terminal. PyInstaller does not cross-compile, so build on the OS you intend to ship to.

### Option 3: Terminal command

```bash
stx-app
```

(or `stx gui` — both launch the same window.)

The window has five phases in the left sidebar; each one writes its own
artifact to disk so you can independently verify it:

| Phase | Action | Saved artifact |
|---|---|---|
| 1. Import STF | Pick the source `.stf` file | (a copy of the parsed STF, on demand) |
| 2. STF → Excel | Convert to organised workbook | `*_organized.xlsx` |
| 3. Translate | Auto-translate untranslated rows | `*_translated.xlsx` (with audit sheets) |
| 4. Review | Inline edit translations with filters | `*_reviewed.xlsx` |
| 5. Export STF | Validate + emit final files | `Super_STF_<code>.stf` + 2 more |

Every phase has a **Load existing ...** button so you can re-enter the
workflow from any saved artifact (e.g. drop in an Excel a colleague
edited externally and continue from phase 4).

---

## Running from the command line

The CLI mirrors every GUI phase and adds a `run` command for end-to-end
automation:

```bash
# Quick metadata check
stx info input.stf

# Phase 1+2: STF → organised Excel
stx stf2xlsx input.stf organized.xlsx

# Phase 3: translate the organised Excel
stx translate organized.xlsx translated.xlsx --source en --target ja

# Phase 5: Excel → 3 STF files
stx xlsx2stf reviewed.xlsx ./out --language Japanese --code ja

# Pre-export validation report
stx validate reviewed.xlsx --code ja

# Full pipeline in one go
stx run input.stf ./out --target ja --language Japanese

# Round-trip test (no translation calls)
stx run input.stf ./out --skip-translation
```

Run `stx --help` (or `stx <command> --help`) for the full reference.

---

## Output file conventions

### Excel workbook layout

| Sheet | Contents |
|---|---|
| `<ComponentType>_<Status>` | One per group; columns: `Key`, `Label`, `Translation` |
| `Content Details` | Index of every component sheet |
| `Translation_Summary` | Per-sheet counts (after phase 3) |
| `Translation_Status_Log` | Per-row status (after phase 3) |

### STF files (phase 5)

Three files per export, all UTF-8 with LF line endings (no BOM):

| File | Contents |
|---|---|
| `Super_STF_<code>.stf`         | Bilingual full file (translated + untranslated sections) |
| `TranslatedOnly_STF_<code>.stf` | Translated rows only |
| `UntranslatedOnly_STF_<code>.stf` | Untranslated rows only |

The section separators (`------------------TRANSLATED-------------------`
and `------------------OUTDATED AND UNTRANSLATED-----------------`) are
reproduced character-for-character to preserve compatibility with any
downstream tooling.

---

## Project layout

```
Salesforce-Translation-Handler/
├── src/stx/                          # Core library + GUI + CLI
│   ├── model.py                      # Document / Entry data classes
│   ├── languages.py                  # Salesforce ↔ Google language codes
│   ├── stf/{parser.py, writer.py}    # STF parse + write
│   ├── excel/{exporter.py, importer.py}
│   ├── translate/                    # Translator backends
│   │   ├── protect.py                # Token protection (IDs, URLs, ...)
│   │   ├── google_free.py            # Default backend
│   │   └── runner.py                 # Document-level translation
│   ├── validate.py                   # Pre-export checks
│   ├── cli.py                        # Typer-based CLI
│   └── gui/                          # PySide6 desktop app
│       ├── app.py
│       ├── main_window.py
│       ├── workers.py                # QThread wrappers
│       └── pages/                    # One module per phase
├── tests/                            # Pytest test suite
├── pyproject.toml
├── README.md
├── launcher.py                       # PyInstaller / OS launcher entry-point
├── launch.bat                        # Windows double-click launcher
├── launch.command                    # macOS double-click launcher
├── launch.sh                         # Linux double-click launcher
├── SalesforceTranslationHandler.desktop  # Linux desktop entry
├── build_exe.py                      # PyInstaller standalone-binary builder
└── (legacy scripts kept for reference)
    ├── stftoexcel_v2.ps1
    ├── translate_excel_fixed.py
    └── ExcelToSTFV2.ps1
```

---

## Running the test suite

```bash
pip install -e ".[dev]"
pytest -q
```

The tests cover STF parse/write round-trips, Excel import/export
round-trips, every category of token protection, validation rules, and
formula-injection safety.

---

## Troubleshooting

### `stx-app` reports `libGL.so.1: cannot open shared object file`

You're on a minimal Linux install without the system libraries Qt
needs. Install them:

| Distribution | Command |
|---|---|
| Debian / Ubuntu | `sudo apt install libgl1 libegl1 libxkbcommon0 libdbus-1-3` |
| Amazon Linux / RHEL / Fedora | `sudo dnf install mesa-libGL mesa-libEGL libxkbcommon` |

### Translation calls hang or 429-error

Google's free tier rate-limits aggressively. The translator backs off
exponentially and falls back to the source label after retries are
exhausted. For high-volume runs, plug in a paid backend (DeepL, Azure,
OpenAI) by implementing the `stx.translate.Translator` protocol and
selecting it via the GUI's Backend dropdown (next release will surface
this; the protocol exists today).

### Excel rejects sheet names with special characters

The exporter sanitises Excel-forbidden characters (`: \ / ? * [ ]`) and
truncates to 31 chars with numeric suffixes on collision, so this
should never happen. If it does, file a bug with the input STF.

### "Salesforce import failed: duplicate key"

Run `stx validate input.stf` to enumerate them. They are pre-existing
duplicates in the export from Translation Workbench; deduplicate them
before import (the validator surfaces all of them with their keys).

---

## Legacy scripts

The original PowerShell + Python scripts (`stftoexcel_v2.ps1`,
`translate_excel_fixed.py`, `ExcelToSTFV2.ps1`) are retained at the repo
root for reference. The new application produces output that those
scripts can still consume, and vice versa.

---

## License

MIT



---

# v1.1 -- Improvements

The `feat/v1.1-improvements` branch adds the following on top of the v1.0 MVP. None of v1.0 is broken; every existing CLI command and GUI page continues to work.

## New core features

### 1. Component selection + persistent key list (Phase 3)

In Phase 3 (Translate), a "Components to translate" panel lists every component type in the loaded document with checkboxes (default: all selected). Below it, "Include" and "Exclude" text areas accept exact keys or glob patterns (`CustomLabel.*`, `*.HelpText`).

The full filter set is saved to a JSON file (`.stxscope.json`) and can be auto-discovered next to the source STF. This implements both:

- "select which components to ultimately translate, all selected by default"
- "store a list of keys somewhere which should be translated"

CLI:

```bash
# Build a scope file from a source document
stx scope new input.stf my-scope.stxscope.json --components CustomLabel,ButtonOrLink --exclude '*.HelpText'

# Use it during translation
stx translate organized.xlsx translated.xlsx --target ja --scope-file my-scope.stxscope.json
```

### 2. Translation Memory (SQLite cache)

Every successful `(source, source_lang, target_lang) -> translation` triple is cached. Subsequent runs skip the network entirely for known sources -- saves time, avoids rate limits, produces identical translations across reviews.

Default location: `~/.cache/salesforce-translation-handler/tm.sqlite`. The Phase 3 panel shows live stats (entries, hits, file size) and exposes a "Clear cache" button.

CLI:

```bash
stx translate organized.xlsx translated.xlsx --memory-db ./tm.sqlite
```

### 3. Glossary (CSV)

Two rule kinds in one file:

- **Do-not-translate (DNT)** -- term shielded by sentinel; round-trips exactly.
- **Forced translation** -- source term always replaced with the specified translation.

CSV format: `source,target,do_not_translate`.

```csv
source,target,do_not_translate
Bayer,,true
ATLS,,true
case,ケース,
record,レコード,
```

CLI:

```bash
stx translate organized.xlsx translated.xlsx --glossary glossary.csv
```

### 4. In-run deduplication + parallel workers

Repeated source labels (e.g. "Name" / "Created Date" appear in every Salesforce object's field labels) are translated **once** and the result is reused for every duplicate row. Combined with a `ThreadPoolExecutor`, translation throughput improves dramatically.

On the bundled 36245-row sample with `workers=4`, dedup eliminates ~50% of the work; with a warm TM, subsequent runs of the same file finish in seconds instead of minutes.

### 5. Adaptive rate limiting

Token-bucket pacer that grows on every successful call and shrinks on every failure. The free Google tier rate-limits aggressively; the limiter self-tunes to whatever rate the backend tolerates today.

CLI:

```bash
stx translate ... --workers 8 --rate-limit 12.0
```

`--rate-limit 0` disables it (recommended for paid backends).

### 6. Multi-language batch

Translate to multiple target languages in a single command:

```bash
stx run input.stf ./out --target ja --targets fr,de,es
```

Outputs land in `./out/ja/`, `./out/fr/`, `./out/de/`, `./out/es/`.

### 7. Multiple translator backends

Available via `--backend`:

| Key      | Backend                       | API key needed | Env var                  |
|----------|-------------------------------|----------------|--------------------------|
| `google` | Google Translate (free)       | no             | -                        |
| `deepl`  | DeepL                         | yes            | `DEEPL_API_KEY`          |
| `azure`  | Microsoft Azure Translator    | yes            | `AZURE_TRANSLATOR_KEY`   |
| `openai` | OpenAI (GPT)                  | yes            | `OPENAI_API_KEY`         |

```bash
stx backends   # list them
stx translate ... --backend deepl --api-key sk-...
```

### 8. Wake-lock (prevent system sleep during long runs)

Cross-platform: `caffeinate` on macOS, `SetThreadExecutionState` on Windows, `systemd-inhibit` on Linux. The Phase 3 page has a "Prevent system sleep" checkbox (on by default).

Note: this prevents *idle* sleep. Closing a laptop lid still suspends every process -- there is no way around that. Keep the lid open.

### 9. Project files (`.stxproject`)

Save the entire pipeline state -- file paths, target language, backend, scope, glossary, TM -- to a single JSON file you can reopen later or share with a teammate.

```bash
stx project show my-project.stxproject
```

## GUI improvements

### Welcome screen (Phase 0)

Recent files list, quick actions ("Open STF", "Load project", "Load Excel"), and the project description. Drag-and-drop files anywhere in the window.

### Sidebar status badges

Each phase now shows its status as an icon (`▶` running, `✓` done, `⚠` error) next to the label, so the entire pipeline state is visible at a glance.

### Drag-and-drop

Drop an `.stf`, `.xlsx`, or `.stxproject` file anywhere in the window. The app routes you to the appropriate phase automatically.

### Keyboard shortcuts

| Shortcut    | Action                          |
|-------------|---------------------------------|
| `Ctrl+0..5` | Switch to phase N               |
| `Ctrl+O`    | Open file...                    |
| `Ctrl+S`    | Save current phase artifact     |
| `Ctrl+Q`    | Quit                            |

### Theme toggle (View menu)

Light, Dark, and Auto themes. The choice is remembered across sessions.

### Phase 3 enhancements

- **Component scope panel** with Select all / Select none / Invert and per-component count
- **Include / Exclude key list** with glob support, save / load / auto-discover
- **Glossary picker** (CSV)
- **Translation Memory** path + live cache stats + Clear cache
- **Backend picker** (Google / DeepL / Azure / OpenAI) with API-key field
- **Workers** spinner (1-32) and **Rate limit** (req/s)
- **Prevent system sleep** checkbox
- **Live feed** showing the actual EN -> JA pair for each row as it translates
- **ETA + rows/second** in the progress panel
- **Multi-click protection** -- "Start" cannot be triggered twice; "Cancel" is idempotent

### Phase 4 enhancements

- **Side-by-side editor** below the table: when a row is selected, the source label and translation appear in larger multi-line fields with explicit "Apply to row" / "Reset row to source" buttons -- much nicer than editing long HTML strings in a single cell.
- **Jump-to-issue** -- when Phase 5 reports a validation error, double-click it and you land on the offending row in Phase 4 with all filters cleared so the row is guaranteed visible.

### Settings persistence

Window geometry, theme, last target language, last output directory, last-used backend, and recent files are remembered across sessions via QSettings.

## CLI parity

Everything the GUI can do is now mirrored on the CLI:

```bash
# Existing commands gain the new flags
stx translate organized.xlsx translated.xlsx \
    --target ja \
    --backend google \
    --scope-file scope.stxscope.json \
    --glossary glossary.csv \
    --memory-db ./tm.sqlite \
    --workers 8 \
    --rate-limit 12

# Multi-language batch in one run
stx run input.stf ./out --target ja --targets fr,de,es --memory-db ./tm.sqlite

# New subcommands
stx scope new input.stf scope.stxscope.json --components CustomLabel,ButtonOrLink
stx scope show scope.stxscope.json
stx project show my-project.stxproject
stx backends   # list available translator backends
```

## Robustness

- **Single-shot runner guard** -- the runner refuses to be invoked twice on the same instance.
- **Multi-click protection** in the GUI -- "Start" / "Cancel" / "Save" buttons can be clicked rapidly without stacking work.
- **Gap-prevention sweep** -- after every translation run, the runner walks the entries array and ensures every slot has both a final entry and a status entry. The audit log is guaranteed to have one row per source row.
- **Verified on the 36245-row sample**: round-trip preserves every row, scope filter correctly accounts for in-scope vs out-of-scope rows, no rows are ever lost.




---

# v1.2 -- Review, Validate & Fix, and Export refinements

The flow now has **seven phases** (the prior six plus a dedicated *Validate & Fix* between Review and Export):

```
0. Welcome  ->  1. Import STF  ->  2. STF -> Excel  ->  3. Translate  ->
4. Review (browse + edit + re-upload Excel)  ->
5. Validate & Fix (auto-fix errors)  ->
6. Export STF  (or load any Excel and convert directly)
```

## Phase 4 (Review) -- now a translation browser

Review is no longer just an editor: it's the place to **browse the translations** and confirm what's been done, with editing on demand.

* **Translation summary card** at the top with four big counters (Total / Translated / Untranslated / Issues) and a visual progress bar showing translation completeness percentage.
* **Auto-validation on entry** -- a colour-coded banner (green / amber / red) immediately tells you whether the document is ready to export.
* **Re-upload reviewed Excel** -- prominent button at the top.  If you'd rather edit the workbook in Excel itself, do that, then drop the file back in here -- it replaces the in-memory document and becomes the latest version for all subsequent phases.
* **Filter / search / sort** by component type, status, or substring.
* **Side-by-side editor pane** below the table (read-only source on the left, editable translation on the right) -- much nicer than editing long HTML strings inside a single table cell.

## Phase 5 (Validate & Fix) -- a dedicated correction phase

A new phase that focuses *only* on the rows with validation issues, so you don't have to scroll through 36k clean rows to find the broken ones.

* Color-coded banner shows error / warning / clean state.
* The issues table lists every row that triggered a validator -- with severity, category, key, label, current translation, and the specific message.
* **Three auto-fix buttons** powered by the new `stx/autofix.py` module:
  * **Auto-fix all** -- run every safe fixer over every issue.
  * **Auto-fix selected** -- only act on the rows you've selected.
  * **Auto-fix this row** -- fix just the row in the inline editor.
* Inline side-by-side editor for manual corrections.
* Double-click any row to **jump to Phase 4** with full table context.
* **Re-validate** at any time to confirm fixes worked.
* Save a "fixed" workbook (`fixed.xlsx`) at any point.

### What the auto-fixer does

| Fixer | What it does |
|---|---|
| `restore_placeholders` | If `{!Foo}` is in the source but missing from the translation, append it back. |
| `restore_message_format` | Same for `{0}`, `{1}`, `{name}` MessageFormat tokens. |
| `trim_to_length` | If the translation exceeds the Salesforce length limit for its component type, truncate at a word boundary and append `...`. |
| `strip_whitespace_translation` | Whitespace-only translations are cleared so they re-import as untranslated (honest rather than misleading). |
| `restore_html_tags` | Wrap the translation in a missing tag pair when there's exactly one. |
| `deduplicate_keys` | Document-wide -- keep the last occurrence of each duplicate key (Salesforce's own behaviour). |

Every fix is **deterministic and safe**.  Fixers never invent data; if they can't help confidently they return None and the row stays flagged for manual attention.

## Phase 6 (Export STF) -- now also a "direct convert" entry point

Export already worked from earlier-phase output.  v1.2 adds a **Load translated Excel** button at the top so users with an externally translated workbook can convert it to STF in one click without going through Phases 1-5.

* If you went through earlier phases, the document is already in memory -- just pick language / output dir and Export.
* If you have your own translated Excel, click **Load translated Excel...**, pick language / output dir, and Export.  No validation is forced -- the app trusts that you've validated yourself (with a tooltip reminder pointing at Phase 5 if you want to check).
* Optional **Run validation** button shows issues but never blocks export -- it's purely advisory at this stage.

## Updated keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+0` | Welcome |
| `Ctrl+1` | Import STF |
| `Ctrl+2` | STF -> Excel |
| `Ctrl+3` | Translate |
| `Ctrl+4` | Review |
| `Ctrl+5` | Validate & Fix |
| `Ctrl+6` | Export STF |
| `Ctrl+O` | Open file |
| `Ctrl+S` | Save current phase artifact |
| `Ctrl+Q` | Quit |



---

# v1.3 -- UI simplification + every phase is independent

This release is about **less, not more**.

## What changed

* **Welcome page is gone.**  The app now opens directly on Phase 1.  Recent files live under `File -> Recent files` only.
* **`.stxproject` files are gone.**  The translation memory + `Recent files` menu cover the same "resume where I left off" need without an extra concept.
* **Six phases instead of seven.**  Numbered 1-6 in the sidebar:
  1. Import STF
  2. STF -> Excel
  3. Translate
  4. Review
  5. Validate & Fix
  6. Export STF
* **Every phase works independently.**  Each one has both:
  * A **"Continue to Phase N+1 ->"** button at the bottom for the end-to-end flow.
  * A **"Load ..."** button so a user can jump straight to that phase with their own file (e.g. open Phase 6 directly with a translated Excel and just convert to STF).
* **Phase 3 (Translate) is dramatically slimmer.**  It now asks only what a translator actually needs to answer: target language, which components, where to save, start.  Backend / API key / workers / rate limit / wake-lock / glossary path / TM path / batch targets all moved into the **Settings dialog** (`Edit -> Settings...` or `Ctrl+,`).
* **Phase 4 (Review) is a translation browser.**  Compact toolbar at the top (status pill + counters + Load Excel), filter row, big table, slim inline editor.  Auto-validates on entry.
* **Phase 5 (Validate & Fix) trimmed to 4 action buttons** (Load Excel / Re-validate / Auto-fix all / Save).  Per-row auto-fix is in the inline editor where it belongs.
* **Phase 2 (STF -> Excel) gained a "Save copy to..."** secondary button so you can write an additional copy elsewhere without disturbing the path the rest of the pipeline uses.
* **New theme.**  Soft cool-grey background with a polished indigo accent -- no more stark white.  Light / dark / auto via `View -> ... theme`, persisted across sessions.
* **`Help -> User guide` (F1)** opens [`USER_GUIDE.md`](./USER_GUIDE.md) with the full walkthrough.

## End-to-end vs independent flow

You can use the app two ways and they're equally first-class:

| Path | When to use it | How |
|---|---|---|
| End-to-end | Fresh STF, want to walk through everything | Click **Continue to Phase N ->** at the bottom of each phase |
| Independent per phase | Already have a workbook from a colleague / external source / earlier run | Click the phase in the sidebar, then **Load ...** |

The `USER_GUIDE.md` documents every common workflow.

