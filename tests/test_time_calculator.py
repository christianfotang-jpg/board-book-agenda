from datetime import date

from boardbook.parser.schema import ExtractedAgenda, ExtractedAgendaItem, ExtractedMeetingMeta, ExtractedSubItem
from boardbook.parser.time_calculator import apply_schedule


def _extracted(*, start_time: str = "14:00", items) -> ExtractedAgenda:
    return ExtractedAgenda(
        meta=ExtractedMeetingMeta(
            committee_name="General Faculties Council",
            meeting_date="2026-09-15",
            start_time=start_time,
            location="Council Chambers",
        ),
        items=items,
    )


def test_sequential_times_accumulate_durations():
    extracted = _extracted(
        items=[
            ExtractedAgendaItem(title="Approval of Minutes", action_type="For Approval", duration_minutes=5),
            ExtractedAgendaItem(title="Budget Update", action_type="For Information", duration_minutes=20),
            ExtractedAgendaItem(title="New Program Proposal", action_type="For Approval", duration_minutes=15),
        ]
    )

    agenda = apply_schedule(extracted, meeting_date=date(2026, 9, 15))

    assert [item.calculated_time for item in agenda.items] == ["2:00", "2:05", "2:25"]
    assert agenda.end_time == "2:40"
    assert agenda.time_range == "2:00 - 2:40 PM"
    assert [item.item_number for item in agenda.items] == [1, 2, 3]


def test_start_time_accepts_several_common_formats():
    for start in ("9:05", "09:05", "9:05 AM", "9:05AM"):
        extracted = _extracted(
            start_time=start,
            items=[ExtractedAgendaItem(title="Only item", action_type="For Information", duration_minutes=5)],
        )
        agenda = apply_schedule(extracted, meeting_date=date(2026, 1, 1))
        assert agenda.items[0].calculated_time == "9:05", f"failed for start_time={start!r}"


def test_item_without_duration_gets_no_time_and_consumes_no_schedule():
    """Matches real agendas: 'Opening Remarks' right after 'Approval of the Agenda'
    has no stated duration, shows no time, and doesn't push later items back."""
    extracted = _extracted(
        items=[
            ExtractedAgendaItem(title="Approval of the Agenda", duration_minutes=5),
            ExtractedAgendaItem(title="Opening Remarks"),  # no duration stated
            ExtractedAgendaItem(title="Academic Schedule", duration_minutes=10),
        ]
    )
    agenda = apply_schedule(extracted, meeting_date=date(2026, 1, 1))

    assert agenda.items[0].calculated_time == "2:00"
    assert agenda.items[1].calculated_time == ""  # Opening Remarks: blank, not "2:05"
    assert agenda.items[1].duration_minutes is None
    assert agenda.items[2].calculated_time == "2:05"  # unaffected by the untimed item between them


def test_sub_items_carry_through_with_no_time_of_their_own():
    extracted = _extracted(
        items=[
            ExtractedAgendaItem(
                title="Consent Agenda",
                action_type="For Decision",
                duration_minutes=5,
                sub_items=[
                    ExtractedSubItem(title="Minutes of June 19, 2025", action_type="Motion to approve"),
                    ExtractedSubItem(title="Proposed Non-Credit Certificate", action_type="Motion to approve"),
                ],
            ),
        ]
    )
    agenda = apply_schedule(extracted, meeting_date=date(2026, 1, 1))

    item = agenda.items[0]
    assert item.calculated_time == "2:00"
    assert len(item.sub_items) == 2
    assert item.sub_items[0].title == "Minutes of June 19, 2025"
    assert item.sub_items[0].action_type == "Motion to approve"
    # Sub-items are plain data passthrough - no calculated_time field on them at all.
    assert not hasattr(item.sub_items[0], "calculated_time")


def test_time_range_shows_single_period_suffix_when_start_and_end_match():
    extracted = _extracted(
        start_time="14:00",
        items=[ExtractedAgendaItem(title="Only item", duration_minutes=120)],
    )
    agenda = apply_schedule(extracted, meeting_date=date(2026, 1, 1))
    assert agenda.time_range == "2:00 - 4:00 PM"


def test_time_range_shows_both_period_suffixes_when_they_differ():
    extracted = _extracted(
        start_time="10:00",
        items=[ExtractedAgendaItem(title="Only item", duration_minutes=120)],
    )
    agenda = apply_schedule(extracted, meeting_date=date(2026, 1, 1))
    assert agenda.time_range == "10:00 AM - 12:00 PM"


def test_empty_agenda_has_no_items_and_range_equals_start_time():
    extracted = _extracted(items=[])
    agenda = apply_schedule(extracted, meeting_date=date(2026, 1, 1))
    assert agenda.items == []
    assert agenda.end_time == "2:00"
    assert agenda.time_range == "2:00 - 2:00 PM"
