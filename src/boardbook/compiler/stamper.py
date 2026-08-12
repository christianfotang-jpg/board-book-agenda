"""Final pass over the fully-merged PDF: stamps "Page X of Y" at the bottom
right of every page, regardless of which stage (cover vs. attachment) that
page came from.
"""

from __future__ import annotations

import io

from pypdf import PageObject, PdfReader, PdfWriter
from reportlab.pdfgen import canvas

# Matches the monospace "Page X of Y" stamp measured on real sample board
# books - Courier is one of the 14 standard PDF fonts, so no embedding is
# needed for it to render identically everywhere.
_MARGIN_PT = 14.0  # ~0.2in from the page edge
_FONT_NAME = "Courier"
_FONT_SIZE = 10


def stamp_page_numbers(pdf_bytes: bytes) -> bytes:
    """Return a new PDF with "Page X of Y" stamped on every page's footer.

    Each page keeps its own media box size (attachments may differ from the
    Letter-size cover page), so the stamp overlay is generated per-page
    rather than reused.
    """
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    total_pages = len(reader.pages)

    for index, page in enumerate(reader.pages, start=1):
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        overlay = _stamp_overlay(width, height, f"Page {index} of {total_pages}")
        # Attach the page to the writer before merging the overlay onto it -
        # merging onto an unattached page is deprecated in recent pypdf.
        attached_page = writer.add_page(page)
        attached_page.merge_page(overlay)

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _stamp_overlay(width: float, height: float, label: str) -> PageObject:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    c.setFont(_FONT_NAME, _FONT_SIZE)
    text_width = c.stringWidth(label, _FONT_NAME, _FONT_SIZE)
    x = max(width - _MARGIN_PT - text_width, 0.0)
    y = _MARGIN_PT * 0.55
    c.drawString(x, y, label)
    c.showPage()
    c.save()
    buf.seek(0)
    return PdfReader(buf).pages[0]
