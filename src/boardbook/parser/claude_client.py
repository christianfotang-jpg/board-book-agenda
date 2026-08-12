"""Freeform agenda text -> structured JSON via the Claude Messages API.

Uses `client.messages.parse(..., output_format=ExtractedAgenda)`, which
constrains the response to the given Pydantic schema and returns an already
-validated instance on `response.parsed_output` - no manual JSON parsing or
retry-on-malformed-JSON loop required.
"""

from __future__ import annotations

import anthropic

from boardbook.config import settings
from boardbook.parser.schema import ExtractedAgenda

SYSTEM_PROMPT = """\
You convert freeform, plain-text committee meeting agendas into structured data,
matching the University of Alberta GFC board-book format.

Read the entire input once before extracting anything. Identify the meeting
metadata (committee/body name, date, start time, location) and then each
top-level agenda item in the order it appears.

Rules:
- Preserve the source order of agenda items exactly - do not reorder, group, or merge items.
- Only extract items that are actual agenda business (skip section headers like "CONSENT AGENDA" unless they are themselves a votable item; skip blank filler lines).
- Presenters are the named individuals or roles bringing the item forward (e.g. "J. Smith, Registrar"). Leave the list empty if none are named.
- Preserve action/status labels exactly as written ("For Discussion", "For Decision", "Motion to approve",
  "Item was deferred", "For Discussion (no documents)", etc.) - do not normalize them to a fixed set of
  values, and do not invent one if the source states none.
- Nested sub-entries: some items have indented entries under them with no time of their own - e.g. each
  motion inside a "Consent Agenda", named reference documents under a "Terms of Reference" item, or
  entries listed under an "Information Items" heading. Extract these as that item's sub_items, in order,
  not as separate top-level items.
- Durations and start times are about the SCHEDULE, not about how long the write-up is. Only set
  duration_minutes when the source explicitly gives a duration (e.g. "(10 min)") or an explicit clock
  time/time range for that specific item. Many items genuinely have no stated time (opening remarks
  folded into the item before them, adjournment, informational entries) - leave duration_minutes null for
  those rather than guessing a value or copying a neighboring item's time.
- Never fabricate a committee name, date, or location that is not present or clearly implied in the text.
"""


def parse_agenda_text(raw_text: str, *, model: str | None = None, api_key: str | None = None) -> ExtractedAgenda:
    """Parse freeform agenda text into an ExtractedAgenda via Claude structured outputs.

    `api_key`, when given, is used for this call only - it is never written to
    the environment. This matters on a shared/multi-user deployment: writing a
    user-supplied key to `os.environ` would leak it to every other concurrent
    session on the same server process. Omit it to use the server's own
    ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN (the usual case for a deployed
    instance where the operator holds the credential).

    Raises:
        ValueError: if Claude declines the request or returns no parsed output.
    """
    if not raw_text or not raw_text.strip():
        raise ValueError("Agenda text is empty - nothing to parse.")

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.parse(
        model=model or settings.anthropic_model,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": raw_text}],
        output_format=ExtractedAgenda,
    )

    if response.stop_reason == "refusal":
        raise ValueError("Claude declined to parse this agenda text.")
    if response.parsed_output is None:
        raise ValueError("Claude did not return a structured agenda (empty parsed_output).")

    return response.parsed_output
