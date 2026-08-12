import io

from pypdf import PdfReader
from reportlab.pdfgen import canvas

from boardbook.compiler.stamper import stamp_page_numbers


def _make_pdf_bytes(num_pages: int) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))
    for i in range(num_pages):
        c.drawString(72, 700, f"content {i + 1}")
        c.showPage()
    c.save()
    return buf.getvalue()


def test_stamp_adds_page_x_of_y_to_every_page():
    original = _make_pdf_bytes(3)

    stamped = stamp_page_numbers(original)

    reader = PdfReader(io.BytesIO(stamped))
    assert len(reader.pages) == 3
    texts = [page.extract_text() for page in reader.pages]
    assert "Page 1 of 3" in texts[0]
    assert "Page 2 of 3" in texts[1]
    assert "Page 3 of 3" in texts[2]
    # Original content survives the overlay merge.
    assert "content 1" in texts[0]
    assert "content 3" in texts[2]


def test_stamp_preserves_each_pages_own_size():
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))
    c.drawString(72, 700, "letter page")
    c.showPage()
    c.setPageSize((1000, 1200))
    c.drawString(72, 1100, "oversized page")
    c.showPage()
    c.save()

    stamped = stamp_page_numbers(buf.getvalue())

    reader = PdfReader(io.BytesIO(stamped))
    assert float(reader.pages[0].mediabox.width) == 612
    assert float(reader.pages[0].mediabox.height) == 792
    assert float(reader.pages[1].mediabox.width) == 1000
    assert float(reader.pages[1].mediabox.height) == 1200


def test_stamp_on_single_page_document():
    stamped = stamp_page_numbers(_make_pdf_bytes(1))
    reader = PdfReader(io.BytesIO(stamped))
    assert "Page 1 of 1" in reader.pages[0].extract_text()
