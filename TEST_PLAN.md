# Salesforce Translation Manager — Unit & Integration Test Plan

A complete test sheet for the application: every module, every scenario
(happy path, edge cases, negatives, integration, GUI, CLI, and
non-functional). Use it as the checklist for reaching high confidence
before shipping v1.x.

**Legend**
- ✅ = already covered by an existing test
- ⬜ = gap (not yet covered — recommended to add)
- 🐞 = covers a known bug / suspicious behaviour (see "Known issues")

**How to run**

```bash
pip install -e ".[gui,dev]"
pytest -q                          # full suite
pytest -q --cov=stx --cov-report=term-missing   # with coverage
QT_QPA_PLATFORM=offscreen pytest -q tests/gui    # GUI tests (headless)
```

**Current state:** 65 tests across 9 files. Core data/transform paths are
well covered; the CLI, GUI, translator backends, `languages`, `wakelock`,
and several edge cases are uncovered.

---

## 1. `model.py` — Document / Entry data model

| ID | Scenario | Setup / Input | Expected | Status |
|----|----------|---------------|----------|--------|
| MODEL-01 | `component_type` from dotted key | `Entry("CustomApp.Foo.Bar", ...)` | `"CustomApp"` | ⬜ |
| MODEL-02 | `component_type` with no dot | `Entry("Standalone", ...)` | `"Standalone"` | ⬜ |
| MODEL-03 | `component_type` empty key | `Entry("", ...)` | `"Unknown"` | ⬜ |
| MODEL-04 | `component_type` leading-dot key | `Entry(".Foo", ...)` | `"Unknown"` | ⬜ |
| MODEL-05 | `status` translated | translation `"x"` | `"Translated"` | ⬜ |
| MODEL-06 | `status` whitespace-only translation | translation `"   "` | `"Untranslated"` | ⬜ |
| MODEL-07 | `logical_sheet_name` format | `CustomField.A.B` translated | `"CustomField_Translated"` | ⬜ |
| MODEL-08 | `Document.translated()` filters blanks | mixed entries | only non-blank translations | ⬜ |
| MODEL-09 | `Document.untranslated()` filters | mixed entries | only blank translations | ⬜ |
| MODEL-10 | `Document.stats()` counts | 3 entries, 1 translated, 2 components | `{total:3, translated:1, untranslated:2, components:2}` | ⬜ |
| MODEL-11 | `Entry` is frozen / hashable | attempt attribute set | raises `FrozenInstanceError` | ⬜ |

## 2. `stf/parser.py` — STF parsing

| ID | Scenario | Setup / Input | Expected | Status |
|----|----------|---------------|----------|--------|
| PARSE-01 | Header metadata captured | sample with `# Language`, `Language code`, `Type`, `Translation type` | all 4 fields populated | ✅ (test_parse_metadata) |
| PARSE-02 | Translated vs untranslated split | sample rows | 3rd col → translation, else `""` | ✅ |
| PARSE-03 | Bilingual 4-column rows | `KEY\tLABEL\tTRANS\t-` | translation captured, OUT-OF-DATE dropped | ⬜ |
| PARSE-04 | Comment lines (`#`) skipped | line `# note` | not added as entry | ⬜ |
| PARSE-05 | Separator lines (`-...`) skipped | `----TRANSLATED----` | not added as entry | ⬜ |
| PARSE-06 | Bare `key: value` metadata (no `#`) | `Language code: ja` | captured, not treated as a row | ⬜ |
| PARSE-07 | Malformed row (<2 columns) tolerated | `OnlyKey` | silently skipped, no crash | ⬜ |
| PARSE-08 | Blank/whitespace lines skipped | empty lines | ignored | ⬜ |
| PARSE-09 | Tabs inside label preserved | label with embedded content | exact label retained | ⬜ |
| PARSE-10 | `parse_stf(path)` reads UTF-8 file | temp `.stf` | same as `parse_stf_text` | ⬜ |
| PARSE-11 | Empty file | `""` | `Document` with 0 entries, default metadata | ⬜ |
| PARSE-12 | File with only header, no rows | header block only | metadata set, 0 entries | ⬜ |
| PARSE-13 | Non-ASCII / multibyte labels | Japanese source text | preserved exactly | ⬜ |
| PARSE-14 | CRLF input normalised | `\r\n` line endings | parses identically to `\n` | ⬜ |
| PARSE-15 | Mixed TRANSLATED + OUTDATED sections | both section markers present | all rows collected in order | ⬜ |

