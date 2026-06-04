# Salesforce Translation Manager - Application Flow

A visual overview of the application architecture and workflow.

---

## Six-Phase Pipeline

```
+------------------+     +------------------+     +------------------+
|  Phase 1         |     |  Phase 2         |     |  Phase 3         |
|  Import STF      | --> |  STF -> Excel    | --> |  Translate       |
|                  |     |                  |     |                  |
|  Input: .stf     |     |  Input: Document |     |  Input: Document |
|  Output: Document|     |  Output: .xlsx   |     |  Output: Document|
+------------------+     +------------------+     +------------------+
                                                         |
                                                         v
+------------------+     +------------------+     +------------------+
|  Phase 6         |     |  Phase 5         |     |  Phase 4         |
|  Export STF      | <-- |  Validate & Fix  | <-- |  Browse & Review |
|                  |     |                  |     |                  |
|  Input: Document |     |  Input: Document |     |  Input: Document |
|  Output: .stf x3 |     |  Output: Document|     |  Output: .xlsx   |
+------------------+     +------------------+     +------------------+
```

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+0..5 | Jump to Phase 1-6 |
| Ctrl+B | Previous Phase (go back) |
| Ctrl+O | Open file |
| Ctrl+S | Save current phase |
| Ctrl+Z | Undo (Phase 4 per-edit) |
| Ctrl+Y | Redo (Phase 4 per-edit) |
| Ctrl+Shift+Z | App-wide Undo (major actions) |
| Ctrl+Shift+Y | App-wide Redo (major actions) |
| Ctrl+H | Find & Replace (Phase 4) |
| Ctrl+L | Toggle Status Log |
| Ctrl+, | Open Settings |
| F1 | User Guide |
| Ctrl+Q | Quit |

## Undo/Redo Architecture

```
+------------------------------------------+
|           App-wide History               |
|  (Ctrl+Shift+Z / Ctrl+Shift+Y)          |
|  Reverses: Load file, Translate,         |
|            Auto-fix, Reset               |
|  Storage: AppSnapshot list (max 25)      |
+------------------------------------------+
         |
         |  separate from
         v
+------------------------------------------+
|        Phase 4 Per-Edit Undo             |
|  (Ctrl+Z / Ctrl+Y)                      |
|  Reverses: Individual cell edits         |
|            (translation text, approved)  |
|  Storage: UndoStack with UndoCommand     |
+------------------------------------------+
```

## Workflow Override Logic

```
User loads new file
       |
       v
  Active workflow? --No--> Proceed normally
       |
      Yes
       |
       v
  Same file? --Yes--> Proceed (no override needed)
       |
      No
       |
       v
  Unsaved changes? --Yes--> Show "Save / Discard / Cancel" dialog
       |                            |
      No                     User chooses
       |                            |
       v                            v
  Show "Override?" dialog     Save? -> save then override
       |                     Discard? -> override without saving
       v                     Cancel? -> abort, keep current
  User confirms? --No--> Abort
       |
      Yes
       |
       v
  Clear stale state, load new file
```

## Reset Behavior

| Action | Scope | What it clears |
|--------|-------|----------------|
| Reset Session | Everything | Document, paths, phases, undo, filters, imports, scope, glossary, batch, all visual state |
| Reset Phase | Current + downstream | Phase status, downstream artifacts (e.g. validation report, reviewed path); reloads document from upstream phase snapshot |

## Phase Snapshot / Reset Current Phase

Each phase saves a lightweight **PhaseSnapshot** (source file path, artifact type, row count, target language code/name, and timestamp) when it completes. This enables reliable reset behavior:

- On **Reset Current Phase**, the document is reloaded from the upstream phase's snapshot file via `_restore_from_snapshot()`.
- The current phase and all downstream phases are set to IDLE.
- Downstream pages show empty until the user re-enters them via "Continue to Phase N" from the upstream phase.
- All action buttons in downstream phases are disabled after reset.
- No `on_enter()` is called for downstream pages after reset; the page shows a clean empty state.
- Loading an Excel via "Load" in any phase marks the upstream phase as DONE (satisfies the IDLE check for downstream navigation).

