"""Domain models shared across the parser, template, and compiler stages.

These are the "settled" shapes the rest of the app works with - i.e. after
Claude's raw extraction (see parser/schema.py) has been validated and after
sequential start times have been computed. Keeping them separate from the
extraction schema means the LLM-facing shape can evolve (retries, looser
typing) without rippling through the renderer/compiler.

The item/sub-item split mirrors how these agendas are actually written:
a scheduled item ("Consent Agenda", "For Decision") can carry indented
sub-entries of its own ("Minutes of June 19, 2025", "Motion to approve")
that don't get their own clock time - they're part of the parent's slot.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class MeetingMeta(BaseModel):
    committee_name: str
    meeting_date: str = Field(description="ISO 8601 date, e.g. 2026-09-15")
    start_time: str = Field(description="24-hour HH:MM, e.g. 14:00")
    location: str


class AgendaSubItem(BaseModel):
    """An indented entry nested under a top-level item - no clock time of its own."""

    title: str
    presenters: list[str] = Field(default_factory=list)
    action_type: Optional[str] = None


class AgendaItem(BaseModel):
    item_number: int
    title: str
    presenters: list[str] = Field(default_factory=list)
    action_type: Optional[str] = None
    duration_minutes: Optional[int] = Field(
        default=None, description="Minutes allotted, or None if no duration/time was stated for this item"
    )
    calculated_time: str = Field(
        default="", description="Rendered clock time (e.g. '2:00'), blank if duration_minutes is None"
    )
    sub_items: list[AgendaSubItem] = Field(default_factory=list)


class Agenda(BaseModel):
    meta: MeetingMeta
    items: list[AgendaItem]
    end_time: str = Field(
        default="", description="Bare clock time (e.g. '4:00') the meeting is expected to end"
    )
    time_range: str = Field(
        default="", description="Formatted header range, e.g. '2:00 - 4:00 PM' or '10:00 AM - 12:00 PM'"
    )


class AttachmentSpec(BaseModel):
    """One supporting PDF, ordered under the agenda item (or one of its sub-items) it belongs to."""

    item_number: int
    sub_item_index: Optional[int] = Field(
        default=None,
        description="0-based index into that item's sub_items to attach to a specific sub-entry "
        "(e.g. one Consent Agenda motion) instead of the item itself. None attaches to the item.",
    )
    path: Path
    label: Optional[str] = None


# ---------------------------------------------------------------------------
# Typography settings - lets each text role on the cover page (headings,
# item title, presenters, action label, time column) have its own font,
# size, and weight, instead of everything being hardcoded in styles.css.
# ---------------------------------------------------------------------------

#: Short names offered in the CLI/API/web UI, mapped to a full CSS font stack.
#: "Roboto" is embedded (self-hosted) so it always renders identically; the
#: others rely on fonts commonly available on the host/renderer machine, with
#: a generic fallback if not. A raw CSS font-family string also works as-is
#: (looked up here first, passed through unchanged if not a recognized key).
FONT_CHOICES: dict[str, str] = {
    "Roboto": "'Roboto', Arial, sans-serif",
    "Arial": "Arial, Helvetica, sans-serif",
    "Georgia": "Georgia, 'Times New Roman', serif",
    "Times New Roman": "'Times New Roman', Times, serif",
}


class TextStyle(BaseModel):
    font_family: str = "Roboto"
    size_pt: float = Field(gt=0)
    bold: bool = False


class TemplateStyle(BaseModel):
    """Per-role typography for the agenda cover page. Unset roles use the
    GFC-format defaults measured from real board books."""

    header_committee_date: TextStyle = Field(default_factory=lambda: TextStyle(size_pt=13, bold=False))
    header_time_location: TextStyle = Field(default_factory=lambda: TextStyle(size_pt=13, bold=True))
    item_title: TextStyle = Field(default_factory=lambda: TextStyle(size_pt=11, bold=True))
    item_presenters: TextStyle = Field(default_factory=lambda: TextStyle(size_pt=11, bold=False))
    item_action: TextStyle = Field(default_factory=lambda: TextStyle(size_pt=10, bold=False))
    time_column: TextStyle = Field(default_factory=lambda: TextStyle(size_pt=10.5, bold=False))
    logo_height_in: float = Field(
        default=0.65,
        gt=0,
        description="Rendered logo height in inches (width scales to match, preserving aspect ratio). "
        "0.65in matches the University of Alberta's own board book letterhead. Unlike CSS max-height, "
        "this is a fixed height - it scales a small source image UP to this size, not just down.",
    )


class BuildRequest(BaseModel):
    """Everything the pipeline needs to produce a final board book PDF."""

    agenda: Agenda
    logo_path: Optional[Path] = None
    attachments: list[AttachmentSpec] = Field(default_factory=list)
    output_path: Path
    style: Optional[TemplateStyle] = None
