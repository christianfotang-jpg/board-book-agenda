"""Merges the rendered agenda cover page with supporting-document attachments,
placing each item's attachments sequentially, in agenda item order - and
within an item, its own attachments first, then each sub-item's attachments
in the sub-item's source order (see AttachmentSpec.sub_item_index).
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Optional, Sequence

from pypdf import PdfReader, PdfWriter

from boardbook.models import Agenda, AttachmentSpec

_Key = tuple  # (item_number: int, sub_item_index: Optional[int])


def merge_board_book(cover_pdf_bytes: bytes, agenda: Agenda, attachments: Sequence[AttachmentSpec]) -> bytes:
    """Concatenate [cover pages] + [item 1's own + sub-item attachments] + [item 2's ...] + ...

    Attachments are grouped by `(item_number, sub_item_index)` and appended
    in agenda order - not by whatever order the caller happened to list them
    in - so the final document always reflects the agenda's own sequencing.
    Within one item: its own attachments (sub_item_index=None) first, then
    each sub-item's attachments in that sub-item's source order. Within one
    item or sub-item, attachments keep the order they were supplied in.
    """
    items_by_number = {item.item_number: item for item in agenda.items}
    _validate_references(items_by_number, attachments)

    by_key: dict[_Key, list[AttachmentSpec]] = {}
    for spec in attachments:
        by_key.setdefault((spec.item_number, spec.sub_item_index), []).append(spec)

    writer = PdfWriter()
    _append_bytes(writer, cover_pdf_bytes, source="rendered agenda cover page")

    for item in agenda.items:
        for spec in by_key.get((item.item_number, None), []):
            _append_file(writer, spec.path)
        for sub_index in range(len(item.sub_items)):
            for spec in by_key.get((item.item_number, sub_index), []):
                _append_file(writer, spec.path)

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _validate_references(items_by_number: dict, attachments: Sequence[AttachmentSpec]) -> None:
    unknown_items = sorted({spec.item_number for spec in attachments} - set(items_by_number))
    if unknown_items:
        raise ValueError(
            f"Attachment(s) reference agenda item number(s) not present in the agenda: {unknown_items}"
        )

    bad_refs = []
    for spec in attachments:
        if spec.sub_item_index is None:
            continue
        sub_count = len(items_by_number[spec.item_number].sub_items)
        if not (0 <= spec.sub_item_index < sub_count):
            bad_refs.append((spec.item_number, spec.sub_item_index, sub_count))
    if bad_refs:
        details = ", ".join(
            f"item {item_number} sub-item index {sub_index} (item has {count} sub-item(s))"
            for item_number, sub_index, count in bad_refs
        )
        raise ValueError(f"Attachment(s) reference sub-items that don't exist: {details}")


def _append_bytes(writer: PdfWriter, data: bytes, *, source: str) -> None:
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError(f"Could not read PDF produced by {source}") from exc
    for page in reader.pages:
        writer.add_page(page)


def _append_file(writer: PdfWriter, path: Path) -> None:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Attachment PDF not found: {path}")
    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise ValueError(f"Could not read attachment as a PDF: {path}") from exc
    for page in reader.pages:
        writer.add_page(page)
