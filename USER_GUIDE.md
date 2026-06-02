# Salesforce Translation Manager — User Guide

A practical, end-to-end walkthrough of the desktop application.

---

## 1. Install and launch

### Quickest way

| OS | What to do |
|---|---|
| Windows | Double-click `setup_desktop_app.bat` (first time), then use the desktop shortcut |
| macOS | Double-click `launch.command` |
| Linux | Double-click `launch.sh` (run `chmod +x launch.sh` once first) |

Everything is automatic -- the launcher creates a virtual environment, installs dependencies, and starts the app on first run. Subsequent launches are instant.

### Prerequisites

- **Python 3.9+** must be installed ([python.org](https://www.python.org/downloads/)).
  On Windows, tick "Add Python to PATH" during installation.

### Alternative launch methods

| Method | When to use |
|---|---|
| `stx-app` from terminal | You already ran `pip install -e ".[gui]"` and prefer the command line |
| `stx gui` from terminal | Same as above (alias) |
| Desktop shortcut (Windows) | Created automatically by `setup_desktop_app.bat` |
| Standalone `.exe` / `.app` | Distributing to users without Python -- see [README.md](./README.md) |

Full installation options (pip install, developer setup, standalone builds) are in [`README.md`](./README.md).

### The sidebar

The sidebar on the left shows:

- The **app logo** (a hexagonal "STM" icon) beside the full title **"Salesforce Translation Manager"**.
- The six phase buttons with status badges (`✓` done, `▶` running, `⚠` error).
- Below the phases: **document stats** (total / translated / untranslated rows), the **target language**, and a **mini progress bar** (visible during translation).

The **Status log** at the bottom of the window can be hidden or shown via `View -> Show Status Log` (`Ctrl+L`).

The sidebar is **resizable** (drag its right edge to taste, between roughly 220 and 280 pixels) and the whole window has a sensible minimum (900×600) -- the app starts within your screen size, never wider, even on small laptops or secondary monitors.

---

## 2. Two ways to use the app

You can use the app either as a **guided pipeline** (Phase 1 → Phase 2 → ... → Phase 6) or as **six independent tools** (jump to any phase via the sidebar and load whatever input you have).

| Path | When to use it | How |
|---|---|---|
| **Pipeline (e2e)** | You start from a fresh STF and want to walk through every phase | Click **"Continue to Phase N →"** at the bottom of each phase |
| **Independent** | You already have a partially translated workbook from a colleague, or you only want to validate, or you want to convert a hand-translated Excel directly to STF | Click the phase in the sidebar, then use the **"Load ..."** button to drop your file into that phase |

The sidebar status badges show which phases have been completed (`✓`), are running (`▶`), or hit an error (`⚠`) so you always know where you are.

Drag-and-drop also works: drop an `.stf` or `.xlsx` anywhere in the window and the app routes to the right phase.

### Active workflow context

The app maintains one **active workflow context** at a time. When you load a file in any phase, a workflow begins from that phase. The app tracks both the original source path and the current working artifact, so every subsequent phase uses the correct file automatically.

**Key behaviours:**

- **Continue buttons** pass the same active document forward without reloading.
- If you load a **different file** while a workflow is already active, an **override confirmation dialog** appears asking whether to replace the current workflow.
- If you have **unsaved changes**, you are offered three choices: Save and Override, Discard and Override, or Cancel.
- On override, all stale state is cleared (translation progress, validation reports, audit data, export paths, filters) so downstream phases never mix old data with the new file.
- Cancelling the override leaves the current workflow unchanged.

This prevents accidental data loss and ensures that the export in Phase 6 always matches the file you are actually working with.

---

## 3. The six phases

### Phase 1 — Import STF

**What it does:** parses the source `.stf` file from Salesforce Translation Workbench into an in-memory document.

**How to use:**

1. Click **"Browse STF..."** and pick the `.stf` you exported from Salesforce.
2. Review the **Parsed metadata** grid:
   - **Translation language** — the language this STF translates *into* (e.g. Japanese), read from the STF header. Change via the dropdown if the header is wrong.
   - **Language code** — Salesforce code for the translation language (e.g. `ja`), auto-filled.
   - **Label language** — the language the source labels are written in (usually English). Auto-detected from the label text after parsing; change via the dropdown if incorrect.
   - **Label code** — Salesforce code for the label language, auto-filled from the dropdown.
3. (Optional) Click **"Save copy as STF..."** to write a clean copy to disk.
4. Click **"Continue to Phase 2 →"**.

**Independent path:** drop an `.stf` directly here and parse it; no need to do anything else.

The Preview panel in Phase 1 has a **"Pop out"** button that detaches the preview into an independent window, useful for viewing the parsed content alongside other phases.

### Phase 2 — STF → Organised Excel

**What it does:** groups the parsed rows by component type (`CustomLabel`, `ButtonOrLink`, etc.) into a structured workbook with one sheet per group plus a `Content Details` index sheet.

**How to use:**

1. Click **"Convert"** (the primary button) to generate the organised workbook.  The output is auto-named from the source file and saved in the same folder.
2. (Optional) Click **"Save a Copy..."** to write an additional copy elsewhere.
3. Inspect the **Content Details** preview to confirm the row counts.
4. Click **"Continue to Phase 3 →"**.

**Independent path:** click **"Load existing .xlsx..."** to start from a previously generated workbook.

### Phase 3 — Translate

**What it does:** auto-translates every untranslated row using the configured backend, with Salesforce IDs / placeholders / URLs / emails / HTML protected from modification.

**How to use:**

1. Pick the **Source** and **Target** language (displayed side by side in a compact form at the top).
2. Click **"Filter Components..."** to choose which component types to translate (default: all selected).
3. (Optional) Set translation options via the **Translation menu** in the menu bar — see [Translation menu](#translation-menu) below.
4. Click **"Start translation"**. A **pre-flight confirmation dialog** appears summarising the current options. Review them and click **"Start translation"** to proceed, or **"Cancel — review settings"** to adjust first.
5. Watch the **live feed** below the progress bar. Each line shows inline counters and the translation pair:
   ```
   [42/1000 | Trans:30 TM:5 Dedup:7] EN: Hello -> JA: こんにちは
   ```
   - `Trans` = translated via API, `TM` = from Translation Memory cache (no API call), `Dedup` = duplicate label reused from same run
6. Rows that match an already-translated label **elsewhere in the same file** appear as:
   ```
   [Reused from file] EN: Save -> JA: 保存
   ```
   No API call is made for these — the existing translation is reused directly.
7. When translation completes, a **final summary block** is printed in the live feed.
8. The translated document is held **in memory** — click **"Save a Copy..."** to write it to disk with a professional dated filename.
9. Click **"Continue to Phase 4 →"** when done.

#### Translation menu

The **Translation** menu in the menu bar groups all translation behaviour toggles. Changes take effect on the next run and are persisted between sessions.

| Option | Default | What it does |
|---|---|---|
| Use in-file translations | ✓ On | Before calling the API for an untranslated row, checks if the same label text already has a translation elsewhere in the same STF/Excel file and reuses it without any API call |
| Use Translation Memory cache | ✓ On | Reuses translations from the SQLite TM database (previous runs) |
| Use Fuzzy matching | ✗ Off | Finds approximate matches in the TM (e.g. "Save record" matches "Save Record") |
| Use imported translations | ✗ Off | Applies translations from a separately imported Excel with highest priority |
| Retranslate all (overwrite existing) | ✗ Off | When on, ALL rows including already-translated ones are sent to the backend |

The menu also has a **Settings...** shortcut (Ctrl+,) and a **Re-enable pre-flight confirmation** action.

#### Pre-flight confirmation dialog

Before every translation run a summary dialog shows the active options so you can review them before committing. Tick **"Don't show this dialog again"** to skip it in future runs. Re-enable it via Translation → Re-enable pre-flight confirmation.

#### Filter Components dialog (Phase 3)

Click "Filter Components..." to open the component selection dialog. Use it to:

- **Search**: Type to filter the component list by name (case-insensitive substring match).
- **Status filter**: Choose what kinds of components to show.
- **Select all / Select none / Invert**: Bulk actions on the visible (filtered) component list.
- **Live summary**: At the bottom of the dialog, see "X of Y selected · Z rows will be translated" updating as you tick boxes.

Click **Apply** to confirm your selection. The estimate next to the Filter button on the main screen shows the resulting row count.

The live feed panel has a **"Pop out"** button that detaches it into an independent window so you can monitor translation progress while navigating other phases.

**Independent path:** click **"Load Excel..."** to skip translation and continue with a workbook you already translated.

**Advanced options live in `Translation → Settings...`** (Ctrl+,):

* **Backend** (Google free / DeepL / Azure / OpenAI) and API key.
* **Workers** (concurrent translation threads, default 4).
* **Rate limit** (auto-tunes; defaults to 8 req/s).
* **Wake-lock** to prevent system sleep during long runs.
* **Glossary** CSV path (do-not-translate terms + forced translations).
* **Translation memory** SQLite path (caches translations across runs).
* **Batch targets** for multi-language runs.

### Phase 4 — Browse & Review

**What it does:** browse and (optionally) edit the translations, with auto-validation on entry so issues stand out immediately.

**How to use:**

1. The **status pill** at the top tells you whether the document is clean (green), has warnings (amber), or has errors (red).
2. The **counters** show translated / untranslated / issue counts.
3. **Filter** the table by component, status, or substring search — see [Filters (Phase 4)](#filters-phase-4--browse--review) below for details.
4. Click any row to populate the **side-by-side editor** at the bottom (source on the left, translation on the right).  Edit the translation and click **Apply** to save the change.  Click **Reset to source** to revert.  Drag the slim handle between the table and the editor to resize them; the text areas grow vertically with the editor pane.
5. **"Save reviewed workbook (.xlsx)"** writes the current state to disk.
6. Click **"Continue to Phase 5 (Validate & Fix) →"**.

**Re-upload externally edited Excel:** Click **"Load reviewed Excel..."** at the top right.  The uploaded workbook *replaces* the in-memory document and becomes the latest version for all subsequent phases.

**Independent path:** identical — load any workbook into Review and start editing.

#### Filters (Phase 4 — Browse & Review)

The filter row at the top of Phase 4 lets you focus on a subset of translations:

- **Component dropdown**: Show only rows belonging to one component type (e.g. `CustomLabel`). Choose "All" to show everything.
- **Status dropdown**: Show only "Translated" or "Untranslated" rows, "Approved" (only approved entries), or "All".
- **Search field**: Substring search across the Key and Source label columns. Useful for finding specific labels (e.g. type "Account" to find all account-related fields).

The three filters combine: e.g. setting Component=CustomLabel + Status=Untranslated + Search="error" shows only untranslated CustomLabel rows whose key or label contains "error".

The table updates immediately as you type or change dropdowns.  Click the **"Clear"** button at the right of the filter row to reset all filters at once, including any column-value filters applied via the header right-click menu.

### Phase 5 — Validate & Fix

**What it does:** dedicated phase that shows *only* the rows with validation issues (no noise from clean rows) and offers automatic + manual fixes.

**How to use:**

1. Validation runs automatically on entry.
2. The banner shows total errors / warnings.
3. Click **"Auto-fix all"** to let the deterministic fixers resolve what they can:
   * Restore missing placeholders / `{0}` MessageFormat tokens
   * Trim translations that exceed Salesforce length limits (truncated at word boundary)
   * Clear whitespace-only translations
   * Remove duplicate keys (keeps last occurrence)
   * Restore missing HTML tag pairs
4. Or click **"Auto-fix selected"** / **"Auto-fix this row"** for finer control.
5. Use the **inline editor** below the table to manually correct rows the auto-fixer can't handle.
6. Click **"Re-validate"** to confirm everything is now clean.
7. Click **"Save fixed workbook (.xlsx)"** at any point.
8. Click **"Download Report..."** to export the validation results as CSV, JSON, or HTML. A save dialog lets you choose the format; the report includes severity, category, component, key, and message for every issue.
9. Click **"Continue to Phase 6 (Export STF) →"**.

**Independent path:** click **"Load Excel for validation..."** to land here directly with any workbook — useful when you only want to check / fix issues, not run the full pipeline.

**Jump to context:** double-click any issue row (or click "Jump to Phase 4 for context") to navigate back to Phase 4 with that row selected, full editor visible, all filters cleared.

### Phase 6 — Export STF

**What it does:** writes the three STF files Salesforce expects.

**How to use:**

1. Pick the **Language** + **Code** (auto-filled from earlier phases).
2. Pick the **Output directory**.
3. (Optional) Click **"Run validation"** for a last-minute check.
4. Click **"Export 3 STF files"**.

You get three files:

| File | Contents |
|---|---|
| `Bilingual_<code>.stf` | Bilingual full file with both translated and untranslated sections |
| `Translated_<code>.stf` | Only the translated rows |
| `Untranslated_<code>.stf` | Only the untranslated rows |

All three are UTF-8 with LF line endings (no BOM), byte-compatible with Salesforce's import format.

**Independent path:** click **"Load translated Excel..."** for the most common drop-in scenario — you have a translated workbook from somewhere else and just want STF files out.  No earlier phases required.

---

## 4. Settings (`Edit → Settings...` or `Ctrl+,`)

The Settings dialog has three tabs that group all advanced configuration:

### Translation tab
- **Translator backend** -- Choose between Google Translate (free, default), DeepL, Microsoft Azure Translator, or OpenAI. The free tier (Google) requires no setup. Paid backends require an API key.
- **API key** -- Required for paid backends. Either paste it here or set the corresponding environment variable (e.g. `DEEPL_API_KEY`, `AZURE_TRANSLATOR_KEY`, `OPENAI_API_KEY`). Use "Save to keyring" to store the key securely in your OS credential store (see Section 21).
- **Workers** -- Number of concurrent translation requests. 4 is a safe default. Increase to 8 or higher if your backend has high quotas; reduce to 1 for very rate-limited backends.
- **Rate limit** -- Max requests per second. 8 is safe for Google free tier. Set to 0 (unlimited) for paid backends.
- **Prevent system sleep** -- Prevents your laptop from sleeping during a long translation run. Recommended on for runs >5 minutes.
- **Multi-language batch** -- Translate to multiple target languages in one run. Comma-separated codes (e.g. `fr, de, es`).
- **Fuzzy TM threshold** -- Minimum similarity score (0-100) for fuzzy translation memory matches. 0 disables fuzzy matching. See Section 15.
- **Fuzzy auto-accept** -- Score above which fuzzy matches are used automatically without confirmation. Default: 90.
- **Session persistence** -- Toggle auto-save of application state to `.stxproj` files. Enabled by default. See Section 17.

### Resources tab
- **Glossary** — Optional CSV file with three columns: `source, target, do_not_translate`.
  - Mark brand/product names with `do_not_translate=true` so they're never modified during translation.
  - Or provide a fixed translation in `target` to enforce a specific term.
  - Example row: `Bayer, , true` (protects "Bayer" from translation).
- **Translation memory** — Optional SQLite database that caches every translation across runs. Subsequent translations of the same source text reuse the cached result, which is much faster and consumes no API quota. The default path is `~/.cache/salesforce-translation-handler/tm.sqlite`.

### Appearance tab
- **Theme** — Application color scheme. Options:
  - Light (default) — clean, readable
  - Dark — for low-light environments
  - Ocean — sky blue & teal palette
  - Forest — earthy green palette
  - Sunset — warm amber palette
  - Auto (system) — follows your OS color scheme

Theme changes take effect immediately when you click OK.

---

## 5. Common workflows

### "I have an STF, give me STF" (full pipeline)

`Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6`

Just click "Continue" at the bottom of each phase.

### "I already translated externally, just convert to STF"

Open the app → click **Phase 6** in the sidebar → **Load translated Excel...** → pick file → set language → Export.

### "I want to check my translations before submitting"

Open the app → click **Phase 5** in the sidebar → **Load Excel for validation...** → pick file → review issues → Auto-fix all → Save.

### "A colleague edited the Excel, integrate their changes"

Open the app → click **Phase 4** → **Load reviewed Excel...** → pick the colleague's file → review → Save → continue to Phase 5 / 6.

### "I want to reuse translations across runs"

Open `Edit → Settings → Resources` and set the **Translation memory** path.  Translations from previous runs are now reused automatically — same source string is never translated twice.

### "Don't translate brand names"

Create a CSV with columns `source,target,do_not_translate`:

```csv
source,target,do_not_translate
Bayer,,true
ATLS,,true
case,ケース,
```

Open `Edit → Settings → Resources` and set the **Glossary** path.  Brand terms are now protected; the `case → ケース` row enforces a forced translation.

---

## 6. Output formats

### Excel workbook layout

| Sheet | Contents |
|---|---|
| `<ComponentType>_<Status>` | One per group; columns: `Key`, `Label`, `Translation` |
| `Content Details` | Index of every component sheet |
| `Translation_Summary` | Per-sheet counts (after Phase 3) |
| `Translation_Status_Log` | Per-row status (after Phase 3) |

Every cell is forced to text type so Salesforce IDs (`001D000000IqhSL`), times (`10:30`), and zero-prefixed numbers (`007`) are preserved without Excel re-typing them as numbers / dates.  Labels starting with `=` / `+` / `-` / `@` are guarded against formula injection.

### STF files (Phase 6)

UTF-8, LF line endings, no BOM.  Section separators (`------------------TRANSLATED-------------------`) are reproduced character-for-character to keep downstream tooling happy.

---

## 7. Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| "libGL.so.1: cannot open shared object" on Linux | Install Qt's runtime libs.  Debian/Ubuntu: `sudo apt install libgl1 libegl1 libxkbcommon0 libdbus-1-3`.  Fedora/RHEL/Amazon Linux: `sudo dnf install mesa-libGL mesa-libEGL libxkbcommon`. |
| Translation hangs or 429-errors | Free Google tier rate-limits aggressively.  The adaptive limiter backs off automatically; for production volume, switch to DeepL via `Edit → Settings`. |
| Lid-close interrupts a run | The wake-lock prevents *idle* sleep, not lid-close.  Keep the lid open during long runs.  TM caching ensures re-runs after interrupt are nearly instant. |
| Salesforce import says "duplicate key" | Run **Phase 5** with **Auto-fix all** — the deduplicator keeps the last occurrence (Salesforce's own behaviour) and removes earlier duplicates. |
| Translation lost a placeholder | Phase 5 flags it under `token_drift`.  **Auto-fix this row** restores the placeholder.  Check the source label for unusual quoting if the auto-fixer can't help. |
| Excel reformatted my Salesforce IDs | The app forces text type on every column on export, so this only happens if a third party re-saved the workbook.  Keep edits inside the app's Phase 4 editor when possible. |

---

## 8. Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+0..5` | Switch to phase N |
| `Ctrl+O` | Open file (auto-routes by extension) |
| `Ctrl+S` | Save current phase artifact |
| `Ctrl+H` | Find & Replace (Phase 4) |
| `Ctrl+Z / Ctrl+Y` | Undo / Redo last translation edit (Phase 4 only) |
| `Ctrl+Shift+Z / Ctrl+Shift+Y` | Undo / Redo last major action (app-wide) |
| `Ctrl+B` | Go to previous phase |
| `Ctrl+,` | Open Settings |
| `Ctrl+L` | Toggle the Status Log dock |
| `Ctrl+F1` | FAQ & Troubleshooting |
| `F1` | This user guide |
| `Ctrl+Q` | Quit |

---

## 9. Where settings are stored

User preferences (window geometry, theme, last target language, recent files, translator backend, API keys, glossary path, TM path) live in your platform's standard QSettings location:

| OS | Path |
|---|---|
| macOS | `~/Library/Preferences/com.salesforce-translation-handler.plist` |
| Windows | `HKEY_CURRENT_USER\Software\SalesforceTranslationHandler` |
| Linux | `~/.config/SalesforceTranslationHandler/SalesforceTranslationHandler.conf` |

The default translation memory database lives at `~/.cache/salesforce-translation-handler/tm.sqlite` unless you override it in Settings → Resources.

---

## 10. CLI: Export validation reports

The `stx validate` command supports a `--export-report` flag to write the validation results to a file.  The format is detected from the file extension.

### Usage

```bash
# Export as CSV
stx validate input.stf --export-report report.csv

# Export as JSON
stx validate input.stf --export-report report.json

# Export as HTML (standalone, can be opened in any browser)
stx validate input.stf --export-report report.html
```

### Format details

| Format | Description |
|---|---|
| CSV | Columns: `severity`, `category`, `component`, `key`, `message`.  A summary comment row at the top shows error/warning counts. |
| JSON | Structure: `{summary: {errors, warnings, total}, issues_by_category: {...}, issues: [...]}`.  Suitable for programmatic consumption. |
| HTML | Standalone page with embedded CSS, summary header, and issues table grouped by category.  Open in any browser. |

The report is written regardless of whether validation passes or fails.  The command still exits with code 1 when errors are present (useful for CI pipelines).

---

## 11. CLI: Approve and unapprove translations

The `stx approve` and `stx unapprove` commands let you batch-mark translations as approved (or clear that mark) directly from the command line.

### Approve

```bash
# Approve specific entries by key
stx approve input.stf --keys CustomLabel.A,CustomLabel.B

# Approve all entries that have a non-empty translation
stx approve translated.xlsx --all-translated
```

### Unapprove

```bash
# Unapprove specific entries by key
stx unapprove input.stf --keys CustomLabel.A

# Clear approval on all entries
stx unapprove translated.xlsx --all
```

Both commands detect the file format by extension (`.stf` or `.xlsx`) and write the result back to the same file.

---

## 12. Approved status

The **Approved** status marks individual translations as reviewed and accepted. It affects several parts of the workflow:

### Phase 4 (Browse & Review)

- A new **Approved** column (rightmost) shows a checkbox for every row.
- Toggle the checkbox to mark/unmark an entry as approved.
- Use the **Status** dropdown filter (set to "Approved") to show only approved rows.
- Approved entries display "Approved" in the Status column.

### Phase 5 (Validate & Fix)

- Entries marked as approved are **skipped** during per-entry validation checks (length limits, token drift, HTML mismatch, empty translation).
- An informational note reports how many approved entries were skipped.
- Document-level checks (duplicate keys) still run on all entries regardless of approval status.

### Persistence

| Format | How approval is stored |
|---|---|
| Excel (`.xlsx`) | An **"Approved"** column with value `Yes` or empty. Old workbooks without this column import fine (all entries default to not approved). |
| STF (`.stf`) | A trailing `# APPROVED` marker after the out-of-date column: `key\tlabel\ttranslation\t-\t# APPROVED`. Lines without the marker are treated as not approved. |

---

That's it.  The CLI (`stx --help`) mirrors every phase for scripting / CI use; see [`README.md`](./README.md) for command-line examples.

---

## 13. Find and Replace

Phase 4 (Browse and Review) includes a Find and Replace dialog, accessible via `Ctrl+H` or from the Edit menu.

### GUI usage

1. Press `Ctrl+H` while in Phase 4.
2. Enter the text to find in the **Find** field.
3. Enter the replacement in the **Replace** field.
4. Configure options:
   - **Case sensitive** -- match exact case only.
   - **Regex** -- treat the find pattern as a regular expression.
   - **Scope** -- which fields to search: Translation (default), Label, Key, or All.
5. The dialog shows a live match count as you type.
6. Click **Replace** to replace the current match, or **Replace All** to replace every occurrence.

All replacements are tracked in the undo stack (see Section 14).

### CLI usage

```bash
# Replace text in translations (default scope)
stx replace workbook.xlsx --find "old term" --replace "new term"

# Case-sensitive regex replacement in all fields
stx replace workbook.xlsx --find "Rev\d+" --replace "Revision" \
    --regex --case-sensitive --scope all

# Works with STF files too
stx replace input.stf --find "deprecated" --replace "legacy"
```

Available scope values: `translation`, `label`, `key`, `all`.

---

## 14. Undo / Redo

Phase 4 (Browse and Review) maintains a full undo/redo history for the current session.

| Action | Shortcut |
|---|---|
| Undo | `Ctrl+Z` |
| Redo | `Ctrl+Y` |

### What is tracked

- Individual cell edits (Apply button in the side-by-side editor)
- Reset-to-source operations
- Bulk find-and-replace operations
- Approval status changes

The undo stack has unlimited depth within a session. Closing the application or loading a new file resets the history.

---

## 15. Fuzzy Translation Memory

When the translation memory does not contain an exact match for a source string, the fuzzy matching engine (powered by `rapidfuzz`) searches for similar entries above a configurable similarity threshold.

### How it works

1. A source string is looked up in the TM.
2. If no exact hit is found and fuzzy matching is enabled, the TM is searched for entries with similarity above the threshold.
3. If a match scores above the auto-accept threshold, it is used directly.
4. Otherwise the match is logged but the string is sent to the translation backend.

### Configuration

In `Edit -> Settings -> Translation`:

- **Fuzzy TM threshold** -- minimum similarity (0-100). Set to 0 to disable. Recommended: 70-80.
- **Fuzzy auto-accept** -- score above which matches are applied without confirmation. Default: 90.
- **Fuzzy max results** -- number of candidates to evaluate per lookup. Default: 5.

### CLI flags

```bash
stx translate input.xlsx output.xlsx --target ja \
    --fuzzy-threshold 75 \
    --fuzzy-max-results 5 \
    --fuzzy-auto-accept 90
```

### Live feed indicators

During translation, fuzzy-matched entries appear in the live feed with a `FM` (Fuzzy Match) indicator and the match score:

```
[42/1000 | T:30 TM:5 FM:3 D:7] EN: Hello world -> JA: ...
```

---

## 16. Resume after crash

Translation runs are automatically checkpointed so that interrupted runs can resume from the last saved position rather than restarting from scratch.

### How it works

- After every batch of rows is translated, the current position and results are saved to a checkpoint file.
- Checkpoints are keyed by source file path and target language.
- On the next run with the same source and target, the checkpoint is detected and the run resumes from the last completed row.

### GUI behaviour

- If a checkpoint exists when you click "Start translation" in Phase 3, a prompt asks whether to resume or start fresh.
- Translation progress shows "resumed N rows" in the status.

### CLI flags

```bash
# Resume is enabled by default
stx translate input.xlsx output.xlsx --target ja

# Start fresh (ignore any existing checkpoint)
stx translate input.xlsx output.xlsx --target ja --no-resume

# Explicitly delete the checkpoint before starting
stx translate input.xlsx output.xlsx --target ja --reset-checkpoint
```

---

## 17. Session persistence

The application automatically saves its full state to a `.stxproj` project file.  When you reopen the same source file, the session is restored -- including the loaded document, translation results, phase completion status, and settings.

### Automatic behaviour

- After every significant action (phase completion, translation finish, file save), the session is written.
- On launch, if a session exists for the opened file, it is restored silently.
- The `.stxproj` file is stored alongside the source file by default.

### Manual controls

- `File -> Save Session` -- force-save the current session.
- `File -> Restore Session` -- reload from the last saved session.

### CLI subcommands

```bash
# Inspect a session file
stx session info project.stxproj

# Clear the auto-saved session for a source file
stx session reset input.stf
```

### Settings

Session persistence can be toggled in `Edit -> Settings -> Translation`.  When disabled, no `.stxproj` files are written.

---

## 18. Auto-detect source language

The application uses the `langdetect` library to analyse source labels and automatically suggest the source language, eliminating the need to manually specify it for non-English source files.

### GUI behaviour

- In Phase 1 (Import STF), after parsing the file, the detected language is displayed in the metadata grid with a confidence percentage.
- In Phase 3 (Translate), the Source language field is pre-filled with the detected language.
- You can always override the detection by selecting a different language manually.

### CLI behaviour

```bash
# Auto-detection is on by default
stx translate input.xlsx output.xlsx --target ja
# Output: "Detected source language: French (fr) [confidence: 95%]"

# Disable auto-detection (use default 'en')
stx translate input.xlsx output.xlsx --target ja --no-detect-source

# Explicit --source always takes priority
stx translate input.xlsx output.xlsx --target ja --source fr
```

Detection requires at least a few non-empty labels.  If confidence is below the threshold, the system falls back to `en` with a warning.

---

## 19. Import existing translations

Reuse translations from a previously translated Excel workbook.  This is useful when you have a partially translated file from a colleague or a prior run and want to apply those translations before starting a new translation pass.

### How it works

1. The import file is parsed and a key-to-translation mapping is built.
2. Before the translation run starts, entries whose keys exist in the import mapping receive the imported translation.
3. Imported entries are counted separately in the results (`imported` count in the live feed).
4. Remaining untranslated entries proceed to the translation backend as normal.

### GUI usage

In Phase 3, click the **"Import Translations..."** button and select a previously translated `.xlsx` file.

### CLI usage

```bash
stx translate input.xlsx output.xlsx --target ja \
    --import-translations previous_translated.xlsx
```

---

## 20. Retranslation control

By default, entries that already have a non-empty translation are skipped during the translation run.  The retranslation control lets you choose to re-translate those entries instead.

### When to use it

- You changed the translator backend and want fresh translations from the new engine.
- Source labels were updated and existing translations are stale.
- You imported translations (Section 19) but want to override some with fresh API results.

### GUI usage

Open the **Translation** menu and check **"Retranslate all (overwrite existing)"** before starting translation.

### CLI usage

```bash
# Default: skip rows that already have translations
stx translate input.xlsx output.xlsx --target ja

# Force re-translation of all rows
stx translate input.xlsx output.xlsx --target ja --retranslate-existing
```

---

## 21. Secure credential storage

API keys for paid translation backends can be stored in your operating system's secure credential store instead of in plain text configuration files.

### Supported keystores

| OS | Backend |
|---|---|
| macOS | Keychain |
| Windows | Credential Locker |
| Linux | Secret Service (GNOME Keyring / KDE Wallet) |

### How to use

1. Open `Edit -> Settings -> Translation`.
2. Enter your API key in the key field.
3. Click **"Save to keyring"** next to the field.
4. On subsequent launches, the key is loaded from the keyring automatically.

To remove a stored key, clear the field and click "Save to keyring" again, or use your OS keyring manager directly.

The `keyring` library is included in the `[gui]` install extra.

---

## FAQ

**Q: What file types does the app support?**
A: `.stf` files (Salesforce Translation Workbench export) and `.xlsx` Excel workbooks. STF files are loaded in Phase 1; Excel files can be loaded in Phases 2-6 depending on their stage.

**Q: Can I skip phases?**
A: Yes. Click any phase in the sidebar and use its "Load..." button to bring in your file directly. You do not have to start at Phase 1 every time.

**Q: How does Translation Memory work?**
A: The app stores every translation in a local SQLite database. On subsequent runs, if the same source text appears, the cached translation is reused instantly (no API call). Configure the TM path in Settings > Resources.

**Q: Where is my API key stored?**
A: When "Remember API key" is checked in Settings > Appearance > Credentials, the key is stored in your OS secure credential manager (macOS Keychain, Windows Credential Manager, or Linux SecretService). It is never saved in plain text.

**Q: What does Reset Session do?**
A: It clears ALL application state: document, file paths, phase statuses, undo history, filters, imported translations, scope, glossary, batch targets -- everything. The app returns to its initial empty state. Use "Reset Current Phase" if you only want to redo the current step.

**Q: Can I translate to multiple languages at once?**
A: Yes. In Settings > Translation > Batch, enter comma-separated language codes (e.g. `fr, de, es`). Each language gets its own output subfolder with a separate translated workbook.

**Q: How do I undo a mistake?**
A: There are two undo levels:
- **Phase 4 per-edit undo** (Ctrl+Z / Ctrl+Y): reverses individual translation edits in the Review table.
- **App-wide undo** (Ctrl+Shift+Z / Ctrl+Shift+Y): reverses major actions like loading a file, running translation, or auto-fix. Accessible from Edit menu.

**Q: What is the Approved column in Phase 4?**
A: Checking "Approved" marks a translation as reviewed and accepted. Approved rows are skipped during validation in Phase 5, reducing noise when you have already verified certain translations.

**Q: Why does the override dialog appear when I load a file?**
A: If a workflow is already active (you have loaded a file and progressed through phases), loading a different file would replace the current work. The dialog gives you a chance to save first, discard, or cancel.

**Q: How do I build the standalone installer?**
A: On Windows, run `python build_secure_setup.py --exe` for a standalone .exe, or `python build_secure_setup.py` for a full installer (requires Inno Setup 6). If the app crashes on launch, check `%TEMP%\stx_crash.log` for details.

---

## Getting Stuck? (Troubleshooting)

| Problem | Solution |
|---------|----------|
| App won't start | Ensure Python 3.9+ is installed and on PATH. Run `pip install -e ".[gui]"` to install dependencies. Check that PySide6 installed correctly. |
| Translation fails with HTTP 429 | You are hitting the API rate limit. Go to Settings > Translation > Performance and reduce the rate limit (try 2-4 req/s). |
| Exported STF looks wrong | Double-check that the target language code (e.g. `ja`, `de`, `fr`) matches your Salesforce Translation Workbench setup exactly. |
| Window opens off-screen | The app saves window geometry. Delete the QSettings file and restart. On Windows: delete registry key under `HKCU\Software\SalesforceTranslationHandler`. On macOS/Linux: delete `~/.config/SalesforceTranslationHandler/`. |
| Undo not working as expected | Phase 4 Ctrl+Z only works for translation cell edits. For undoing major actions (load file, translate, auto-fix), use Ctrl+Shift+Z (Edit → Undo last major action). |
| Reset Session clears everything? | Yes, that is by design. "Reset Session" = full clear. Use "Reset Current Phase" (File menu) to only reset the active phase and downstream. |
| Standalone .exe crashes immediately | Check `%TEMP%\stx_crash.log` (Windows) or `/tmp/stx_crash.log` (Mac/Linux) for the error message. Common cause: missing hidden imports -- ensure build_exe.py includes all required modules. |
| "No module named stx" when running .exe | Rebuild with `python build_exe.py` after installing `pip install -e ".[gui]" pyinstaller`. |