## 3. `stf/writer.py` — STF rendering & file emission

| ID | Scenario | Setup / Input | Expected | Status |
|----|----------|---------------|----------|--------|
| WRITE-01 | Full STF uses exact separators | parsed doc | both dash separators + headers present | ✅ |
| WRITE-02 | Translated-only excludes untranslated | parsed doc | only translated keys present | ✅ |
| WRITE-03 | LF, no CR, no BOM | write to disk | bytes contain no `\r`, no BOM | ✅ |
| WRITE-04 | `render_untranslated_only_stf` | doc | only untranslated rows + 2-col header | ⬜ |
| WRITE-05 | Out-of-date column `\t-` on translated rows | translated entry | line ends with `\t-` | ⬜ |
| WRITE-06 | `write_stf_files` returns 3 paths | doc + tmp dir | `Super_/TranslatedOnly_/UntranslatedOnly_` named by code | ⬜ |
| WRITE-07 | Language override doesn't mutate input doc | pass `language_code="fr"` | original doc unchanged; output uses `fr` | ⬜ |
| WRITE-08 | Missing language code defaults to `xx` | doc with blank code | filenames use `xx` | ⬜ |
| WRITE-09 | Output dir auto-created | non-existent nested dir | created, files written | ⬜ |
| WRITE-10 | Embedded CR in label scrubbed | label with `\r` | output normalised to `\n` | ⬜ |
| WRITE-11 | Translation with surrounding spaces trimmed in output | `"  x  "` | rendered as `x` | ⬜ |

## 4. `excel/exporter.py` — Document → XLSX

| ID | Scenario | Setup / Input | Expected | Status |
|----|----------|---------------|----------|--------|
| XLEXP-01 | Round-trip via importer | doc → xlsx → doc | keys/labels/translations preserved | ✅ |
| XLEXP-02 | Formula injection guarded | label `=cmd...` | prefixed with `'` on export, stripped on import | ✅ |
| XLEXP-03 | Sheet-name collision after truncation | two 28+ char component types | distinct sheet names | ✅ |
| XLEXP-04 | Forbidden chars sanitised | component with `:\/?*[]` | replaced with `_` | ⬜ |
| XLEXP-05 | Sheet name ≤ 31 chars always | very long name + many collisions | never exceeds 31 | ⬜ |
| XLEXP-06 | `Content Details` index sheet written | any doc | index lists every component sheet with counts | ⬜ |
| XLEXP-07 | One sheet per `Component_Status` group | mixed statuses | correct grouping | ⬜ |
| XLEXP-08 | Empty document | 0 entries | only `Content Details` sheet, no crash | ⬜ |
| XLEXP-09 | Type coercion prevented (`007`, `10:30`) | numeric-looking keys | stay text on round-trip | ⬜ |
| XLEXP-10 | Audit sheets appended | `write_translation_audit_sheets` | `Translation_Summary` + `Translation_Status_Log` present | ⬜ |
| XLEXP-11 | Audit sheet replace (idempotent) | call twice | no duplicate sheets | ⬜ |
| XLEXP-12 | Header row styled + frozen | any sheet | row 1 bold, `freeze_panes="A2"` | ⬜ |

## 5. `excel/importer.py` — XLSX → Document

| ID | Scenario | Setup / Input | Expected | Status |
|----|----------|---------------|----------|--------|
| XLIMP-01 | Reads via Content Details order | exporter output | sheets read in index order | ⬜ |
| XLIMP-02 | Fallback scan when no index | hand-made workbook w/ Key/Label cols | entries read | ⬜ |
| XLIMP-03 | Audit sheets skipped | workbook with audit sheets | not parsed as entries | ⬜ |
| XLIMP-04 | Missing `Translation` column | Key+Label only | translation defaults `""` | ⬜ |
| XLIMP-05 | Short/ragged rows padded | rows with trailing blanks | no `IndexError` | ⬜ |
| XLIMP-06 | `nan`/`none` cell values cleaned | merged-cell artefacts | become `""` | ⬜ |
| XLIMP-07 | Apostrophe guard stripped | `'=formula` | returns `=formula` | ⬜ |
| XLIMP-08 | Rows with empty key+label skipped | blank rows | excluded | ⬜ |
| XLIMP-09 | Sheet missing required columns ignored | a "notes" sheet | produces no entries | ⬜ |

