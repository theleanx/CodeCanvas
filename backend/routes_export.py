"""
Export an FSD draft as a file, or push it to GitHub / Google Drive.

Downloads need no configuration -- Markdown/Word/PDF are all built locally
from data already in the DB. The two push endpoints are optional
integrations gated by env vars (backend/config.py, backend/push.py) and
return a clear 503 with setup instructions when not configured, rather
than a confusing failure.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.db import get_db
from backend.export import build_docx, build_intake_validation_pdf, build_markdown, build_pdf
from backend.fsd_enhancement_meta import build_document_identification, build_review_signoff, build_validation_table
from backend.models_db import FsdDraft, Project, TrackedObject
from backend.push import PushNotConfigured, push_docx_to_google_drive, push_markdown_to_github

logger = logging.getLogger("codecanvas")

router = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return slug or "untitled"


def _load_context(db: Session, draft_id: str) -> tuple[dict, dict, dict]:
    draft = db.get(FsdDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail=f"No FSD draft with id {draft_id}")
    obj = db.get(TrackedObject, draft.object_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Owning object not found.")
    project = db.get(Project, obj.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Owning project not found.")

    draft_dict = {
        "id": draft.id,
        "version": draft.version,
        "created_at": draft.created_at,
        "request_id": draft.request_id,
        "duration_ms": draft.duration_ms,
        "sources": draft.sources_json,
        "ledger": draft.ledger_json,
        "sections": draft.sections_json,
        "quality_score": draft.quality_score_json,
        "note": draft.note,
        "intake_validation_status": draft.intake_validation_status or "pending",
        "intake_validation": draft.intake_validation_json,
        "approvals": {
            "module_lead_approved": draft.module_lead_approved,
            "module_lead_approved_by": draft.module_lead_approved_by,
            "module_lead_approved_at": draft.module_lead_approved_at,
            "solution_architect_approved": draft.solution_architect_approved,
            "solution_architect_approved_by": draft.solution_architect_approved_by,
            "solution_architect_approved_at": draft.solution_architect_approved_at,
        },
    }
    obj_dict = {"id": obj.id, "name": obj.name, "type": obj.type, "module": obj.module}
    project_dict = {"id": project.id, "name": project.name}

    if obj.type == "Enhancement":
        draft_dict["document_identification"] = build_document_identification(obj_dict, project_dict, draft_dict)
        draft_dict["review_signoff"] = build_review_signoff(draft_dict)
        draft_dict["validation_table"] = build_validation_table(draft.sections_json)

    return draft_dict, obj_dict, project_dict


def _filename(obj: dict, draft: dict, ext: str) -> str:
    return f"{_slugify(obj['name'])}-fsd-v{draft['version']}.{ext}"


# --- downloads ---------------------------------------------------------------

@router.get("/fsd-drafts/{draft_id}/export/markdown")
def export_markdown(draft_id: str, db: Session = Depends(get_db)):
    draft, obj, project = _load_context(db, draft_id)
    content = build_markdown(draft, obj, project)
    filename = _filename(obj, draft, "md")
    return Response(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/fsd-drafts/{draft_id}/export/docx")
def export_docx(draft_id: str, db: Session = Depends(get_db)):
    draft, obj, project = _load_context(db, draft_id)
    content = build_docx(draft, obj, project)
    filename = _filename(obj, draft, "docx")
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/fsd-drafts/{draft_id}/export/pdf")
def export_pdf(draft_id: str, db: Session = Depends(get_db)):
    draft, obj, project = _load_context(db, draft_id)
    content = build_pdf(draft, obj, project)
    filename = _filename(obj, draft, "pdf")
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/fsd-drafts/{draft_id}/export/intake-validation-pdf")
def export_intake_validation_pdf(draft_id: str, db: Session = Depends(get_db)):
    draft, obj, project = _load_context(db, draft_id)
    content = build_intake_validation_pdf(draft, obj, project)
    filename = f"{_slugify(obj['name'])}-intake-validation-v{draft['version']}.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- push ----------------------------------------------------------------

@router.post("/fsd-drafts/{draft_id}/push/github")
def push_github(draft_id: str, db: Session = Depends(get_db)):
    draft, obj, project = _load_context(db, draft_id)
    content = build_markdown(draft, obj, project)
    filename = _filename(obj, draft, "md")
    path_slug = f"{_slugify(project['name'])}/{_slugify(obj['name'])}"
    try:
        result = push_markdown_to_github(
            path_slug,
            filename,
            content,
            commit_message=f"FSD: {obj['name']} v{draft['version']} ({project['name']})",
        )
    except PushNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("github push failed draft_id=%s", draft_id)
        raise HTTPException(status_code=502, detail=f"GitHub push failed: {exc}") from exc
    return {"url": result.url, "detail": result.detail}


@router.post("/fsd-drafts/{draft_id}/push/google-drive")
def push_google_drive(draft_id: str, db: Session = Depends(get_db)):
    draft, obj, project = _load_context(db, draft_id)
    content = build_docx(draft, obj, project)
    filename = _filename(obj, draft, "docx")
    try:
        result = push_docx_to_google_drive(filename, content)
    except PushNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("google drive push failed draft_id=%s", draft_id)
        raise HTTPException(status_code=502, detail=f"Google Drive push failed: {exc}") from exc
    return {"url": result.url, "detail": result.detail}
