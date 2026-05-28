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
