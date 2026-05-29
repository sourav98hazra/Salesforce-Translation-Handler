"""Command line interface for the Salesforce Translation Manager.

The CLI mirrors every GUI phase plus a ``run`` convenience command that
performs the full pipeline.  v1.1 adds:

* ``--backend`` (google / deepl / azure / openai) for the ``translate`` /
  ``run`` commands.
* ``--scope-file`` to apply a saved component / key scope.
* ``--glossary`` to apply a glossary CSV.
* ``--memory-db`` to enable the persistent translation memory.
* ``--workers`` and ``--rate-limit`` for performance tuning.
* ``--targets`` for multi-language batch runs.
* ``stx scope`` subcommand to inspect / build scope files.

Examples
--------
::

    # Phase 1+2: STF -> organised Excel
    stx stf2xlsx input.stf organized.xlsx

    # Phase 3 with all v1.1 features
    stx translate organized.xlsx translated.xlsx \\
        --target ja \\
        --backend google \\
        --scope-file input.stxscope.json \\
        --glossary glossary.csv \\
        --memory-db tm.sqlite \\
        --workers 8

    # Multi-language batch in one go
    stx run input.stf ./out --targets ja,fr,de,es

    # Pre-export validation
    stx validate input.stf

    # Build a scope file from a document
    stx scope new input.stf scope.stxscope.json --components CustomLabel,ButtonOrLink
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from . import __version__
from .excel import (
    export_document_to_excel,
    import_document_from_excel,
    write_translation_audit_sheets,
)
from .glossary import Glossary
from .languages import code_for_language, language_for_code, to_google_code
from .memory import TranslationMemory
from .scope import Scope, StatusFilter
from .stf import parse_stf, write_stf_files
from .translate import (
    TranslationProgress,
    list_backends,
    make_backend,
    translate_document,
    translate_document_multi,
)
from .validate import validate_document

app = typer.Typer(
    name="stx",
    help="Salesforce Translation Manager -- STF <-> Excel <-> Translate pipeline.",
    no_args_is_help=True,
    add_completion=False,
)
scope_app = typer.Typer(
    name="scope",
    help="Inspect / build translation scope files (.stxscope.json).",
    no_args_is_help=True,
)
app.add_typer(scope_app)

console = Console()


# ---------------------------------------------------------------------------
# Top-level options
# ---------------------------------------------------------------------------

def _version_callback(value: bool) -> None:
    if value:
        console.print(f"stx {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable debug logging.",
    ),
) -> None:
    """Configure logging and global options."""

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


# ---------------------------------------------------------------------------
# Phase commands
# ---------------------------------------------------------------------------

@app.command("info")
def info(
    stf_path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
) -> None:
    """Show metadata and counts for an STF file without converting anything."""

    doc = parse_stf(stf_path)
    stats = doc.stats()

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Language", doc.language or "(unknown)")
    table.add_row("Language code", doc.language_code or "(unknown)")
    table.add_row("STF type", doc.stf_type)
    table.add_row("Translation type", doc.translation_type)
    table.add_row("Total rows", f"{stats['total']:,}")
    table.add_row("Translated", f"{stats['translated']:,}")
    table.add_row("Untranslated", f"{stats['untranslated']:,}")
    table.add_row("Components", str(stats["components"]))
    console.print(table)

    components = sorted({e.component_type for e in doc.entries})
    console.print(f"\nComponent types ({len(components)}): " + ", ".join(components))


@app.command("backends")
def list_translator_backends() -> None:
    """List available translator backends and their auth requirements."""
    table = Table(title="Translator backends", show_header=True, header_style="bold cyan")
    table.add_column("Key")
    table.add_column("Label")
    table.add_column("API key")
    table.add_column("Env var")
    table.add_column("Description")
    for info in list_backends():
        table.add_row(
            info.key,
            info.label,
            "yes" if info.requires_api_key else "no",
            info.env_var or "",
            info.description,
        )
    console.print(table)


@app.command("stf2xlsx")
def stf2xlsx(
    stf_path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    xlsx_path: Path = typer.Argument(..., dir_okay=False),
) -> None:
    """Phase 1+2: convert an STF file into an organised Excel workbook."""

    doc = parse_stf(stf_path)
    result = export_document_to_excel(doc, xlsx_path)
    console.print(
        f"[green]OK[/green] Wrote {len(result.sheets_written)} sheets to "
        f"[bold]{result.path}[/bold]"
    )


@app.command("translate")
def translate(
    xlsx_in: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    xlsx_out: Path = typer.Argument(..., dir_okay=False),
    source: str = typer.Option("en", "--source", "-s", help="Source language code."),
    target: str = typer.Option("ja", "--target", "-t", help="Target language code."),
    language_name: Optional[str] = typer.Option(
        None, "--language", "-l", help="Human-readable language name."
    ),
    backend: str = typer.Option(
        "google", "--backend", "-b", help="Translator backend (google/deepl/azure/openai)."
    ),
    api_key: Optional[str] = typer.Option(
        None, "--api-key", help="API key for the backend (overrides env var)."
    ),
    scope_file: Optional[Path] = typer.Option(
        None, "--scope-file", help="Path to a .stxscope.json scope file."
    ),
    glossary_path: Optional[Path] = typer.Option(
        None, "--glossary", help="Path to a CSV glossary."
    ),
    memory_db: Optional[Path] = typer.Option(
        None, "--memory-db", help="Path to a SQLite translation memory."
    ),
    workers: int = typer.Option(
        4, "--workers", "-w", help="Concurrent translation workers."
    ),
    rate_limit: float = typer.Option(
        8.0, "--rate-limit", help="Initial token-bucket capacity (req/s).  0 = unlimited."
    ),
) -> None:
    """Phase 3: translate every untranslated row in an organised Excel workbook."""

    if language_name is None:
        language_name = language_for_code(target) or target

    console.print(
        f"Translating [bold]{xlsx_in}[/bold] from [cyan]{source}[/cyan] -> "
        f"[cyan]{target}[/cyan] ({language_name}) via [bold]{backend}[/bold]"
    )

    doc = import_document_from_excel(xlsx_in, language=language_name, language_code=target)

    backend_kwargs: dict = {}
    if api_key is not None:
        backend_kwargs["api_key"] = api_key
    translator = make_backend(backend, **backend_kwargs)

    scope = Scope.load(scope_file) if scope_file else None
    glossary = Glossary.load_csv(glossary_path) if glossary_path else None
    memory = TranslationMemory(path=memory_db) if memory_db else None

    google_source = to_google_code(source)
    google_target = to_google_code(target)
    rate = rate_limit if rate_limit > 0 else None

    result = _run_translation_with_progress(
        doc, translator, google_source, google_target,
        scope=scope, memory=memory, glossary=glossary,
        workers=workers, rate_limit_per_second=rate,
    )

    export_document_to_excel(doc, xlsx_out)
    write_translation_audit_sheets(
        xlsx_out,
        summary_rows=[s.as_audit_row() for s in result.summaries],
        status_rows=[s.as_audit_row() for s in result.statuses],
    )

    console.print(
        f"[green]OK[/green] Translated {result.translated_count:,} "
        f"(TM hits {result.cached_count:,}, dedup {result.deduped_count:,}); "
        f"skipped {result.skipped_count:,}; "
        f"elapsed {result.elapsed_seconds:.1f}s; output: [bold]{xlsx_out}[/bold]"
    )


@app.command("xlsx2stf")
def xlsx2stf(
    xlsx_in: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    output_dir: Path = typer.Argument(..., file_okay=False),
    language_name: Optional[str] = typer.Option(None, "--language", "-l"),
    language_code: Optional[str] = typer.Option(None, "--code", "-c"),
) -> None:
    """Phase 5: write the three STF files (full / translated / untranslated)."""

    if language_code is None and language_name is not None:
        language_code = code_for_language(language_name)
    if language_name is None and language_code is not None:
        language_name = language_for_code(language_code) or language_code

    if not language_name or not language_code:
        console.print("[red]Error:[/red] supply --language and/or --code (at least one must be recognised).")
        raise typer.Exit(code=2)

    doc = import_document_from_excel(xlsx_in, language=language_name, language_code=language_code)
    res = write_stf_files(doc, output_dir, language_name=language_name, language_code=language_code)

    table = Table(title="STF files written", show_header=True, header_style="bold cyan")
    table.add_column("File")
    table.add_column("Size", justify="right")
    for path in res.as_list():
        table.add_row(str(path), f"{path.stat().st_size:,} B")
    console.print(table)


@app.command("run")
def run_pipeline(
    stf_in: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    output_dir: Path = typer.Argument(..., file_okay=False),
    target: str = typer.Option("ja", "--target", "-t"),
    targets: Optional[str] = typer.Option(
        None,
        "--targets",
        help="Comma-separated additional target codes for multi-language batch.",
    ),
    source: str = typer.Option("en", "--source", "-s"),
    language_name: Optional[str] = typer.Option(None, "--language", "-l"),
    backend: str = typer.Option("google", "--backend", "-b"),
    api_key: Optional[str] = typer.Option(None, "--api-key"),
    scope_file: Optional[Path] = typer.Option(None, "--scope-file"),
    glossary_path: Optional[Path] = typer.Option(None, "--glossary"),
    memory_db: Optional[Path] = typer.Option(None, "--memory-db"),
    workers: int = typer.Option(4, "--workers", "-w"),
    rate_limit: float = typer.Option(8.0, "--rate-limit"),
    skip_translation: bool = typer.Option(False, "--skip-translation"),
) -> None:
    """Run the full pipeline: STF -> Excel -> Translate -> Excel -> STF."""

    output_dir.mkdir(parents=True, exist_ok=True)
    if language_name is None:
        language_name = language_for_code(target) or target

    organised = output_dir / "01_organized.xlsx"

    console.rule("[bold]Phase 1+2: parse STF and export Excel[/bold]")
    doc = parse_stf(stf_in)
    if not doc.language:
        doc.language = language_name
    if not doc.language_code:
        doc.language_code = target
    export_document_to_excel(doc, organised)
    console.print(f"  [green]written[/green] {organised}")

    if not skip_translation:
        targets_list = [target]
        if targets:
            extra = [t.strip() for t in targets.split(",") if t.strip()]
            for t in extra:
                if t not in targets_list:
                    targets_list.append(t)

        backend_kwargs: dict = {}
        if api_key is not None:
            backend_kwargs["api_key"] = api_key
        translator = make_backend(backend, **backend_kwargs)
        scope = Scope.load(scope_file) if scope_file else None
        glossary = Glossary.load_csv(glossary_path) if glossary_path else None
        memory = TranslationMemory(path=memory_db) if memory_db else None
        rate = rate_limit if rate_limit > 0 else None

        for target_code in targets_list:
            console.rule(f"[bold]Phase 3: translate -> {target_code}[/bold]")
            per_lang_doc = parse_stf(stf_in)
            translated_xlsx = output_dir / f"02_translated_{target_code}.xlsx"
            result = _run_translation_with_progress(
                per_lang_doc, translator,
                to_google_code(source), to_google_code(target_code),
                scope=scope, memory=memory, glossary=glossary,
                workers=workers, rate_limit_per_second=rate,
            )
            export_document_to_excel(per_lang_doc, translated_xlsx)
            write_translation_audit_sheets(
                translated_xlsx,
                summary_rows=[s.as_audit_row() for s in result.summaries],
                status_rows=[s.as_audit_row() for s in result.statuses],
            )
            console.print(
                f"  [green]written[/green] {translated_xlsx} "
                f"(translated={result.translated_count:,}, "
                f"TM hits={result.cached_count:,}, dedup={result.deduped_count:,}, "
                f"skipped={result.skipped_count:,})"
            )

            console.rule(f"[bold]Phase 5: STF export -> {target_code}[/bold]")
            tname = language_name if target_code == target else (language_for_code(target_code) or target_code)
            stf_out = output_dir / target_code if len(targets_list) > 1 else output_dir
            stf_out.mkdir(parents=True, exist_ok=True)
            stf_res = write_stf_files(per_lang_doc, stf_out, language_name=tname, language_code=target_code)
            for path in stf_res.as_list():
                console.print(f"  [green]written[/green] {path}")
    else:
        console.print("[yellow]skipping translation as requested[/yellow]")
        console.rule("[bold]Phase 5: STF export[/bold]")
        stf_res = write_stf_files(doc, output_dir, language_name=language_name, language_code=target)
        for path in stf_res.as_list():
            console.print(f"  [green]written[/green] {path}")


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------

@app.command("validate")
def validate(
    source: Path = typer.Argument(..., exists=True),
    language_code: Optional[str] = typer.Option(None, "--code", "-c"),
) -> None:
    """Run pre-export validation (duplicate keys, length limits, token drift, ...)."""

    if source.suffix.lower() == ".xlsx":
        if not language_code:
            console.print("[red]--code/-c is required when validating an Excel workbook.[/red]")
            raise typer.Exit(code=2)
        doc = import_document_from_excel(source, language_code=language_code)
    else:
        doc = parse_stf(source)

    report = validate_document(doc)
    if not report.issues:
        console.print("[green]No validation issues.[/green]")
        return

    table = Table(
        title=f"{len(report.errors)} error(s) / {len(report.warnings)} warning(s)",
        show_header=True,
        header_style="bold",
    )
    table.add_column("Severity")
    table.add_column("Category")
    table.add_column("Key")
    table.add_column("Message")
    severity_styles = {"error": "red", "warning": "yellow", "info": "cyan"}
    for issue in report.issues[:200]:
        style = severity_styles.get(issue.severity, "")
        table.add_row(
            f"[{style}]{issue.severity.upper()}[/]" if style else issue.severity.upper(),
            issue.category,
            issue.key,
            issue.message,
        )
    console.print(table)
    if len(report.issues) > 200:
        console.print(f"[yellow]... and {len(report.issues) - 200} more.[/yellow]")


# ---------------------------------------------------------------------------
# Scope subcommands
# ---------------------------------------------------------------------------

@scope_app.command("show")
def scope_show(
    path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
) -> None:
    """Pretty-print the contents of a .stxscope.json file."""
    scope = Scope.load(path)
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Name", scope.name)
    table.add_row(
        "Components",
        "ALL" if scope.components is None else ", ".join(sorted(scope.components)),
    )
    table.add_row("Status filter", scope.status.value)
    table.add_row("Include keys", str(len(scope.include_keys)))
    table.add_row("Include patterns", ", ".join(scope.include_patterns) or "(none)")
    table.add_row("Exclude keys", str(len(scope.exclude_keys)))
    table.add_row("Exclude patterns", ", ".join(scope.exclude_patterns) or "(none)")
    console.print(table)


@scope_app.command("new")
def scope_new(
    source_path: Path = typer.Argument(..., exists=True),
    output: Path = typer.Argument(..., dir_okay=False),
    components: Optional[str] = typer.Option(
        None, "--components", help="Comma-separated component types to include."
    ),
    status: str = typer.Option(
        "untranslated", "--status",
        help="Status filter: untranslated / all / translated.",
    ),
    include: Optional[str] = typer.Option(
        None, "--include", help="Comma-separated keys/patterns to allowlist."
    ),
    exclude: Optional[str] = typer.Option(
        None, "--exclude", help="Comma-separated keys/patterns to denylist."
    ),
) -> None:
    """Build a .stxscope.json scope file from a source STF / xlsx."""

    if source_path.suffix.lower() == ".xlsx":
        doc = import_document_from_excel(source_path)
    else:
        doc = parse_stf(source_path)

    if components:
        comps = {c.strip() for c in components.split(",") if c.strip()}
    else:
        comps = {e.component_type for e in doc.entries}

    inc_keys = []
    inc_patterns = []
    if include:
        for token in (t.strip() for t in include.split(",") if t.strip()):
            (inc_patterns if "*" in token or "?" in token else inc_keys).append(token)
    exc_keys = []
    exc_patterns = []
    if exclude:
        for token in (t.strip() for t in exclude.split(",") if t.strip()):
            (exc_patterns if "*" in token or "?" in token else exc_keys).append(token)

    scope = Scope(
        components=comps,
        status=StatusFilter(status),
        include_keys=inc_keys,
        include_patterns=inc_patterns,
        exclude_keys=exc_keys,
        exclude_patterns=exc_patterns,
        name=output.stem,
    )
    scope.save(output)
    estimate = scope.estimate_count(doc)
    console.print(
        f"[green]OK[/green] Scope saved to [bold]{output}[/bold] "
        f"(matches {estimate:,} of {len(doc.entries):,} rows)"
    )


# ---------------------------------------------------------------------------
# GUI launcher
# ---------------------------------------------------------------------------

@app.command("gui")
def launch_gui() -> None:
    """Launch the desktop GUI (requires the ``[gui]`` extra)."""

    try:
        from .gui.app import main  # noqa: WPS433
    except ImportError as exc:  # pragma: no cover
        console.print(
            "[red]The desktop GUI requires PySide6.[/red]\n"
            "Install it with: [bold]pip install '.[gui]'[/bold]\n"
            f"Underlying error: {exc}",
            highlight=False,
        )
        raise typer.Exit(code=1)
    main()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_translation_with_progress(
    doc, translator, source: str, target: str,
    *,
    scope=None, memory=None, glossary=None,
    workers: int = 4, rate_limit_per_second=8.0,
):
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=False,
    ) as progress:
        task_id = progress.add_task("Translating", total=len(doc.entries))

        def on_progress(event: TranslationProgress) -> None:
            extras = []
            if event.rows_per_second:
                extras.append(f"{event.rows_per_second:.1f} rows/s")
            description = f"Translating {event.sheet}"
            if extras:
                description += f"  ({', '.join(extras)})"
            progress.update(task_id, completed=event.completed, description=description)

        return translate_document(
            doc, translator,
            source_lang=source, target_lang=target,
            progress=on_progress,
            scope=scope, memory=memory, glossary=glossary,
            workers=workers, rate_limit_per_second=rate_limit_per_second,
        )


if __name__ == "__main__":  # pragma: no cover
    app()
