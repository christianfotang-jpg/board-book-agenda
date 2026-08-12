"""Sequential start-time computation.

Given a meeting start time and each item's duration, compute the clock time
each item begins - purely deterministic, no LLM involvement. Real GFC
agendas don't give every line its own time: items with no stated duration
(opening remarks folded into the item before them, adjournment, nested
sub-entries) simply show no time and consume zero minutes of the schedule.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, time as dt_time

from boardbook.models import Agenda, AgendaItem, AgendaSubItem, MeetingMeta
from boardbook.parser.schema import ExtractedAgenda

_TIME_FORMATS = ("%H:%M", "%I:%M %p", "%I:%M%p", "%H:%M:%S")


def _parse_start_time(value: str) -> dt_time:
    candidate = value.strip()
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(candidate, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Could not parse meeting start time: {value!r}")


def _bare_clock(moment: datetime) -> str:
    """'2:00' - no AM/PM, matching how times are shown next to each item."""
    hour12 = moment.hour % 12 or 12
    return f"{hour12}:{moment.minute:02d}"


def _period(moment: datetime) -> str:
    return "AM" if moment.hour < 12 else "PM"


def _format_time_range(start: datetime, end: datetime) -> str:
    """'2:00 - 4:00 PM' if both periods match, else '10:00 AM - 12:00 PM'."""
    end_period = _period(end)
    if _period(start) != end_period:
        return f"{_bare_clock(start)} {_period(start)} - {_bare_clock(end)} {end_period}"
    return f"{_bare_clock(start)} - {_bare_clock(end)} {end_period}"


def apply_schedule(extracted: ExtractedAgenda, meeting_date: date | None = None) -> Agenda:
    """Assign item_number and calculated_time to each top-level item, sequentially.

    Only items with an explicit `duration_minutes` advance the clock and get a
    rendered `calculated_time`; everything else (and all sub_items) gets a
    blank time, matching the source format. `Agenda.time_range` is the
    meeting's full start-end range for the header, independent of whether any
    individual item happens to carry a time.
    """
    start = _parse_start_time(extracted.meta.start_time)
    anchor_date = meeting_date or date.today()
    start_dt = datetime.combine(anchor_date, start)
    cursor = start_dt

    items: list[AgendaItem] = []
    for index, raw_item in enumerate(extracted.items, start=1):
        calculated_time = ""
        if raw_item.duration_minutes is not None:
            duration = max(raw_item.duration_minutes, 0)
            calculated_time = _bare_clock(cursor)
            cursor += timedelta(minutes=duration)

        sub_items = [
            AgendaSubItem(title=s.title, presenters=s.presenters, action_type=s.action_type)
            for s in raw_item.sub_items
        ]

        items.append(
            AgendaItem(
                item_number=index,
                title=raw_item.title,
                presenters=raw_item.presenters,
                action_type=raw_item.action_type,
                duration_minutes=raw_item.duration_minutes,
                calculated_time=calculated_time,
                sub_items=sub_items,
            )
        )

    return Agenda(
        meta=MeetingMeta(
            committee_name=extracted.meta.committee_name,
            meeting_date=extracted.meta.meeting_date,
            start_time=extracted.meta.start_time,
            location=extracted.meta.location,
        ),
        items=items,
        end_time=_bare_clock(cursor),
        time_range=_format_time_range(start_dt, cursor),
    )