## Settings Layout

```
Settings Dialog
+-- Translation tab
|   +-- Translator Backend (combo + API key + status)
|   +-- Performance (workers, rate limit, wake-lock)
|   +-- Batch (extra target codes)
|
+-- Resources tab
|   +-- Translation Memory (path + fuzzy matching controls)
|   +-- Glossary (CSV path)
|   +-- Import Translations (xlsx path + enable checkbox)
|   +-- Session (enable auto-save/restore)
|
+-- Appearance tab
    +-- Theme (6 options)
    +-- Credentials (remember API key in OS keyring)
```

## Translation Menu

The **Translation** menu (menu bar) groups all translation behaviour toggles. Changes persist between sessions.

```
Translation
├── [✓] Use in-file translations      (default on)
│         Reuse translations already present in the same file.
│         If "Save" is translated elsewhere as "保存", untranslated rows
│         with the same label get "保存" without any API call.
│
├── [✓] Use Translation Memory cache  (default on)
│         Reuse translations from previous runs (SQLite TM database).
│
├── [ ] Use Fuzzy matching             (default off)
│         Approximate TM matches (e.g. "Save record" ~ "Save Record").
│         Only active when TM cache is also on.
│
├── [  ] Use imported translations    (default off)
│         Apply translations from an imported Excel file at highest priority.
│
├── ─────────────────────────────────
│
├── [  ] Retranslate all (overwrite existing)    (default off)
│         Send ALL rows to the backend, overwriting existing translations.
│         When on, in-file translations are also skipped.
│
├── ─────────────────────────────────
│
├──  Settings...  (Ctrl+,)
└──  Re-enable pre-flight confirmation
```

## Pre-flight Confirmation Dialog

Shown before every translation run (can be disabled with "Don't show again"):

```
Ready to translate?
─────────────────────────────────────────────
Translating 19 rows  (English → Japanese)

Translation options:
  ✓ Use in-file translations     — reuse translations already in this file
  ✓ Use Translation Memory cache — reuse from previous runs
  ✗ Use Fuzzy matching           — approximate TM matches (default off)
  ✗ Use imported translations    — no file imported
  ✗ Retranslate all (overwrite existing)    — only untranslated rows processed

Run summary:
  Backend:             google
  Workers:             4
  Rows to translate:   19 of 2,738 total

[Start translation]   [Cancel — review settings]
─────────────────────────────────────────────
[ ] Don't show this dialog again
```

Re-enable via: **Translation → Re-enable pre-flight confirmation**

## Cancellation Dialog

When you click "Cancel" during translation, a choice dialog appears:

```
Cancel Translation
---
The translation is currently running.

[Finish in-flight rows]   [Stop immediately]   [Keep running]
```

- **Finish in-flight rows** -- waits for active API requests to complete, saves checkpoint, then stops.
- **Stop immediately** -- disconnects all signals, halts instantly with no further progress updates.
- **Keep running** -- dismisses the dialog and continues translating.

## Translation Summary (Live Feed)

After translation completes, the live feed displays:

```
═══════════════════════════════════════════
  TRANSLATION COMPLETE
═══════════════════════════════════════════
  Rows attempted:                 803
  Rows translated:                800
  Rows failed:                      3

  Successfully Translated:        800
  ├─ Via Translation API:         500
  ├─ Via Translation Memory:      120
  │    (via fuzzy match:           15)
  ├─ Via deduplication:            80
  ├─ Via in-file label match:      10
  └─ Via imported reference:        5

  Pre-existing (kept as-is):       95
  Failed Translations:              3
  Total with translation:     895 / 998

  Elapsed time:             00:05:32
  Rate:                     2.4 rows/s
═══════════════════════════════════════════
```

## Phase 4 Column Filtering

Right-click any column header in the Review table:
- Sort Ascending / Sort Descending
- Filter by value (checkable list of distinct values)
- Clear filter (also available via the **"Clear"** button in the filter row)
- Select all / Select none

Multiple column filters stack (AND logic).

---

*Updated for v2.0.0 of Salesforce Translation Manager.*