## 6. `languages.py` — language name/code mapping

| ID | Scenario | Setup / Input | Expected | Status |
|----|----------|---------------|----------|--------|
| LANG-01 | `code_for_language` exact | `"Japanese"` | `"ja"` | ⬜ |
| LANG-02 | `code_for_language` case-insensitive | `"japanese"` | `"ja"` | ⬜ |
| LANG-03 | `code_for_language` unknown | `"Klingon"` | `None` | ⬜ |
| LANG-04 | `code_for_language` empty | `""` | `None` | ⬜ |
| LANG-05 | `language_for_code` reverse | `"ja"` | `"Japanese"` | ⬜ |
| LANG-06 | `to_google_code` Salesforce-specific | `"iw"` → `"he"`, `"in"` → `"id"` | mapped | ⬜ |
| LANG-07 | `to_google_code` regional split | `"pt_BR"` → `"pt"`, `"fr_CA"` → `"fr"` | mapped | ⬜ |
| LANG-08 | `to_google_code` unknown falls back to prefix | `"xx_YY"` → `"xx"` | prefix before `_` | ⬜ |
| LANG-09 | `supported_language_names` sorted | — | sorted list, contains "Japanese" | ⬜ |

## 7. `translate/protect.py` — token protection

| ID | Scenario | Setup / Input | Expected | Status |
|----|----------|---------------|----------|--------|
| PROT-01 | Round-trip preserves all token types | parametrised inputs | output == input | ✅ |
| PROT-02 | Pure digits NOT treated as SFID | `810225277674347` | not protected | ✅ |
| PROT-03 | 14-char identifier not an SFID | `abc123def4567x` | not protected | ✅ |
| PROT-04 | Dropped sentinel detected | translator loses token | `all_tokens_restored` → False | ✅ |
| PROT-05 | Full restore succeeds | tokens intact | True | ✅ |
| PROT-06 | URL absorbs embedded SFID | URL containing id | single token | ✅ |
| PROT-07 | MessageFormat `{0}`/`{1}` protected | sample | tokens replaced/restored | ✅ |
| PROT-08 | 15- and 18-char SFIDs both protected | both lengths | protected | ⬜ |
| PROT-09 | ALL-CAPS acronyms protected | `API`, `URL`, `WO` | preserved | ⬜ |
| PROT-10 | Escape sequences `\n` `\t` `\r` | literal escapes | preserved | ⬜ |
| PROT-11 | Email addresses protected | `a@b.com` | preserved | ⬜ |
| PROT-12 | HTML tags + attributes round-trip | `<a href=...>` | tags/attrs intact | ⬜ |
| PROT-13 | Nested/adjacent tokens | `{!A}{0}` adjacent | both restored | ⬜ |
| PROT-14 | No tokens → identity | plain sentence | unchanged, empty map | ⬜ |

## 8. `translate/factory.py` — backend registry

| ID | Scenario | Setup / Input | Expected | Status |
|----|----------|---------------|----------|--------|
| FACT-01 | `make_backend("google")` | — | `GoogleFreeTranslator` instance | ⬜ |
| FACT-02 | `make_backend` unknown key | `"nope"` | `ValueError` listing available | ⬜ |
| FACT-03 | `list_backends` order | — | google, deepl, azure, openai | ⬜ |
| FACT-04 | `BackendInfo.requires_api_key` flags | each backend | google False, others True | ⬜ |
| FACT-05 | kwargs forwarded to constructor | api_key passed | reaches backend | ⬜ |
| FACT-06 | Lazy import doesn't fail when SDK absent | deepl/azure/openai | only fails at construction, not at registry import | ⬜ |

## 9. Translator backends (`google_free`, `deepl_paid`, `azure`, `openai_llm`)

| ID | Scenario | Setup / Input | Expected | Status |
|----|----------|---------------|----------|--------|
| BACK-01 | Google: long text chunked (>5000 chars) | 6000-char label | split on sentence boundaries, recombined | ⬜ |
| BACK-02 | Google: protect integration | text w/ SFID | id not sent raw to network (mock) | ⬜ |
| BACK-03 | Google: retry/backoff on 429 (mock) | mocked rate error | retries then falls back to source | ⬜ |
| BACK-04 | DeepL: missing key raises clear error | no key/env | informative error | ⬜ |
| BACK-05 | Azure: missing key/region error | no creds | informative error | ⬜ |
| BACK-06 | OpenAI: SDK not installed → friendly error | uninstalled | `ImportError` surfaced cleanly | ⬜ |
| BACK-07 | All backends honour `Translator` protocol | signature check | `translate(text, src, tgt)` present | ⬜ |

