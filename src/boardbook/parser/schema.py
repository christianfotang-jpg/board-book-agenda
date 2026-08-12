"""Pydantic shape Claude is asked to fill in via structured outputs.

This is deliberately narrower than boardbook.models.Agenda: it only covers
what an LLM should be inferring from freeform text (titles, presenters,
action labels, durations, nested sub-entries, meeting metadata). Sequencing
fields - item_number and calculated_time - are derived deterministically
afterwards by time_calculator.apply_schedule, never by the model.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ExtractedSubItem(BaseModel):
    title: str = Field(
        description="Title of an entry indented under a parent agenda item - e.g. one motion within a "
        "Consent Agenda, a named reference document, or one entry under an 'Information Items' heading."
    )
    presenters: list[str] = Field(
        default_factory=list,
        description="Names and/or roles of the people presenting this sub-entry, if any are named.",
    )
    action_type: Optional[str] = Field(
        default=None,
        description="The action/status label exactly as written (e.g. 'Motion to approve'), or omit/null "
        "if the source text states none for this sub-entry.",
    )


class ExtractedAgendaItem(BaseModel):
    title: str = Field(description="The agenda item's title or subject line, verbatim or lightly cleaned up.")
    presenters: list[str] = Field(
        default_factory=list,
        description="Names and/or roles of the people presenting or bringing forward this item. Empty list if none are named.",
    )
    action_type: Optional[str] = Field(
        default=None,
        description=(
            "The action or status label exactly as written in the source text - e.g. 'For Discussion', "
            "'For Decision', 'For Information', 'Motion to approve', 'Motion to Recommend', 'Item was "
            "deferred', 'For Discussion (no documents)'. Preserve the source's exact wording and "
            "capitalization. Omit/null if the source states no action label for this item."
        ),
    )
    duration_minutes: Optional[int] = Field(
        default=None,
        description=(
            "Minutes allotted to this item, ONLY if the source text explicitly states a duration (e.g. "
            "'(10 min)') or an explicit clock time/time range for this specific item. Do NOT guess or "
            "estimate a duration when none is given - omit/null instead. Many real agenda items "
            "(introductory remarks, adjournment, informational entries) intentionally have no stated "
            "time and must be left null rather than assigned a made-up value."
        ),
    )
    sub_items: list[ExtractedSubItem] = Field(
        default_factory=list,
        description=(
            "Entries that appear indented underneath this item in the source text, with no independent "
            "time of their own - e.g. each motion inside a 'Consent Agenda' item, named reference "
            "documents under a 'Terms of Reference' item, or entries under an 'Information Items' item. "
            "Leave empty if the item has no nested entries."
        ),
    )


class ExtractedMeetingMeta(BaseModel):
    committee_name: str = Field(description="The full committee or meeting body name, e.g. 'General Faculties Council'.")
    meeting_date: str = Field(
        description="The meeting date normalized to ISO 8601 (YYYY-MM-DD). Resolve partial/relative dates using any year or context given in the text."
    )
    start_time: str = Field(description="The meeting's start time normalized to 24-hour HH:MM, e.g. '14:00'.")
    location: str = Field(description="Room, building, and/or virtual meeting link/platform as given in the text.")


class ExtractedAgenda(BaseModel):
    meta: ExtractedMeetingMeta
    items: list[ExtractedAgendaItem] = Field(
        description="Top-level agenda items in the exact order they appear in the source text."
    )
