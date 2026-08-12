"""Command line entry point.

    boardbook parse    <agenda.txt>                       -> structured agenda JSON
    boardbook build    --agenda <agenda.json> ...          -> final board book PDF
    boardbook generate <agenda.txt> ...                    -> parse + build in one step
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Tuple

import click

from boardbook.models import Agenda, AttachmentSpec, BuildRequest, TemplateStyle
from boardbook.pipeline import build_board_book, parse_text_to_agenda

_ATTACHMENT_HELP = (
    'Supporting PDF: "ITEM_NUMBER:PATH" attaches to the item itself; '
    '"ITEM_NUMBER.SUB_NUMBER:PATH" attaches to one of its sub-items (1-based, e.g. "6.1" for the '
    "first sub-item of item 6 - see `boardbook parse` output for sub-item order). Repeatable; order "
    "is preserved within each item/sub-item."
)
_STYLE_HELP = "Path to a TemplateStyle JSON file overriding fonts/sizes per role (see README)."


def _parse_attachment_arg(value: str) -> AttachmentSpec:
    """Parse a repeatable `--attachment "ITEM_NUMBER[.SUB_NUMBER]:PATH"` CLI argument."""
    if ":" not in value:
        raise click.BadParameter(
            f"expected 'ITEM_NUMBER[.SUB_NUMBER]:PATH', got {value!r} (missing ':')", param_hint="--attachment"
        )
    ref_str, _, path_str = value.partition(":")
    ref_str = ref_str.strip()

    sub_item_index: Optional[int] = None
    if "." in ref_str:
        item_str, _, sub_str = ref_str.partition(".")
        try:
            item_number = int(item_str.strip())
            sub_number = int(sub_str.strip())
        except ValueError as exc:
            raise click.BadParameter(
                f"expected 'ITEM_NUMBER.SUB_NUMBER:PATH', got {value!r}", param_hint="--attachment"
            ) from exc
        if sub_number < 1:
            raise click.BadParameter(
                f"sub-item number must be 1 or greater, got {sub_number} in {value!r}", param_hint="--attachment"
            )
        sub_item_index = sub_number - 1
    else:
        try:
            item_number = int(ref_str)
        except ValueError as exc:
            raise click.BadParameter(
                f"item number must be an integer, got {ref_str!r} in {value!r}", param_hint="--attachment"
            ) from exc

    path = Path(path_str.strip()).expanduser()
    if not path.exists():
        raise click.BadParameter(f"attachment file not found: {path}", param_hint="--attachment")
    return AttachmentSpec(item_number=item_number, sub_item_index=sub_item_index, path=path)


def _load_style_option(style_path: Optional[Path]) -> Optional[TemplateStyle]:
    if style_path is None:
        return None
    return TemplateStyle.model_validate_json(style_path.read_text(encoding="utf-8"))


@click.group()
@click.version_option()
def cli() -> None:
    """Automated Board Book Generator."""


@cli.command()
@click.argument("agenda_text_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-o", "--output", "output_path", type=click.Path(path_type=Path), default=None, help="Write structured agenda JSON here instead of stdout.")
@click.option("--meeting-date", type=click.DateTime(formats=["%Y-%m-%d"]), default=None, help="Anchor date (YYYY-MM-DD) used to compute item clock times. Defaults to today.")
@click.option("--model", default=None, help="Override the Claude model used for extraction (default: claude-opus-5).")
@click.option("--committee", "committee_name", default=None, help="Committee name to use instead of whatever Claude extracts from the text (e.g. one of boardbook.committees.GFC_COMMITTEES).")
def parse(agenda_text_file: Path, output_path: Optional[Path], meeting_date, model: Optional[str], committee_name: Optional[str]) -> None:
    """Parse freeform agenda text into structured JSON with computed start times."""
    raw_text = agenda_text_file.read_text(encoding="utf-8")
    agenda = parse_text_to_agenda(
        raw_text,
        meeting_date=meeting_date.date() if meeting_date else None,
        model=model,
        committee_name=committee_name,
    )
    payload = agenda.model_dump_json(indent=2)

    if output_path:
        output_path.write_text(payload, encoding="utf-8")
        click.echo(f"Wrote structured agenda to {output_path}")
    else:
        click.echo(payload)


@cli.command()
@click.option("--agenda", "agenda_json_file", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path), help="Structured agenda JSON produced by `boardbook parse`.")
@click.option("-o", "--output", "output_path", required=True, type=click.Path(path_type=Path), help="Where to write the final board book PDF.")
@click.option("--logo", "logo_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None, help="Institution logo image (top-left of the header).")
@click.option("--attachment", "attachment_args", multiple=True, help=_ATTACHMENT_HELP)
@click.option("--style", "style_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None, help=_STYLE_HELP)
def build(
    agenda_json_file: Path,
    output_path: Path,
    logo_path: Optional[Path],
    attachment_args: Tuple[str, ...],
    style_path: Optional[Path],
) -> None:
    """Compile a final board book PDF from a structured agenda JSON plus attachments."""
    agenda = Agenda.model_validate_json(agenda_json_file.read_text(encoding="utf-8"))
    attachments = [_parse_attachment_arg(a) for a in attachment_args]

    request = BuildRequest(
        agenda=agenda,
        logo_path=logo_path,
        attachments=attachments,
        output_path=output_path,
        style=_load_style_option(style_path),
    )
    result_path = build_board_book(request)
    click.echo(f"Board book written to {result_path}")


@cli.command()
@click.argument("agenda_text_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-o", "--output", "output_path", required=True, type=click.Path(path_type=Path), help="Where to write the final board book PDF.")
@click.option("--logo", "logo_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None, help="Institution logo image (top-left of the header).")
@click.option("--attachment", "attachment_args", multiple=True, help=_ATTACHMENT_HELP)
@click.option("--meeting-date", type=click.DateTime(formats=["%Y-%m-%d"]), default=None, help="Anchor date (YYYY-MM-DD) used to compute item clock times. Defaults to today.")
@click.option("--model", default=None, help="Override the Claude model used for extraction (default: claude-opus-5).")
@click.option("--committee", "committee_name", default=None, help="Committee name to use instead of whatever Claude extracts from the text (e.g. one of boardbook.committees.GFC_COMMITTEES).")
@click.option("--style", "style_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None, help=_STYLE_HELP)
def generate(
    agenda_text_file: Path,
    output_path: Path,
    logo_path: Optional[Path],
    attachment_args: Tuple[str, ...],
    meeting_date,
    model: Optional[str],
    committee_name: Optional[str],
    style_path: Optional[Path],
) -> None:
    """One-shot: parse freeform agenda text and build the final board book PDF."""
    raw_text = agenda_text_file.read_text(encoding="utf-8")
    agenda = parse_text_to_agenda(
        raw_text,
        meeting_date=meeting_date.date() if meeting_date else None,
        model=model,
        committee_name=committee_name,
    )
    attachments = [_parse_attachment_arg(a) for a in attachment_args]
    request = BuildRequest(
        agenda=agenda,
        logo_path=logo_path,
        attachments=attachments,
        output_path=output_path,
        style=_load_style_option(style_path),
    )
    result_path = build_board_book(request)
    click.echo(f"Board book written to {result_path}")


@cli.command()
def doctor() -> None:
    """Check the local environment for common setup problems.

    Verifies the interpreter this command is actually running under, that
    every required dependency is importable, that headless Chromium is
    installed for Playwright, and that Anthropic credentials are resolvable
    - each with the exact fix if it fails. Most "it doesn't work" reports
    trace back to one of these (usually: a fresh terminal that never
    activated the virtualenv).
    """
    failures = 0
    warnings = 0

    def ok(msg: str) -> None:
        click.echo(f"  [OK]   {msg}")

    def fail(msg: str, fix: str) -> None:
        nonlocal failures
        failures += 1
        click.echo(f"  [FAIL] {msg}")
        click.echo(f"         Fix: {fix}")

    def warn(msg: str, fix: str) -> None:
        nonlocal warnings
        warnings += 1
        click.echo(f"  [WARN] {msg}")
        click.echo(f"         Fix: {fix}")

    click.echo("Board Book Generator - environment check\n")

    # 1. Interpreter / venv sanity
    click.echo(f"Python: {sys.version.split()[0]} ({sys.executable})")
    if sys.version_info < (3, 9):
        fail("Python 3.9+ is required.", "Install Python 3.9 or newer and recreate the virtualenv.")
    else:
        ok("Python version is >= 3.9")
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    if in_venv:
        ok(f"Running inside a virtualenv ({sys.prefix})")
    else:
        warn(
            "Not running inside a virtualenv - this is almost always the cause of "
            "'command not found: boardbook' or 'ModuleNotFoundError: No module named boardbook'.",
            "source .venv/bin/activate  (create one first with: python3 -m venv .venv)",
        )

    # 2. Required packages importable
    click.echo("\nDependencies:")
    for module_name, pip_name in (
        ("anthropic", "anthropic"),
        ("pydantic", "pydantic"),
        ("jinja2", "jinja2"),
        ("playwright", "playwright"),
        ("pypdf", "pypdf"),
        ("reportlab", "reportlab"),
        ("click", "click"),
        ("fastapi", "fastapi"),
        ("streamlit", "streamlit"),
    ):
        try:
            __import__(module_name)
            ok(module_name)
        except ImportError:
            fail(f"'{module_name}' is not installed.", 'pip install -e ".[dev]"  (from the project root)')

    # 2b. Pydantic schema generation - this is what Claude's structured-output
    # call relies on, and it is known to crash on some broken Python builds
    # (observed: an old python.org 3.9.0 install shadowing the system Python
    # in PATH), surfacing only as a cryptic runtime error deep in the app.
    click.echo("\nPydantic schema generation (used by Claude's structured outputs):")
    try:
        from boardbook.parser.schema import ExtractedAgenda

        ExtractedAgenda.model_json_schema()
        ok("Pydantic can build a JSON schema from the agenda model")
    except AttributeError as exc:
        fail(
            f"Pydantic's JSON schema builder crashed ({exc}).",
            "This Python interpreter's `typing` module is broken (seen on some old "
            "python.org 3.9.0 builds shadowing the system Python in PATH). Recreate the "
            "venv with a different interpreter, e.g.: rm -rf .venv && /usr/bin/python3 -m "
            'venv .venv && source .venv/bin/activate && pip install -e ".[dev]"',
        )
    except ImportError:
        pass  # already reported by the dependency loop above
    except Exception as exc:  # noqa: BLE001 - surfacing to the user, not handling
        fail(f"Unexpected error building the agenda schema: {exc}", 'Run `pip install -e ".[dev]"` again.')

    # 3. Headless Chromium (needed to render the agenda cover page)
    click.echo("\nAgenda rendering (Playwright + headless Chromium):")
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()
            browser.close()
        ok("Headless Chromium launches successfully")
    except ImportError:
        fail("Playwright is not installed.", 'pip install -e ".[dev]"')
    except Exception as exc:  # noqa: BLE001 - surfacing to the user, not handling
        fail(f"Could not launch headless Chromium ({exc}).", "playwright install chromium")

    # 4. Anthropic credentials
    click.echo("\nAnthropic credentials:")
    import os

    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        ok("ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN is set")
    else:
        warn(
            "No ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN in the environment.",
            "cp .env.example .env and set ANTHROPIC_API_KEY=..., or run `ant auth login`.",
        )

    click.echo(f"\n{failures} failing, {warnings} warning(s).")
    if failures:
        click.echo("Fix the [FAIL] items above, then re-run `boardbook doctor`.")
        sys.exit(1)
    click.echo("Environment looks good.")


def main() -> None:
    try:
        cli()
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