> Backends that hit the network should be tested with **mocks** (e.g.
> `responses`/`unittest.mock`) so the suite stays offline and deterministic.

## 10. `translate/rate_limit.py`

| ID | Scenario | Setup / Input | Expected | Status |
|----|----------|---------------|----------|--------|
| RATE-01 | Token bucket burst then paces | capacity 3 | 4th acquire waits | ✅ |
| RATE-02 | Adaptive grows on success, shrinks on failure | report success/failure | bounded by min/max | ✅ |
| RATE-03 | Capacity never < min | many failures | ≥ min | ✅ (within RATE-02) |
| RATE-04 | Capacity never > max | many successes | ≤ max | ✅ (within RATE-02) |
| RATE-05 | Thread-safety under concurrent acquire | N threads | no over-issue beyond capacity | ⬜ |

## 11. `translate/runner.py` — orchestration

| ID | Scenario | Setup / Input | Expected | Status |
|----|----------|---------------|----------|--------|
| RUN-01 | Dedup: one call per unique label | 20 entries, 2 unique | 2 translator calls, deduped_count=18 | ✅ |
| RUN-02 | No gaps in statuses | parallel run | one status per entry | ✅ |
| RUN-03 | Scope blocks out-of-scope components | scope filter | out-of-scope skipped | ✅ |
| RUN-04 | TM serves repeated runs | warm TM | 0 network calls, cached_count>0 | ✅ |
| RUN-05 | Glossary DNT protected through translation | upper-casing translator | term unchanged | ✅ |
| RUN-06 | Parallel workers produce same result as serial | workers 1 vs 4 | identical output | ⬜ |
| RUN-07 | Cancellation stops further calls | cancel mid-run | remaining rows not translated | ⬜ |
| RUN-08 | Progress events carry source+translation+eta | capture callbacks | fields populated | ⬜ |
| RUN-09 | Single-shot guard (no double run) | call run twice on same instance | guarded / raises | ⬜ |
| RUN-10 | `translate_document_multi` (batch) | targets ja,fr,de | one output set per language | ⬜ |
| RUN-11 | Token rollback on sentinel loss | translator drops `{!X}` | row rolled back to source | ⬜ |
| RUN-12 | Forced glossary translation applied | `case→ケース` | replacement present | ⬜ |
| RUN-13 | Rate limiter engaged when configured | `rate_limit_per_second=5` | paced (timing) | ⬜ |
| RUN-14 | Wake-lock engaged for run duration | `prevent_system_sleep=True` (mock) | acquire+release called | ⬜ |
| RUN-15 | Translator exception on one row doesn't abort all | one row raises | row marked error, others succeed | ⬜ |

## 12. `scope.py` — component/key filtering

| ID | Scenario | Status |
|----|----------|--------|
| SCOPE-01..09 | default-all, component filter, include exact, include glob, exclude-wins, status filter, JSON round-trip, discover sidecar, all_components_of | ✅ (all covered in test_scope.py) |
| SCOPE-10 | Invalid glob pattern handled | ⬜ |
| SCOPE-11 | `discover` returns None when no sidecar | ⬜ |
| SCOPE-12 | Load malformed JSON → clear error | ⬜ |

## 13. `memory.py` — translation memory (SQLite)

| ID | Scenario | Status |
|----|----------|--------|
| MEM-01..05 | round-trip, persistence, hit counting, clear, target-lang isolation | ✅ |
| MEM-06 | source-lang isolation (en vs de) | ⬜ |
| MEM-07 | Overwrite existing key updates value | ⬜ |
| MEM-08 | Corrupt/locked DB handled gracefully | ⬜ |
| MEM-09 | Unicode keys/values stored correctly | ⬜ |
| MEM-10 | Concurrent writers (WAL) don't corrupt | ⬜ |

## 14. `glossary.py`

| ID | Scenario | Status |
|----|----------|--------|
| GLOS-01..05 | DNT protect, forced translation, case-insensitive match, CSV round-trip, inactive rows dropped | ✅ |
| GLOS-06 | Forced translation: whole-word only (no substring mid-word) | ⬜ |
| GLOS-07 | Multiple terms in one string all applied | ⬜ |
| GLOS-08 | Overlapping terms — deterministic precedence | ⬜ |
| GLOS-09 | CSV with extra/missing columns tolerated | ⬜ |
| GLOS-10 | Empty glossary → identity | ⬜ |

