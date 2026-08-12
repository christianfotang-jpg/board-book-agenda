"""Orchestrates the full run: freeform text -> structured agenda -> cover PDF
-> merged + stamped board book. Each stage is also independently importable
(and independently testable) from its own module - this module just wires
them together in the order the spec describes.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional, Sequence

from boardbook.compiler import merge_board_book, stamp_page_numbers
from boardbook.models import Agenda, AttachmentSpec, BuildRequest, TemplateStyle
from boardbook.parser import apply_schedule, parse_agenda_text
from boardbook.template import render_agenda_pdf


def parse_text_to_agenda(
    raw_text: str,
    *,
    meeting_date: Optional[date] = None,
    model: Optional[str] = None,
    committee_name: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Agenda:
    """Stage 1 - INPUT PARSER: freeform text -> structured Agenda with computed start times.

    `committee_name`, when given, overrides whatever committee name Claude
    extracted from the text - e.g. a value picked from a fixed dropdown
    (see boardbook.committees.GFC_COMMITTEES) rather than relying on the
    source text spelling it out consistently.

    `api_key`, when given, is used for this call only rather than the
    server's own credentials - see parser.claude_client.parse_agenda_text for
    why this matters on a shared/multi-user deployment.
    """
    extracted = parse_agenda_text(raw_text, model=model, api_key=api_key)
    agenda = apply_schedule(extracted, meeting_date=meeting_date)
    if committee_name:
        agenda.meta.committee_name = committee_name
    return agenda


def build_board_book(request: BuildRequest) -> Path:
    """Stages 2 & 3 - AGENDA TEMPLATE + PDF COMPILER & STAMPER.

    Renders the agenda cover page, merges it with the requested attachments
    in agenda order, stamps "Page X of Y" on every resulting page, and
    writes the finished board book to `request.output_path`.
    """
    cover_pdf = render_agenda_pdf(request.agenda, logo_path=request.logo_path, style=request.style)
    merged_pdf = merge_board_book(cover_pdf, request.agenda, request.attachments)
    final_pdf = stamp_page_numbers(merged_pdf)

    request.output_path.parent.mkdir(parents=True, exist_ok=True)
    request.output_path.write_bytes(final_pdf)
    return request.output_path


def generate_board_book(
    raw_text: str,
    output_path: Path,
    *,
    logo_path: Optional[Path] = None,
    attachments: Optional[Sequence[AttachmentSpec]] = None,
    meeting_date: Optional[date] = None,
    model: Optional[str] = None,
    committee_name: Optional[str] = None,
    style: Optional[TemplateStyle] = None,
    api_key: Optional[str] = None,
) -> Path:
    """One-shot convenience: parse text, then build the board book in a single call."""
    agenda = parse_text_to_agenda(
        raw_text, meeting_date=meeting_date, model=model, committee_name=committee_name, api_key=api_key
    )
    request = BuildRequest(
        agenda=agenda,
        logo_path=logo_path,
        attachments=list(attachments or []),
        output_path=output_path,
        style=style,
    )
    return build_board_book(request)
