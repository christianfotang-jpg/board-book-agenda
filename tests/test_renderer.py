"""Renderer tests that don't need a browser - render_agenda_html() (Jinja2 only)
and the CSS-variable generation are pure string operations; only
render_agenda_pdf()/_html_to_pdf() need Playwright, which is covered by the
CLI/app smoke tests instead.
"""

from boardbook.models import Agenda, AgendaItem, MeetingMeta, TemplateStyle, TextStyle
from boardbook.template.renderer import _style_vars_css
from boardbook.template.renderer import render_agenda_html


def _minimal_agenda() -> Agenda:
    return Agenda(
        meta=MeetingMeta(committee_name="Test Committee", meeting_date="2026-01-01", start_time="14:00", location="Room 1"),
        items=[
            AgendaItem(
                item_number=1,
                title="Approval of the Agenda",
                action_type="For Approval",
                duration_minutes=5,
                calculated_time="2:00",
            )
        ],
        end_time="2:05",
        time_range="2:00 - 2:05 PM",
    )


def test_template_style_logo_height_defaults_to_ualberta_measurement():
    # Measured directly from a real University of Alberta board book PDF.
    assert TemplateStyle().logo_height_in == 0.65


def test_style_vars_css_includes_logo_height():
    css = _style_vars_css(TemplateStyle())
    assert "--logo-height: 0.65in;" in css


def test_style_vars_css_reflects_custom_logo_height():
    css = _style_vars_css(TemplateStyle(logo_height_in=1.2))
    assert "--logo-height: 1.2in;" in css


def test_render_agenda_html_embeds_style_vars_and_logo_height():
    html = render_agenda_html(_minimal_agenda(), style=TemplateStyle(logo_height_in=0.9))
    assert "--logo-height: 0.9in;" in html
    assert "Test Committee" in html
