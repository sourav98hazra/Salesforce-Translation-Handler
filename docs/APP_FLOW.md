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
| Reset Phase | Current + downstream | Phase status, downstream artifacts (e.g. validation report, reviewed path) |

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

## Phase 4 Column Filtering

Right-click any column header in the Review table:
- Sort Ascending / Sort Descending
- Filter by value (checkable list of distinct values)
- Clear filter
- Select all / Select none

Multiple column filters stack (AND logic).

---

*Generated for v2.0.0 of Salesforce Translation Manager.*
