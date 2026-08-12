"""Streamlit web interface for the Board Book Generator.

Wraps the same three pipeline stages the CLI and API use - parse text,
render + merge + stamp - behind a form-driven UI:

    1. Pick the committee, paste freeform agenda text, pick a meeting date,
       click Parse Agenda.
    2. Review the structured items (including nested sub-entries, e.g. each
       Consent Agenda motion); drag & drop PDF attachments onto the exact
       item or sub-item they belong to. Optionally adjust fonts/sizes.
    3. Click "Generate & Download Board Book PDF" to render, merge, and
       stamp the final document - previewed and downloadable in-browser.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Streamlit Community Cloud only ever runs `pip install -r requirements.txt`
# - it never runs `pip install -e .`. Locally, that editable install is what
# puts the local `boardbook` package (src-layout: it lives under src/, not
# the repo root - see pyproject.toml's `[tool.setuptools.packages.find]
# where = ["src"]`) on the import path. Without it, `import boardbook` fails
# with ModuleNotFoundError on a fresh Streamlit Cloud container. Add src/ to
# sys.path explicitly, before importing anything from boardbook, so both
# environments resolve the same package.
_SRC_DIR = Path(__file__).resolve().parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import base64
import os
import shutil
import subprocess
import tempfile
from datetime import date
from typing import Optional

import anthropic
import streamlit as st

from boardbook.committees import GFC_COMMITTEES
from boardbook.models import Agenda, AttachmentSpec, BuildRequest, FONT_CHOICES, TemplateStyle, TextStyle
from boardbook.pipeline import build_board_book, parse_text_to_agenda

st.set_page_config(page_title="Board Book Generator", page_icon="📋", layout="wide")


@st.cache_resource(show_spinner="Setting up the PDF renderer (first run only, ~30s)...")
def _ensure_chromium_installed() -> None:
    """Hosted platforms like Streamlit Community Cloud only run `pip install
    -r requirements.txt` - they never run `playwright install chromium`, so
    the browser binary has to be fetched on first use here instead. Local
    setups already do this via setup.sh/`boardbook doctor`, so this is a fast
    no-op there. `st.cache_resource` makes it a true one-time cost per
    running container (not per user session) - unlike a user-entered API
    key, this touches no per-user state, so caching it process-wide is safe.
    """
    subprocess.run(["playwright", "install", "chromium"], check=True)


_ensure_chromium_installed()

_SELECT_COMMITTEE_PLACEHOLDER = "— Select committee —"
_OTHER_COMMITTEE = "Other (type below)"
_COMMITTEE_OPTIONS = [_SELECT_COMMITTEE_PLACEHOLDER, *GFC_COMMITTEES, _OTHER_COMMITTEE]
_FONT_OPTIONS = list(FONT_CHOICES.keys())

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

st.session_state.setdefault("agenda", None)
st.session_state.setdefault("parse_error", None)
st.session_state.setdefault("pdf_bytes", None)
st.session_state.setdefault("pdf_filename", None)
st.session_state.setdefault("build_error", None)


def _reset_all() -> None:
    st.session_state.agenda = None
    st.session_state.parse_error = None
    st.session_state.pdf_bytes = None
    st.session_state.pdf_filename = None
    st.session_state.build_error = None


def _build_pdf_bytes(
    agenda: Agenda,
    logo_file,
    output_filename: str,
    style: Optional[TemplateStyle],
) -> bytes:
    """Materialize uploaded files to a temp dir, run the build pipeline, return the PDF bytes.

    The pipeline works with filesystem paths (so it can shell out to a real PDF
    merge/stamp pass), while Streamlit hands us in-memory UploadedFile objects -
    this bridges the two, and cleans the temp dir up before returning.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="boardbook_"))
    try:
        logo_path: Optional[Path] = None
        if logo_file is not None:
            logo_path = tmp_dir / logo_file.name
            logo_path.write_bytes(logo_file.getvalue())

        attachments: list[AttachmentSpec] = []
        for item in agenda.items:
            uploaded_files = st.session_state.get(f"attachments_item_{item.item_number}") or []
            for uploaded in uploaded_files:
                dest = tmp_dir / f"item{item.item_number}_{uploaded.name}"
                dest.write_bytes(uploaded.getvalue())
                attachments.append(AttachmentSpec(item_number=item.item_number, path=dest))

            for sub_index, _sub in enumerate(item.sub_items, start=1):
                sub_uploaded_files = st.session_state.get(f"attachments_item_{item.item_number}_sub_{sub_index}") or []
                for uploaded in sub_uploaded_files:
                    dest = tmp_dir / f"item{item.item_number}_sub{sub_index}_{uploaded.name}"
                    dest.write_bytes(uploaded.getvalue())
                    attachments.append(
                        AttachmentSpec(item_number=item.item_number, sub_item_index=sub_index - 1, path=dest)
                    )

        if not output_filename.lower().endswith(".pdf"):
            output_filename = f"{output_filename}.pdf"
        output_path = tmp_dir / output_filename

        request = BuildRequest(
            agenda=agenda, logo_path=logo_path, attachments=attachments, output_path=output_path, style=style
        )
        build_board_book(request)
        return output_path.read_bytes()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _style_row(role_key: str, label: str, default: TextStyle) -> TextStyle:
    """One row of the style-settings grid: font family / size / bold for one text role."""
    cols = st.columns([2, 2, 1, 1])
    cols[0].markdown(label)
    family = cols[1].selectbox(
        "Font",
        _FONT_OPTIONS,
        index=_FONT_OPTIONS.index(default.font_family),
        key=f"style_{role_key}_font",
        label_visibility="collapsed",
    )
    size = cols[2].number_input(
        "Size (pt)",
        min_value=6.0,
        max_value=36.0,
        value=default.size_pt,
        step=0.5,
        key=f"style_{role_key}_size",
        label_visibility="collapsed",
    )
    bold = cols[3].checkbox("Bold", value=default.bold, key=f"style_{role_key}_bold")
    return TextStyle(font_family=family, size_pt=size, bold=bold)


