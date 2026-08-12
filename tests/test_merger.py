import io
from pathlib import Path

import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from boardbook.compiler.merger import merge_board_book
from boardbook.models import Agenda, AgendaItem, AgendaSubItem, AttachmentSpec, MeetingMeta


def _make_pdf_bytes(num_pages: int = 1, label: str = "page") -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))
    for i in range(num_pages):
        c.drawString(72, 700, f"{label} {i + 1}")
        c.showPage()
    c.save()
    return buf.getvalue()


def _agenda_with_items(n: int, sub_items: "list[AgendaSubItem] | None" = None) -> Agenda:
    items = [
        AgendaItem(
            item_number=i,
            title=f"Item {i}",
            presenters=[],
            action_type="For Information",
            duration_minutes=10,
            calculated_time="2:00 p.m.",
            sub_items=sub_items if (i == n and sub_items) else [],
        )
        for i in range(1, n + 1)
    ]
    return Agenda(
        meta=MeetingMeta(committee_name="Test Committee", meeting_date="2026-01-01", start_time="14:00", location="Room 1"),
        items=items,
        end_time="2:30 p.m.",
    )


def test_merge_places_attachments_in_agenda_item_order_not_input_order(tmp_path: Path):
    cover = _make_pdf_bytes(num_pages=1, label="cover")

    item2_doc = tmp_path / "item2_doc.pdf"
    item2_doc.write_bytes(_make_pdf_bytes(num_pages=1, label="item2-doc"))
    item1_doc = tmp_path / "item1_doc.pdf"
    item1_doc.write_bytes(_make_pdf_bytes(num_pages=2, label="item1-doc"))

    agenda = _agenda_with_items(2)
    # Deliberately supplied out of agenda order - item 2's attachment first.
    attachments = [
        AttachmentSpec(item_number=2, path=item2_doc),
        AttachmentSpec(item_number=1, path=item1_doc),
    ]

    merged = merge_board_book(cover, agenda, attachments)

    reader = PdfReader(io.BytesIO(merged))
    assert len(reader.pages) == 1 + 2 + 1  # cover + item1's 2 pages + item2's 1 page
    texts = [page.extract_text() for page in reader.pages]
    assert "cover 1" in texts[0]
    assert "item1-doc 1" in texts[1]
    assert "item1-doc 2" in texts[2]
    assert "item2-doc 1" in texts[3]


def test_merge_with_no_attachments_returns_cover_only():
    cover = _make_pdf_bytes(num_pages=2, label="cover")
    agenda = _agenda_with_items(1)

    merged = merge_board_book(cover, agenda, [])

    reader = PdfReader(io.BytesIO(merged))
    assert len(reader.pages) == 2


def test_merge_rejects_attachment_for_unknown_item_number(tmp_path: Path):
    cover = _make_pdf_bytes()
    stray = tmp_path / "stray.pdf"
    stray.write_bytes(_make_pdf_bytes())
    agenda = _agenda_with_items(1)

    with pytest.raises(ValueError, match="not present in the agenda"):
        merge_board_book(cover, agenda, [AttachmentSpec(item_number=99, path=stray)])


def test_merge_raises_for_missing_attachment_file(tmp_path: Path):
    cover = _make_pdf_bytes()
    agenda = _agenda_with_items(1)
    missing = tmp_path / "does_not_exist.pdf"

    with pytest.raises(FileNotFoundError):
        merge_board_book(cover, agenda, [AttachmentSpec(item_number=1, path=missing)])


def test_merge_orders_item_level_before_sub_item_attachments_in_sub_item_order(tmp_path: Path):
    cover = _make_pdf_bytes(label="cover")

    item_level_doc = tmp_path / "item_level.pdf"
    item_level_doc.write_bytes(_make_pdf_bytes(label="item-level"))
    sub1_doc = tmp_path / "sub1.pdf"
    sub1_doc.write_bytes(_make_pdf_bytes(label="sub1"))
    sub2_doc = tmp_path / "sub2.pdf"
    sub2_doc.write_bytes(_make_pdf_bytes(label="sub2"))

    agenda = _agenda_with_items(
        1,
        sub_items=[
            AgendaSubItem(title="Minutes of June 9, 2026", action_type="Motion to approve"),
            AgendaSubItem(title="Proposed Graduate Certificate", action_type="Motion to approve"),
        ],
    )

    # Supplied deliberately out of order: sub-item 2's doc, then sub-item 1's, then the item's own.
    attachments = [
        AttachmentSpec(item_number=1, sub_item_index=1, path=sub2_doc),
        AttachmentSpec(item_number=1, sub_item_index=0, path=sub1_doc),
        AttachmentSpec(item_number=1, path=item_level_doc),
    ]

    merged = merge_board_book(cover, agenda, attachments)

    reader = PdfReader(io.BytesIO(merged))
    texts = [page.extract_text() for page in reader.pages]
    assert len(texts) == 4
    assert "cover 1" in texts[0]
    assert "item-level 1" in texts[1]  # item's own attachment comes before any sub-item's
    assert "sub1 1" in texts[2]  # sub-item 0 (first sub-item) before sub-item 1
    assert "sub2 1" in texts[3]


def test_merge_rejects_out_of_range_sub_item_index(tmp_path: Path):
    cover = _make_pdf_bytes()
    doc = tmp_path / "doc.pdf"
    doc.write_bytes(_make_pdf_bytes())
    agenda = _agenda_with_items(1, sub_items=[AgendaSubItem(title="Only sub-item")])

    with pytest.raises(ValueError, match="sub-items that don't exist"):
        merge_board_book(cover, agenda, [AttachmentSpec(item_number=1, sub_item_index=5, path=doc)])