## 15. `validate.py`

| ID | Scenario | Status |
|----|----------|--------|
| VAL-01 | Duplicate keys flagged (error) | ✅ |
| VAL-02 | Length limit violation (CustomField 80) | ✅ |
| VAL-03 | Token drift (placeholder dropped) | ✅ |
| VAL-04 | HTML mismatch (warning) | ✅ |
| VAL-05 | Clean document → no issues | ✅ |
| VAL-06 | MessageFormat token drift flagged | ⬜ |
| VAL-07 | Unknown component type → length check skipped | ⬜ |
| VAL-08 | Multiple placeholders, reordered, still valid | ⬜ |
| VAL-09 | `by_category()` grouping | ⬜ |
| VAL-10 | 🐞 `empty_translation` category **never emitted** (dead code — early return) | ⬜ 🐞 |
| VAL-11 | Length exactly at limit (boundary) not flagged | ⬜ |

## 16. `autofix.py`

| ID | Scenario | Status |
|----|----------|--------|
| AF-01..09 | restore placeholders, no-op when present, restore msgfmt, trim length, no-op within limit, strip whitespace, dedup keeps last, combine all, per-entry descriptions | ✅ |
| AF-10 | `fix_restore_html_tags` wraps single missing tag pair | ⬜ |
| AF-11 | Trim truncates on word boundary + ellipsis | ⬜ (partially in AF trim) |
| AF-12 | Fixer returns None when it can't help confidently | ⬜ |
| AF-13 | `auto_fix_document` re-validates clean afterwards | ⬜ |
| AF-14 | Idempotency — running autofix twice changes nothing the 2nd time | ⬜ |

## 17. `wakelock.py`

| ID | Scenario | Setup | Expected | Status |
|----|----------|-------|----------|--------|
| WAKE-01 | Platform dispatch (mac/win/linux) | mock `sys.platform` | correct strategy chosen | ⬜ |
| WAKE-02 | Context-manager acquire/release | `with wakelock():` | enter/exit calls underlying API (mocked) | ⬜ |
| WAKE-03 | No-op / graceful when tool missing | mock missing `caffeinate` | no crash, logs and continues | ⬜ |
| WAKE-04 | Disabled flag → no system call | `enabled=False` | nothing invoked | ⬜ |

## 18. `cli.py` — Typer commands (use `typer.testing.CliRunner`)

| ID | Command | Scenario | Expected | Status |
|----|---------|----------|----------|--------|
| CLI-01 | `stx info FILE` | parse + show metadata | exit 0, prints counts | ⬜ |
| CLI-02 | `stx stf2xlsx IN OUT` | convert | xlsx created | ⬜ |
| CLI-03 | `stx xlsx2stf IN OUTDIR` | convert back | 3 stf files | ⬜ |
| CLI-04 | `stx translate IN OUT --target ja` (mock backend) | translate | output workbook written | ⬜ |
| CLI-05 | `stx validate FILE` | report | exit code reflects errors | ⬜ |
| CLI-06 | `stx run IN OUT --skip-translation` | full pipeline no network | artifacts produced | ⬜ |
| CLI-07 | `stx run --targets ja,fr,de` | multi-language | per-language output dirs | ⬜ |
| CLI-08 | `stx scope new/show` | scope file lifecycle | file created/displayed | ⬜ |
| CLI-09 | `stx backends` | list | shows 4 backends + key requirements | ⬜ |
| CLI-10 | `stx --version` | version callback | prints version, exits | ⬜ |
| CLI-11 | Missing file → friendly error, non-zero exit | bad path | error message, exit≠0 | ⬜ |
| CLI-12 | `--backend deepl` without key | clear failure | informative message | ⬜ |

## 19. GUI (`gui/*`) — use `pytest-qt` + `QT_QPA_PLATFORM=offscreen`

