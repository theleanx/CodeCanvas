"""
Project Repository: general engagement reference documents (SOW, BPML, PDD,
FDD, Big Rocks, project-specific Skill files, or Other) stored alongside a
project -- a file cabinet, not an input to any generation agent. Distinct
from backend/routes_project_brain.py's document-templates, which store only
extracted text to drive FSD section generation; these store the original
file's bytes unchanged, so whatever was uploaded (a signed SOW PDF, a BPML
export, a roadmap deck) downloads back exactly as uploaded.

Reads (list/download) are open to any logged-in user, same as the rest of
the app. Upload is open to any logged-in user too -- any project member may
need to add a reference document, and nothing here feeds a generation
pipeline the way a document-template upload does. Delete is restricted to
admin/solution_architect or the document's own uploader, the same bar
Project Brain's config writes use for admin/solution_architect, extended to
let someone remove their own mistaken upload without waiting on an admin.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.db import get_db
from backend.api_schemas import ProjectDocumentOut
from backend.models_db import PROJECT_DOCUMENT_CATEGORIES, Project, ProjectDocument, User

router = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])


def _get_project_or_404(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"No project with id {project_id}")
    return project


def _get_document_or_404(db: Session, document_id: str) -> ProjectDocument:
    doc = db.get(ProjectDocument, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"No document with id {document_id}")
    return doc


def _require_delete_permission(user: User, doc: ProjectDocument) -> None:
    if user.role in ("admin", "solution_architect"):
        return
    if doc.uploaded_by and doc.uploaded_by == user.name:
        return
    raise HTTPException(
        status_code=403,
        detail="Only an admin, a solution architect, or the person who uploaded it can delete a repository document.",
    )


@router.get("/projects/{project_id}/documents", response_model=list[ProjectDocumentOut])
def list_project_documents(project_id: str, category: str | None = None, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)
    query = db.query(ProjectDocument).filter(ProjectDocument.project_id == project_id)
    if category:
        query = query.filter(ProjectDocument.category == category)
    rows = query.order_by(ProjectDocument.uploaded_at.desc()).all()
    return rows


@router.post("/projects/{project_id}/documents", response_model=ProjectDocumentOut, status_code=201)
async def upload_project_document(
    project_id: str,
    file: UploadFile,
    category: str,
    notes: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_project_or_404(db, project_id)
    if category not in PROJECT_DOCUMENT_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=f"category must be one of: {', '.join(PROJECT_DOCUMENT_CATEGORIES)} (got {category!r}).",
        )
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail=f'"{file.filename}" is empty.')

    doc = ProjectDocument(
        project_id=project_id,
        category=category,
        filename=file.filename or "unnamed",
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
        content=content,
        notes=notes.strip(),
        uploaded_by=user.name,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@router.get("/project-documents/{document_id}/download")
def download_project_document(document_id: str, db: Session = Depends(get_db)):
    doc = _get_document_or_404(db, document_id)
    return Response(
        content=doc.content,
        media_type=doc.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{doc.filename}"'},
    )


@router.delete("/project-documents/{document_id}", status_code=204)
def delete_project_document(document_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = _get_document_or_404(db, document_id)
    _require_delete_permission(user, doc)
    db.delete(doc)
    db.commit()
