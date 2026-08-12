"""Renders the agenda cover page: Jinja2 (HTML/CSS) -> PDF bytes via headless Chromium.

The template replicates the University of Alberta GFC board-book format
(measured directly from real sample board books):
  - Header: logo centered at the top, "[Committee Name] | [Date]", then
    "[Time Range] | [Location]" - both centered across the full page width.
  - Content: a narrower, left-anchored two-column table - left column is the
    calculated clock time (blank for items with no stated duration), right
    column is the item title, presenters, and action label, with indented
    sub-entries (e.g. individual Consent Agenda motions) nested underneath.
  - Roboto, self-hosted (embedded as base64 @font-face) so rendering doesn't
    depend on whatever fonts happen to be installed on the host machine.
"""

from __future__ import annotations

import base64
import functools
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Optional

import jinja2

from boardbook.models import Agenda, FONT_CHOICES, TemplateStyle, TextStyle

_TEMPLATE_DIR = Path(__file__).parent
_FONTS_DIR = _TEMPLATE_DIR / "fonts"
_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=jinja2.select_autoescape(("html", "j2")),
)

# PDF page geometry - kept in sync with the @page rule in styles.css. Passed
# explicitly to Chromium's print-to-PDF because @page margins are only
# honored when prefer_css_page_size is set, and we want an unambiguous
# contract between the template and the renderer. Measured from real sample
# board books: ~0.46in left/right, ~0.75in top (where the centered logo
# starts), extra bottom margin reserved for the page-number stamp.
_PAGE_FORMAT = "Letter"
_PAGE_MARGIN = {"top": "0.75in", "bottom": "0.9in", "left": "0.46in", "right": "0.46in"}


def _format_date(iso_date: str) -> str:
    """'2026-09-08' -> 'September 08, 2026' (day zero-padded, matching the source format)."""
    try:
        parsed = datetime.strptime(iso_date.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return iso_date
    return f"{parsed.strftime('%B')} {parsed.day:02d}, {parsed.year}"


def _logo_data_uri(logo_path: Optional[Path]) -> Optional[str]:
    if logo_path is None:
        return None
    logo_path = Path(logo_path)
    if not logo_path.exists():
        raise FileNotFoundError(f"Logo file not found: {logo_path}")
    mime, _ = mimetypes.guess_type(logo_path.name)
    mime = mime or "image/png"
    encoded = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


@functools.lru_cache(maxsize=1)
def _font_faces_css() -> str:
    """Self-hosted Roboto as base64 @font-face rules (variable fonts - one file covers all weights)."""
    regular = base64.b64encode((_FONTS_DIR / "Roboto-Variable.ttf").read_bytes()).decode("ascii")
    italic = base64.b64encode((_FONTS_DIR / "Roboto-Italic-Variable.ttf").read_bytes()).decode("ascii")
    return (
        "@font-face {\n"
        "  font-family: 'Roboto';\n"
        f"  src: url(data:font/ttf;base64,{regular}) format('truetype-variations');\n"
        "  font-weight: 100 900;\n"
        "  font-style: normal;\n"
        "}\n"
        "@font-face {\n"
        "  font-family: 'Roboto';\n"
        f"  src: url(data:font/ttf;base64,{italic}) format('truetype-variations');\n"
        "  font-weight: 100 900;\n"
        "  font-style: italic;\n"
        "}"
    )


def _resolve_font_stack(name: str) -> str:
    """A recognized short name (e.g. 'Roboto') -> full CSS font stack. An
    unrecognized value is assumed to already be a valid CSS font-family
    string and is passed through as-is, so power users can supply their own."""
    return FONT_CHOICES.get(name, name)


# (CSS-variable name, TemplateStyle attribute) - drives both the :root block
# below and which selectors in styles.css read var(--font-<key>) etc.
_STYLE_ROLES = (
    ("header1", "header_committee_date"),
    ("header2", "header_time_location"),
    ("title", "item_title"),
    ("presenters", "item_presenters"),
    ("action", "item_action"),
    ("time", "time_column"),
)


def _style_vars_css(style: TemplateStyle) -> str:
    """Render a TemplateStyle into a `:root { --font-title: ...; }` block that
    styles.css's `var(--font-title)` etc. pick up - lets each text role's
    font/size/weight, plus the logo's rendered height, be set from Python
    without touching the stylesheet."""
    lines = [":root {"]
    for css_key, attr_name in _STYLE_ROLES:
        text_style: TextStyle = getattr(style, attr_name)
        lines.append(f"  --font-{css_key}: {_resolve_font_stack(text_style.font_family)};")
        lines.append(f"  --size-{css_key}: {text_style.size_pt}pt;")
        lines.append(f"  --weight-{css_key}: {700 if text_style.bold else 400};")
    lines.append(f"  --logo-height: {style.logo_height_in}in;")
    lines.append("}")
    return "\n".join(lines)


def render_agenda_html(agenda: Agenda, logo_path: Optional[Path] = None, style: Optional[TemplateStyle] = None) -> str:
    """Render the agenda into a standalone HTML document (logo + fonts inlined as data URIs)."""
    template = _env.get_template("agenda.html.j2")
    return template.render(
        agenda=agenda,
        formatted_date=_format_date(agenda.meta.meeting_date),
        logo_data_uri=_logo_data_uri(logo_path),
        font_faces_css=_font_faces_css(),
        style_vars_css=_style_vars_css(style or TemplateStyle()),
    )


def _html_to_pdf(html: str) -> bytes:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError(
            "Playwright is required to render the agenda PDF. Install it with "
            "`pip install playwright` and then run `playwright install chromium` once."
        ) from exc

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - environment guard
            raise RuntimeError(
                "Could not launch headless Chromium. Run `playwright install chromium` "
                "once after installing Python dependencies."
            ) from exc
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            pdf_bytes = page.pdf(
                format=_PAGE_FORMAT,
                print_background=True,
                margin=_PAGE_MARGIN,
            )
        finally:
            browser.close()
    return pdf_bytes


def render_agenda_pdf(agenda: Agenda, logo_path: Optional[Path] = None, style: Optional[TemplateStyle] = None) -> bytes:
    """Render the agenda cover page directly to PDF bytes."""
    html = render_agenda_html(agenda, logo_path, style)
    return _html_to_pdf(html)