| ID | Area | Scenario | Expected | Status |
|----|------|----------|----------|--------|
| GUI-01 | `MainWindow` constructs | instantiate | 6 pages, no exception | ⬜ |
| GUI-02 | `state.py` AppState transitions | set document | signals fire, stats update | ⬜ |
| GUI-03 | `settings.py` persistence | set+get key | value survives round-trip (QSettings mocked/temp) | ⬜ |
| GUI-04 | `workers.py` runs off UI thread | start worker | `finished`/`error` signals emitted | ⬜ |
| GUI-05 | `theme.py` builds QSS for all 5 palettes | each palette | no unresolved `{}` placeholders | ⬜ (manually verified this session) |
| GUI-06 | Phase 1 import wires file → state | load sample | metadata populated | ⬜ |
| GUI-07 | Phase 4 editor edit → applies to entry | edit + Apply | document updated | ⬜ |
| GUI-08 | Phase 5 auto-fix all → re-validate clean | issues doc | report clears | ⬜ |
| GUI-09 | Drag-and-drop routing by extension | drop `.stf`/`.xlsx` | correct phase activated | ⬜ |
| GUI-10 | `clamp_to_screen` respects available geometry | tiny screen mock | size capped | ⬜ |
| GUI-11 | About/User-guide dialogs construct | open both | render without error | ⬜ |
| GUI-12 | Multi-click protection on action buttons | rapid clicks | work not stacked | ⬜ |

## 20. Integration / End-to-End

| ID | Scenario | Expected | Status |
|----|----------|----------|--------|
| E2E-01 | STF → Excel → STF byte/data preservation | all keys/labels retained | ✅ (test_stf_then_excel_then_stf) |
| E2E-02 | Full pipeline with mock translator (no network) | translated STF emitted | ⬜ |
| E2E-03 | Real 36k-row sample round-trips losslessly | row count preserved | ⬜ (manual; add as slow/marked test) |
| E2E-04 | Translate → validate → autofix → export clean | final STF passes validation | ⬜ |
| E2E-05 | External hand-edited xlsx → Phase 6 → STF | direct convert works | ⬜ |
| E2E-06 | Resume run with warm TM is near-instant | timing/calls drop | ⬜ |

## 21. Non-functional

| ID | Scenario | Expected | Status |
|----|----------|----------|--------|
| NFR-01 | Encoding: UTF-8, LF, no BOM on all STF outputs | byte-checked | ✅ (partial) |
| NFR-02 | Large file (36k rows) memory/time within budget | no OOM, completes | ⬜ |
| NFR-03 | Parallelism determinism (workers don't reorder entries) | stable order | ⬜ |
| NFR-04 | Long label (>5000 chars) handled without truncation loss | chunked + recombined | ⬜ |
| NFR-05 | Unicode throughout (CJK, RTL Arabic/Hebrew) | preserved end-to-end | ⬜ |
| NFR-06 | PyInstaller bundle imports `stx.gui.app` | smoke-launch exits cleanly past import | ⬜ (verified manually this session) |

---

## Known issues / observations surfaced while writing this plan

1. **🐞 `validate.py` dead code (VAL-10).** In `_check_entry`, the function
   returns early when `not entry.translation.strip()`. The later
   `empty_translation` branch (`if entry.translation and not
   entry.translation.strip()`) is therefore unreachable — the
   `empty_translation` category documented in the module docstring is
   never emitted. Either remove the dead branch or move the check before
   the early return.

2. **Backends need mock-based tests.** `google_free`, `deepl_paid`,
   `azure`, `openai_llm` have zero tests. They hit the network, so use
   `unittest.mock` / `responses` to assert chunking, retry, and
   protect-integration without real calls.

3. **No GUI tests at all.** Add `pytest-qt` to the dev extra and run with
   `QT_QPA_PLATFORM=offscreen`. Even smoke-construction tests (GUI-01,
   GUI-11) would catch import/layout regressions like the ones hit this
   session.

4. **No CLI tests.** Typer ships `CliRunner`; CLI-01..12 are cheap and
   high-value (they exercise the whole stack through the public surface).

5. **`languages.py` and `wakelock.py` untested.** Both are small, pure,
   and trivial to cover.

## Recommended tooling additions

- `pytest-qt` (GUI), `pytest-cov` (coverage gate, e.g. fail under 85% on
  `stx` excluding `gui`), `responses` or `respx` (HTTP mocking).
- Mark slow/large-sample tests with `@pytest.mark.slow` and exclude from
  the default fast run (`pytest -m "not slow"`).
- Add a `conftest.py` with shared fixtures: `sample_doc`, `tmp_stf`,
  `mock_translator`, `temp_tm`, `qapp` (offscreen).