# ---------------------------------------------------------------------------
# Sidebar - credentials, logo, reset
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Settings")

    has_server_credentials = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    session_api_key: Optional[str] = None
    if has_server_credentials:
        st.success("Anthropic API key detected.")
    else:
        # Passed straight to the Claude call for this run only (see
        # pipeline.parse_text_to_agenda) - never written to os.environ, which
        # is shared by every concurrent user on a multi-user deployment.
        entered_key = st.text_input(
            "Anthropic API key",
            type="password",
            help="Used for this session only, never stored. Set ANTHROPIC_API_KEY on the server "
            "instead if you'd rather your users not need their own key.",
        )
        if entered_key:
            session_api_key = entered_key
            st.success("API key set for this session.")
        else:
            st.warning("Needed before you can parse an agenda.")

    st.divider()
    st.subheader("Institution logo (optional)")
    logo_file = st.file_uploader(
        "Shown centered at the top of the agenda header",
        type=["png", "jpg", "jpeg", "svg"],
        key="logo_uploader",
    )
    logo_height_in = st.number_input(
        "Logo height (inches)",
        min_value=0.2,
        max_value=2.0,
        value=0.65,
        step=0.05,
        key="logo_height_in",
        help="0.65in matches the University of Alberta's own board book letterhead. The logo is "
        "scaled to this height regardless of the uploaded image's resolution, width auto-scales "
        "to preserve its aspect ratio.",
    )

    st.divider()
    if st.button("Start over", use_container_width=True):
        _reset_all()
        st.rerun()

# ---------------------------------------------------------------------------
# 1. Committee + agenda text + meeting date + parse
# ---------------------------------------------------------------------------

st.title("📋 Board Book Generator")
st.caption(
    "Pick the committee, paste a freeform meeting agenda, parse it into structured items, attach "
    "supporting PDFs per item, then generate the finished board book."
)

