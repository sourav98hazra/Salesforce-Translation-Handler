"""Command line interface for the Salesforce Translation Handler.

The CLI exposes every phase of the workflow individually so it can be
scripted into CI, plus a ``run`` convenience command that performs the
full pipeline in one invocation.

Examples
--------
::

    # Phase 1+2: STF -> organised Excel
    stx stf2xlsx input.stf organized.xlsx

    # Phase 3: translate the Excel
    stx translate organized.xlsx translated.xlsx --target ja

    # Phase 5: Excel -> three STF files
    stx xlsx2stf translated.xlsx ./output --language Japanese

    # Convenience: do everything in one go
    stx run input.stf ./output --target ja --language Japanese

    # Launch the desktop GUI
    stx gui
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from . import __version__
from .excel import (
    export_document_to_excel,
    import_document_from_excel,
    write_translation_audit_sheets,
)
from .languages import code_for_language, language_for_code, to_google_code
from .stf import parse_stf, write_stf_files
from .translate import (
    GoogleFreeTranslator,
    TranslationProgress,
    translate_document,
)
from .validate import validate_document

app = typer.Typer(
    name="stx",
    help="Salesforce Translation Handler -- STF <-> Excel <-> Translate pipeline.",
    no_args_is_help=True,
    add_completion=False,
)
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
    table.add_row("Total rows", str(stats["total"]))
    table.add_row("Translated", str(stats["translated"]))
    table.add_row("Untranslated", str(stats["untranslated"]))
    table.add_row("Components", str(stats["components"]))
    console.print(table)


@app.command("stf2xlsx")
def stf2xlsx(
    stf_path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True, help="Input STF file."),
    xlsx_path: Path = typer.Argument(..., dir_okay=False, help="Output organised .xlsx file."),
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
        None,
        "--language",
        "-l",
        help="Human-readable language name (auto-derived from --target if omitted).",
    ),
) -> None:
    """Phase 3: translate every untranslated row in an organised Excel workbook."""

    if language_name is None:
        language_name = language_for_code(target) or target

    console.print(
        f"Translating [bold]{xlsx_in}[/bold] from [cyan]{source}[/cyan] -> "
        f"[cyan]{target}[/cyan] ({language_name})"
    )

    doc = import_document_from_excel(xlsx_in, language=language_name, language_code=target)
    translator = GoogleFreeTranslator()
    google_source = to_google_code(source)
    google_target = to_google_code(target)

    result = _run_translation_with_progress(doc, translator, google_source, google_target)

    # Write output workbook including audit sheets.
    export_document_to_excel(doc, xlsx_out)
    write_translation_audit_sheets(
        xlsx_out,
        summary_rows=[s.as_audit_row() for s in result.summaries],
        status_rows=[s.as_audit_row() for s in result.statuses],
    )

    console.print(
        f"[green]OK[/green] Translation completed!\n"
    )
    console.print(result.format_summary())


@app.command("xlsx2stf")
def xlsx2stf(
    xlsx_in: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    output_dir: Path = typer.Argument(..., file_okay=False),
    language_name: Optional[str] = typer.Option(
        None,
        "--language",
        "-l",
        help="Human-readable language name (e.g. 'Japanese').",
    ),
    language_code: Optional[str] = typer.Option(
        None,
        "--code",
        "-c",
        help="Salesforce language code (e.g. 'ja'). Auto-derived from --language if omitted.",
    ),
) -> None:
    """Phase 5: write the three STF files (full / translated / untranslated)."""

    if language_code is None and language_name is not None:
        language_code = code_for_language(language_name)
    if language_name is None and language_code is not None:
        language_name = language_for_code(language_code) or language_code

    if not language_name or not language_code:
        console.print(
            "[red]Error:[/red] supply --language and/or --code "
            "(at least one must be recognised).",
            highlight=False,
        )
        raise typer.Exit(code=2)

    doc = import_document_from_excel(
        xlsx_in,
        language=language_name,
        language_code=language_code,
    )
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
    target: str = typer.Option("ja", "--target", "-t", help="Target language code."),
    source: str = typer.Option("en", "--source", "-s", help="Source language code."),
    language_name: Optional[str] = typer.Option(
        None,
        "--language",
        "-l",
        help="Human-readable language name. Auto-derived from --target if omitted.",
    ),
    skip_translation: bool = typer.Option(
        False,
        "--skip-translation",
        help="Convert STF -> Excel -> STF without invoking the translator (round-trip test).",
    ),
) -> None:
    """Run the full pipeline: STF -> Excel -> Translate -> Excel -> STF.

    Every phase writes its artifact to ``OUTPUT_DIR`` so you can verify
    intermediates without relying on the GUI.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    if language_name is None:
        language_name = language_for_code(target) or target

    organised = output_dir / "01_organized.xlsx"
    translated = output_dir / "02_translated.xlsx"

    console.rule("[bold]Phase 1+2: parse STF and export Excel[/bold]")
    doc = parse_stf(stf_in)
    if not doc.language:
        doc.language = language_name
    if not doc.language_code:
        doc.language_code = target
    export_document_to_excel(doc, organised)
    console.print(f"  [green]written[/green] {organised}")

    if not skip_translation:
        console.rule("[bold]Phase 3: translate[/bold]")
        translator = GoogleFreeTranslator()
        result = _run_translation_with_progress(
            doc,
            translator,
            to_google_code(source),
            to_google_code(target),
        )
        export_document_to_excel(doc, translated)
        write_translation_audit_sheets(
            translated,
            summary_rows=[s.as_audit_row() for s in result.summaries],
            status_rows=[s.as_audit_row() for s in result.statuses],
        )
        console.print(
            f"  [green]written[/green] {translated}\n"
        )
        console.print(result.format_summary())
    else:
        console.print("[yellow]skipping translation as requested[/yellow]")

    console.rule("[bold]Phase 5: STF export[/bold]")
    stf_res = write_stf_files(doc, output_dir, language_name=language_name, language_code=target)
    for path in stf_res.as_list():
        console.print(f"  [green]written[/green] {path}")


@app.command("validate")
def validate(
    source: Path = typer.Argument(..., exists=True, help="STF or .xlsx file to validate."),
    language_code: Optional[str] = typer.Option(
        None,
        "--code",
        "-c",
        help="Salesforce language code (only required for .xlsx input).",
    ),
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


@app.command("gui")
def launch_gui() -> None:
    """Launch the desktop GUI (requires the ``[gui]`` extra)."""

    try:
        from .gui.app import main  # noqa: WPS433 - intentional lazy import
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

def _run_translation_with_progress(doc, translator, source: str, target: str):
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task_id = progress.add_task("Translating", total=len(doc.entries))

        def on_progress(event: TranslationProgress) -> None:
            progress.update(
                task_id,
                completed=event.completed,
                description=f"Translating {event.sheet}",
            )

        return translate_document(
            doc,
            translator,
            source_lang=source,
            target_lang=target,
            progress=on_progress,
        )


if __name__ == "__main__":  # pragma: no cover
    app()
