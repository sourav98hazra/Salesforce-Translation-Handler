# Salesforce Translation Manager — User Guide

A practical, end-to-end walkthrough of the desktop application.

---

## 1. Install + launch

### Install

You only need this once.  Pick the option that fits how you'll run the app.

| You are... | Best option |
|---|---|
| A developer with Python on the machine | `pip install -e ".[gui]"` from the repo root |
| A non-developer on Windows / macOS / Linux | Double-click `launch.bat` / `launch.command` / `launch.sh` (auto-creates a venv on first run) |
| Distributing to people without Python | Build a standalone executable: `python build_exe.py` produces `dist/SalesforceTranslationHandler{.exe,.app,}` — ship that single file |

Full instructions and prerequisites are in [`README.md`](./README.md).

### Launch

After install, three equivalent ways to start:

* **Double-click** the launcher (`launch.bat` / `launch.command` / `launch.sh`).
* From a terminal: `stx-app`.
* From a terminal: `stx gui`.

The Window opens on **Phase 1 -- Import STF**.

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

---

## 3. The six phases

### Phase 1 — Import STF

**What it does:** parses the source `.stf` file from Salesforce Translation Workbench into an in-memory document.

**How to use:**

1. Click **"Browse STF..."** and pick the `.stf` you exported from Salesforce.
2. Verify the parsed metadata displayed in a **2-column grid** (language and code side by side, STF type and total rows side by side, translated and untranslated counts side by side). Hover over any field to see the full value in a tooltip if it is truncated.
3. (Optional) Edit the language fields if Salesforce's preamble was missing or wrong.
4. (Optional) Click **"Save copy as STF..."** to write a clean copy to disk.
5. Click **"Continue to Phase 2 →"**.

**Independent path:** drop an `.stf` directly here and parse it; no need to do anything else.

The Preview panel in Phase 1 has a **"Pop out"** button that detaches the preview into an independent window, useful for viewing the parsed content alongside other phases.

### Phase 2 — STF → Organised Excel

**What it does:** groups the parsed rows by component type (`CustomLabel`, `ButtonOrLink`, etc.) into a structured workbook with one sheet per group plus a `Content Details` index sheet.

**How to use:**

1. The output path defaults to `<source>_organized.xlsx`.  Click **Browse...** to change it.
2. Click **"Convert and save .xlsx"** (the primary button) to write the file.
3. (Optional) Click **"Save copy to..."** to write an additional copy elsewhere — handy for backups or sharing without disturbing the file the rest of the pipeline uses.
4. Inspect the **Content Details** preview to confirm the row counts.
5. Click **"Continue to Phase 3 →"**.

**Independent path:** click **"Load existing organised .xlsx..."** to start from a previously generated workbook.

### Phase 3 — Translate

**What it does:** auto-translates every untranslated row using the configured backend, with Salesforce IDs / placeholders / URLs / emails / HTML protected from modification.

**How to use:**

1. Pick the **Source** and **Target** language (displayed side by side in a compact form at the top).
2. Click **"Filter Components..."** to open a dialog where you can select which component types to translate (default: all selected). See the [Filter Components dialog](#filter-components-dialog-phase-3) section below for full details on the search, status filter, and bulk-action controls.
3. Click **"Start translation"**.
4. Watch the **live feed** below the progress bar. Each line shows inline counters and the translation pair:
   ```
   [42/1000 | T:30 TM:5 D:7] EN: Hello -> JA: こんにちは
   ```
   - `T` = translated via API, `TM` = from translation memory, `D` = deduplicated
5. Every 50 rows an **intermittent summary** appears with progress percentage, rate (rows/s), and ETA.
6. When translation completes, a **final summary block** is printed:
   ```
   ━━━ DONE ━━━
   Translated: 800 | TM: 120 | Deduped: 50 | Skipped: 30
   Elapsed: 5m 32s | Rate: 3.2 rows/s
   ```
7. The translated document is held **in memory** — click **"Save copy to..."** to write it to a file of your choice. The default suggested filename is `<source>_translated.xlsx` in the same folder as the source. Audit sheets (per-row status log + summary) are appended to the saved workbook automatically.
8. Click **"Continue to Phase 4 →"** when done.

#### Filter Components dialog (Phase 3)

Click "Filter Components..." to open the component selection dialog. Use it to:

- **Search**: Type to filter the component list by name (case-insensitive substring match).
- **Status filter**: Choose what kinds of components to show:
  - "Show all components" — every type, regardless of status (default)
  - "Only components with untranslated rows" — focus on what needs translation
  - "Only components with translated rows (for retranslation)" — useful if you want to redo translations
  - "Only components with both translated and untranslated" — mixed-state components
- **Select all / Select none / Invert**: Bulk actions on the visible (filtered) component list.
- **Live summary**: At the bottom of the dialog, see "X of Y selected · Z rows will be translated" updating as you tick boxes.

Click **Apply** to confirm your selection. The estimate next to the Filter button on the main screen shows the resulting row count.

The live feed panel has a **"Pop out"** button that detaches it into an independent window so you can monitor translation progress while navigating other phases.

**Independent path:** click **"Load translated .xlsx..."** to skip translation and continue with a workbook you already translated.

**Advanced options live in `Edit → Settings`** (Ctrl+,):

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

The table updates immediately as you type or change dropdowns.

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
| `Super_STF_<code>.stf` | Bilingual full file with both translated and untranslated sections |
| `TranslatedOnly_STF_<code>.stf` | Only the translated rows |
| `UntranslatedOnly_STF_<code>.stf` | Only the untranslated rows |

All three are UTF-8 with LF line endings (no BOM), byte-compatible with Salesforce's import format.

**Independent path:** click **"Load translated Excel..."** for the most common drop-in scenario — you have a translated workbook from somewhere else and just want STF files out.  No earlier phases required.

---

## 4. Settings (`Edit → Settings...` or `Ctrl+,`)

The Settings dialog has three tabs that group all advanced configuration:

### Translation tab
- **Translator backend** — Choose between Google Translate (free, default), DeepL, Microsoft Azure Translator, or OpenAI. The free tier (Google) requires no setup. Paid backends require an API key.
- **API key** — Required for paid backends. Either paste it here or set the corresponding environment variable (e.g. `DEEPL_API_KEY`, `AZURE_TRANSLATOR_KEY`, `OPENAI_API_KEY`).
- **Workers** — Number of concurrent translation requests. 4 is a safe default. Increase to 8 or higher if your backend has high quotas; reduce to 1 for very rate-limited backends.
- **Rate limit** — Max requests per second. 8 is safe for Google free tier. Set to 0 (unlimited) for paid backends.
- **Prevent system sleep** — Prevents your laptop from sleeping during a long translation run. Recommended on for runs >5 minutes.
- **Multi-language batch** — Translate to multiple target languages in one run. Comma-separated codes (e.g. `fr, de, es`).

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
| `Ctrl+,` | Open Settings |
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