with st.expander("How this works", expanded=False):
    st.markdown(
        "1. **Parse** - Claude reads your plain-text agenda and extracts each item's title, "
        "presenters, and action type (plus any nested sub-entries, like individual Consent Agenda "
        "motions); item start times are then computed sequentially from the meeting date/start "
        "time and each item's duration.\n"
        "2. **Attach** - upload the supporting PDF(s) for any item or sub-item that has one.\n"
        "3. **Generate** - the GFC-style cover page is rendered, your attachments are merged "
        "in after it (in agenda order), and every page is stamped with a page number footer."
    )

st.subheader("1. Committee & agenda text")

committee_choice = st.selectbox("Committee", _COMMITTEE_OPTIONS, key="committee_choice")
committee_name_override: Optional[str] = None
if committee_choice == _OTHER_COMMITTEE:
    committee_name_override = st.text_input("Custom committee name", key="committee_custom_name").strip() or None
elif committee_choice != _SELECT_COMMITTEE_PLACEHOLDER:
    committee_name_override = committee_choice

col_text, col_controls = st.columns([3, 1])

with col_text:
    raw_text = st.text_area(
        "Paste the raw meeting agenda text",
        height=320,
        key="raw_text",
        placeholder="General Faculties Council\nRegular Meeting\n\nDate: September 15, 2026\n"
        "Time: 2:00 p.m.\nLocation: Council Chambers, University Hall\n\n"
        "1. Approval of the Agenda\n   For Approval\n   (2 min)\n\n...",
    )

with col_controls:
    meeting_date: date = st.date_input("Meeting date", value=date.today(), key="meeting_date")
    parse_clicked = st.button("Parse Agenda", type="primary", use_container_width=True)
    st.caption("Item start times are computed sequentially from this date's start time and each item's duration.")

if parse_clicked:
    if not raw_text.strip():
        st.warning("Paste some agenda text first.")
    elif not (session_api_key or has_server_credentials):
        st.warning("Add your Anthropic API key in the sidebar first.")
    else:
        with st.spinner("Asking Claude to parse the agenda..."):
            try:
                agenda = parse_text_to_agenda(
                    raw_text,
                    meeting_date=meeting_date,
                    committee_name=committee_name_override,
                    api_key=session_api_key,
                )
            except anthropic.AuthenticationError:
                st.session_state.agenda = None
                st.session_state.parse_error = "Invalid Anthropic API key. Check the key in the sidebar."
            except anthropic.APIConnectionError as exc:
                st.session_state.agenda = None
                st.session_state.parse_error = f"Could not reach the Anthropic API: {exc}"
            except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
                st.session_state.agenda = None
                st.session_state.parse_error = str(exc)
            else:
                st.session_state.agenda = agenda
                st.session_state.parse_error = None
                st.session_state.pdf_bytes = None  # a re-parse invalidates any previously built PDF
                st.session_state.pdf_filename = None

if st.session_state.parse_error:
    st.error(f"Could not parse the agenda: {st.session_state.parse_error}")

# ---------------------------------------------------------------------------
# 2 & 3. Review items, attach PDFs, adjust style, generate
# ---------------------------------------------------------------------------

agenda: Optional[Agenda] = st.session_state.agenda

if agenda is None:
    st.info("Paste agenda text above and click **Parse Agenda** to get started.")
