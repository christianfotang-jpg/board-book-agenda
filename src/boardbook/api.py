"""FastAPI service.

    POST /parse        freeform agenda text -> structured agenda JSON
    POST /attachments   upload a supporting PDF, get back a file_id
    POST /logo           upload an institution logo image, get back a file_id
    POST /build          structured agenda + file_ids -> final board book PDF

Run with: uvicorn boardbook.api:app --reload
"""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from boardbook import __version__
from boardbook.config import settings
from boardbook.models import Agenda, AttachmentSpec, BuildRequest, TemplateStyle
from boardbook.pipeline import build_board_book, parse_text_to_agenda

UPLOAD_DIR = Path(settings.upload_dir)
OUTPUT_DIR = Path(settings.output_dir)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Board Book Generator API",
    version=__version__,
    description="Parses freeform agenda text, renders a GFC-style cover page, and compiles the final board book PDF.",
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ParseRequest(BaseModel):
    text: str = Field(..., description="Freeform, plain-text meeting agenda.")
    meeting_date: Optional[date] = Field(None, description="Anchor date used to compute item clock times. Defaults to today.")
    model: Optional[str] = Field(None, description="Override the Claude model used for extraction.")
    committee_name: Optional[str] = Field(
        None, description="Committee name to use instead of whatever Claude extracts from the text."
    )


class ParseResponse(BaseModel):
    agenda: Agenda


class UploadResponse(BaseModel):
    file_id: str
    filename: str


class BuildAttachmentRef(BaseModel):
    item_number: int
    file_id: str
    sub_item_index: Optional[int] = Field(
        None,
        description="0-based index into that item's sub_items to attach to a specific sub-entry "
        "(e.g. one Consent Agenda motion) instead of the item itself.",
    )


class BuildRequestBody(BaseModel):
    agenda: Agenda
    logo_file_id: Optional[str] = None
    attachments: list[BuildAttachmentRef] = Field(default_factory=list)
    output_filename: Optional[str] = None
    style: Optional[TemplateStyle] = Field(
        None, description="Per-role font/size/weight overrides for the cover page. Omit for GFC-format defaults."
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _save_upload(file: UploadFile) -> UploadResponse:
    file_id = f"{uuid.uuid4().hex}{Path(file.filename or '').suffix}"
    dest = UPLOAD_DIR / file_id
    dest.write_bytes(await file.read())
    return UploadResponse(file_id=file_id, filename=file.filename or file_id)


def _resolve_upload(file_id: str) -> Path:
    """Resolve a previously-uploaded file's id back to a path, refusing anything
    that would escape UPLOAD_DIR (path traversal via a crafted file_id)."""
    base = UPLOAD_DIR.resolve()
    candidate = (base / file_id).resolve()
    if not candidate.is_relative_to(base):
        raise HTTPException(status_code=400, detail="Invalid file_id")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail=f"Uploaded file not found: {file_id}")
    return candidate


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.post("/parse", response_model=ParseResponse)
def parse_endpoint(body: ParseRequest) -> ParseResponse:
    """Stage 1 - INPUT PARSER."""
    try:
        agenda = parse_text_to_agenda(
            body.text, meeting_date=body.meeting_date, model=body.model, committee_name=body.committee_name
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ParseResponse(agenda=agenda)


@app.post("/attachments", response_model=UploadResponse)
async def upload_attachment(file: UploadFile = File(...)) -> UploadResponse:
    """Upload one supporting PDF. Reference the returned file_id from /build."""
    return await _save_upload(file)


@app.post("/logo", response_model=UploadResponse)
async def upload_logo(file: UploadFile = File(...)) -> UploadResponse:
    """Upload an institution logo image. Reference the returned file_id from /build."""
    return await _save_upload(file)


@app.post("/build")
def build_endpoint(body: BuildRequestBody) -> FileResponse:
    """Stages 2 & 3 - AGENDA TEMPLATE + PDF COMPILER & STAMPER. Returns the finished PDF."""
    logo_path = _resolve_upload(body.logo_file_id) if body.logo_file_id else None
    attachments = [
        AttachmentSpec(item_number=ref.item_number, sub_item_index=ref.sub_item_index, path=_resolve_upload(ref.file_id))
        for ref in body.attachments
    ]

    filename = body.output_filename or f"boardbook_{uuid.uuid4().hex[:8]}.pdf"
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"
    output_path = OUTPUT_DIR / filename

    request = BuildRequest(
        agenda=body.agenda,
        logo_path=logo_path,
        attachments=attachments,
        output_path=output_path,
        style=body.style,
    )
    try:
        build_board_book(request)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return FileResponse(output_path, media_type="application/pdf", filename=filename)