else:
    st.success(f"Parsed {len(agenda.items)} agenda item(s).")
    st.subheader("2. Review items & attach supporting documents")
    st.caption(
        f"**{agenda.meta.committee_name}** · {agenda.meta.meeting_date} · "
        f"{agenda.time_range} · {agenda.meta.location}"
    )

    for item in agenda.items:
        with st.container(border=True):
            item_col, upload_col = st.columns([2, 1])
            with item_col:
                st.markdown(f"**{item.item_number}. {item.title}**")
                if item.presenters:
                    st.caption(", ".join(item.presenters))
                detail_bits = [b for b in (item.calculated_time, item.action_type) if b]
                if item.duration_minutes is not None:
                    detail_bits.append(f"{item.duration_minutes} min")
                if detail_bits:
                    st.caption(" · ".join(detail_bits))
            with upload_col:
                st.file_uploader(
                    f"Attachments for item {item.item_number}",
                    type=["pdf"],
                    accept_multiple_files=True,
                    key=f"attachments_item_{item.item_number}",
                    label_visibility="collapsed",
                )

            for sub_index, sub in enumerate(item.sub_items, start=1):
                sub_col, sub_upload_col = st.columns([2, 1])
                with sub_col:
                    sub_bits = ", ".join(sub.presenters) if sub.presenters else None
                    sub_label = f"↳ {sub.title}"
                    if sub_bits:
                        sub_label += f" — {sub_bits}"
                    if sub.action_type:
                        sub_label += f" ({sub.action_type})"
                    st.caption(sub_label)
                with sub_upload_col:
                    st.file_uploader(
                        f"Attachments for item {item.item_number}, sub-item {sub_index}",
                        type=["pdf"],
                        accept_multiple_files=True,
                        key=f"attachments_item_{item.item_number}_sub_{sub_index}",
                        label_visibility="collapsed",
                    )

    with st.expander("Style settings (fonts & sizes)", expanded=False):
        st.caption("Adjust typography for each part of the cover page. Leave as-is for the standard GFC look.")
        header_cols = st.columns([2, 2, 1, 1])
        header_cols[0].caption("**Role**")
        header_cols[1].caption("**Font**")
        header_cols[2].caption("**Size (pt)**")
        header_cols[3].caption("**Bold**")

        _defaults = TemplateStyle()
        style = TemplateStyle(
            header_committee_date=_style_row("header1", "Committee \\| Date", _defaults.header_committee_date),
            header_time_location=_style_row("header2", "Time \\| Location", _defaults.header_time_location),
            item_title=_style_row("title", "Item title", _defaults.item_title),
            item_presenters=_style_row("presenters", "Presenters", _defaults.item_presenters),
            item_action=_style_row("action", "Action label", _defaults.item_action),
            time_column=_style_row("time", "Time column", _defaults.time_column),
            logo_height_in=logo_height_in,  # set in the sidebar, next to the logo uploader
        )

    st.subheader("3. Generate")
    default_filename = f"boardbook_{agenda.meta.meeting_date or meeting_date.isoformat()}.pdf"
    output_filename = st.text_input("Output filename", value=default_filename)
    generate_clicked = st.button("Generate & Download Board Book PDF", type="primary")

    if generate_clicked:
        with st.spinner("Rendering the agenda, merging attachments, and stamping page numbers..."):
            try:
                pdf_bytes = _build_pdf_bytes(agenda, logo_file, output_filename, style)
            except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
                st.session_state.build_error = str(exc)
                st.session_state.pdf_bytes = None
            else:
                st.session_state.build_error = None
                st.session_state.pdf_bytes = pdf_bytes
                st.session_state.pdf_filename = output_filename if output_filename.lower().endswith(".pdf") else f"{output_filename}.pdf"

    if st.session_state.build_error:
        st.error(f"Could not generate the board book: {st.session_state.build_error}")

    if st.session_state.pdf_bytes:
        st.success("Board book generated.")
        st.download_button(
            "⬇️ Download Board Book PDF",
            data=st.session_state.pdf_bytes,
            file_name=st.session_state.pdf_filename,
            mime="application/pdf",
        )
        st.subheader("Preview")
        _b64 = base64.b64encode(st.session_state.pdf_bytes).decode("ascii")
        st.markdown(
            f'<iframe src="data:application/pdf;base64,{_b64}" width="100%" height="900" '
            'style="border: 1px solid #ddd; border-radius: 4px;"></iframe>',
            unsafe_allow_html=True,
        )
