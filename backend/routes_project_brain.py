"""
Project Brain: per-project terminology (object types/modules/complexity)
and document templates (in-built vs. client-specific, per document type x
object-type category).

Reads are open to any logged-in user, same as the rest of the app; writes
are restricted to admin/solution_architect, the same two senior roles
project-delete already uses -- this is project-wide configuration that
changes what every contributor sees in dropdowns and what every future FSD
drafts against, not a personal setting.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.db import get_db
from backend.documents import UnsupportedDocumentType
from backend.models_db import (
    DOCUMENT_TYPES,
    OBJECT_TYPE_INTERNAL_KEYS,
    Project,
    ProjectComplexityConfig,
    ProjectDocumentTemplate,
    ProjectModuleConfig,
    ProjectObjectTypeConfig,
    TrackedObject,
    User,
)
from backend.project_brain import _sanitize_id_code, ensure_default_configs
from backend.schemas import get_template_sections
from backend.template_parsing import extract_template_sections
from backend.api_schemas import (
    ComplexityConfigCreate,
    ComplexityConfigOut,
    ComplexityConfigPatch,
    DocumentTemplateOut,
    DocumentTemplateSave,
    DocumentTemplateSection,
    DocumentTemplateUploadResponse,
    ModuleConfigCreate,
    ModuleConfigOut,
    ModuleConfigPatch,
    ObjectTypeConfigOut,
    ObjectTypeConfigPatch,
)

router = APIRouter(prefix="/api/projects/{project_id}/brain", dependencies=[Depends(get_current_user)])


def _require_editor(user: User) -> None:
    if user.role not in ("admin", "solution_architect"):
        raise HTTPException(status_code=403, detail="Only an admin or solution architect can edit Project Brain configuration.")


def _get_project_or_404(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"No project with id {project_id}")
    return project


# --- object types (rename-only -- see models_db.OBJECT_TYPE_INTERNAL_KEYS) -

@router.get("/object-types", response_model=list[ObjectTypeConfigOut])
def list_object_types(project_id: str, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)
    ensure_default_configs(db, project_id)
    rows = (
        db.query(ProjectObjectTypeConfig)
        .filter(ProjectObjectTypeConfig.project_id == project_id)
        .order_by(ProjectObjectTypeConfig.sort_order)
        .all()
    )
    return rows


@router.patch("/object-types/{internal_key}", response_model=ObjectTypeConfigOut)
def update_object_type(
    project_id: str,
    internal_key: str,
    payload: ObjectTypeConfigPatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_editor(user)
    _get_project_or_404(db, project_id)
    if internal_key not in OBJECT_TYPE_INTERNAL_KEYS:
        raise HTTPException(status_code=404, detail=f"Unknown object type category {internal_key!r}.")
    ensure_default_configs(db, project_id)
    row = (
        db.query(ProjectObjectTypeConfig)
        .filter(ProjectObjectTypeConfig.project_id == project_id, ProjectObjectTypeConfig.internal_key == internal_key)
        .first()
    )
    if payload.display_label is not None:
        row.display_label = payload.display_label.strip() or internal_key
    if payload.id_prefix is not None:
        row.id_prefix = payload.id_prefix.strip().upper() or internal_key[0].upper()
    if payload.enabled is not None:
        row.enabled = payload.enabled
    db.commit()
    db.refresh(row)
    return row


# --- modules -----------------------------------------------------------------

@router.get("/modules", response_model=list[ModuleConfigOut])
def list_modules(project_id: str, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)
    ensure_default_configs(db, project_id)
    return (
        db.query(ProjectModuleConfig)
        .filter(ProjectModuleConfig.project_id == project_id)
        .order_by(ProjectModuleConfig.sort_order)
        .all()
    )


def _check_module_id_code_unique(db: Session, project_id: str, id_code: str, exclude_id: str | None = None) -> None:
    q = db.query(ProjectModuleConfig).filter(
        ProjectModuleConfig.project_id == project_id, ProjectModuleConfig.id_code == id_code
    )
    if exclude_id:
        q = q.filter(ProjectModuleConfig.id != exclude_id)
    if q.first() is not None:
        raise HTTPException(
            status_code=409,
            detail=f'Another module already uses the id-code "{id_code}" in this project -- Object IDs need a unique code per module.',
        )


@router.post("/modules", response_model=ModuleConfigOut, status_code=201)
def create_module(
    project_id: str, payload: ModuleConfigCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    _require_editor(user)
    _get_project_or_404(db, project_id)
    ensure_default_configs(db, project_id)
    id_code = (payload.id_code or _sanitize_id_code(payload.name)).upper()
    _check_module_id_code_unique(db, project_id, id_code)
    max_order = db.query(ProjectModuleConfig).filter(ProjectModuleConfig.project_id == project_id).count()
    row = ProjectModuleConfig(project_id=project_id, name=payload.name.strip(), id_code=id_code, enabled=True, sort_order=max_order)
    db.add(row)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=f'A module named "{payload.name}" already exists in this project.') from exc
    db.refresh(row)
    return row


@router.patch("/modules/{module_id}", response_model=ModuleConfigOut)
def update_module(
    project_id: str,
    module_id: str,
    payload: ModuleConfigPatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_editor(user)
    _get_project_or_404(db, project_id)
    row = db.query(ProjectModuleConfig).filter(ProjectModuleConfig.id == module_id, ProjectModuleConfig.project_id == project_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="No module with that id in this project.")
    if payload.id_code is not None:
        new_code = payload.id_code.strip().upper()
        _check_module_id_code_unique(db, project_id, new_code, exclude_id=module_id)
        row.id_code = new_code
    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.enabled is not None:
        row.enabled = payload.enabled
    db.commit()
    db.refresh(row)
    return row


@router.delete("/modules/{module_id}", status_code=204)
def delete_module(project_id: str, module_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_editor(user)
    _get_project_or_404(db, project_id)
    row = db.query(ProjectModuleConfig).filter(ProjectModuleConfig.id == module_id, ProjectModuleConfig.project_id == project_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="No module with that id in this project.")
    in_use = db.query(TrackedObject).filter(TrackedObject.project_id == project_id, TrackedObject.module == row.name).count()
    if in_use:
        raise HTTPException(
            status_code=409,
            detail=f'"{row.name}" is used by {in_use} object(s) in this project -- disable it instead of deleting, so those objects keep a valid module.',
        )
    db.delete(row)
    db.commit()


# --- complexity levels ---------------------------------------------------

@router.get("/complexities", response_model=list[ComplexityConfigOut])
def list_complexities(project_id: str, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)
    ensure_default_configs(db, project_id)
    return (
        db.query(ProjectComplexityConfig)
        .filter(ProjectComplexityConfig.project_id == project_id)
        .order_by(ProjectComplexityConfig.sort_order)
        .all()
    )


@router.post("/complexities", response_model=ComplexityConfigOut, status_code=201)
def create_complexity(
    project_id: str, payload: ComplexityConfigCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    _require_editor(user)
    _get_project_or_404(db, project_id)
    ensure_default_configs(db, project_id)
    max_order = db.query(ProjectComplexityConfig).filter(ProjectComplexityConfig.project_id == project_id).count()
    row = ProjectComplexityConfig(project_id=project_id, name=payload.name.strip(), enabled=True, sort_order=max_order)
    db.add(row)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=f'A complexity level named "{payload.name}" already exists in this project.') from exc
    db.refresh(row)
    return row


@router.patch("/complexities/{complexity_id}", response_model=ComplexityConfigOut)
def update_complexity(
    project_id: str,
    complexity_id: str,
    payload: ComplexityConfigPatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_editor(user)
    _get_project_or_404(db, project_id)
    row = (
        db.query(ProjectComplexityConfig)
        .filter(ProjectComplexityConfig.id == complexity_id, ProjectComplexityConfig.project_id == project_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="No complexity level with that id in this project.")
    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.enabled is not None:
        row.enabled = payload.enabled
    db.commit()
    db.refresh(row)
    return row


@router.delete("/complexities/{complexity_id}", status_code=204)
def delete_complexity(project_id: str, complexity_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_editor(user)
    _get_project_or_404(db, project_id)
    row = (
        db.query(ProjectComplexityConfig)
        .filter(ProjectComplexityConfig.id == complexity_id, ProjectComplexityConfig.project_id == project_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="No complexity level with that id in this project.")
    in_use = db.query(TrackedObject).filter(TrackedObject.project_id == project_id, TrackedObject.complexity == row.name).count()
    if in_use:
        raise HTTPException(
            status_code=409,
            detail=f'"{row.name}" is used by {in_use} object(s) in this project -- disable it instead of deleting.',
        )
    db.delete(row)
    db.commit()


# --- document templates ---------------------------------------------------
# Only FSD actually has a generation agent today -- see DocumentTemplateOut.
# generation_available in api_schemas.py.
_GENERATION_AVAILABLE_DOC_TYPES = {"FSD"}


@router.get("/document-templates", response_model=list[DocumentTemplateOut])
def list_document_templates(project_id: str, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)
    rows = {
        (r.document_type, r.object_type_key): r
        for r in db.query(ProjectDocumentTemplate).filter(ProjectDocumentTemplate.project_id == project_id).all()
    }
    out: list[DocumentTemplateOut] = []
    for document_type in DOCUMENT_TYPES:
        for object_type_key in OBJECT_TYPE_INTERNAL_KEYS:
            row = rows.get((document_type, object_type_key))
            in_built_sections = (
                [DocumentTemplateSection(**s) for s in get_template_sections(object_type_key)]
                if document_type == "FSD"
                else None
            )
            if row:
                out.append(
                    DocumentTemplateOut(
                        document_type=document_type,
                        object_type_key=object_type_key,
                        source=row.source,
                        uploaded_filename=row.uploaded_filename,
                        sections=[DocumentTemplateSection(**s) for s in row.sections_json] if row.sections_json else None,
                        diagram_section_key=row.diagram_section_key,
                        allow_ai_inferred=row.allow_ai_inferred,
                        updated_at=row.updated_at,
                        updated_by=row.updated_by,
                        in_built_sections=in_built_sections,
                        generation_available=document_type in _GENERATION_AVAILABLE_DOC_TYPES,
                    )
                )
            else:
                out.append(
                    DocumentTemplateOut(
                        document_type=document_type,
                        object_type_key=object_type_key,
                        source="in_built",
                        in_built_sections=in_built_sections,
                        generation_available=document_type in _GENERATION_AVAILABLE_DOC_TYPES,
                    )
                )
    return out


@router.post("/document-templates/upload", response_model=DocumentTemplateUploadResponse)
async def upload_document_template(
    project_id: str, file: UploadFile, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """Extracts a preview the admin reviews/edits before saving -- this
    endpoint never writes to the database. Saving happens via PUT
    /document-templates/{document_type}/{object_type_key} once the admin
    confirms the section list."""
    _require_editor(user)
    _get_project_or_404(db, project_id)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail=f'"{file.filename}" is empty.')
    try:
        sections, raw_text = extract_template_sections(file.filename or "unnamed", content)
    except UnsupportedDocumentType as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DocumentTemplateUploadResponse(
        filename=file.filename or "unnamed",
        sections=[DocumentTemplateSection(**s) for s in sections],
        raw_text=raw_text,
        char_count=len(raw_text),
    )


@router.put("/document-templates/{document_type}/{object_type_key}", response_model=DocumentTemplateOut)
def save_document_template(
    project_id: str,
    document_type: str,
    object_type_key: str,
    payload: DocumentTemplateSave,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_editor(user)
    _get_project_or_404(db, project_id)
    if document_type not in DOCUMENT_TYPES:
        raise HTTPException(status_code=404, detail=f"Unknown document type {document_type!r}.")
    if object_type_key not in OBJECT_TYPE_INTERNAL_KEYS:
        raise HTTPException(status_code=404, detail=f"Unknown object type category {object_type_key!r}.")

    if payload.source == "client_specific":
        if not payload.sections or len(payload.sections) == 0:
            raise HTTPException(status_code=422, detail="A client-specific template needs at least one section.")
        keys = [s.key for s in payload.sections]
        if len(keys) != len(set(keys)):
            raise HTTPException(status_code=422, detail="Section keys must be unique within a template.")
        if payload.diagram_section_key and payload.diagram_section_key not in keys:
            raise HTTPException(status_code=422, detail="diagram_section_key must match one of the section keys.")

    row = (
        db.query(ProjectDocumentTemplate)
        .filter(
            ProjectDocumentTemplate.project_id == project_id,
            ProjectDocumentTemplate.document_type == document_type,
            ProjectDocumentTemplate.object_type_key == object_type_key,
        )
        .first()
    )
    if row is None:
        row = ProjectDocumentTemplate(project_id=project_id, document_type=document_type, object_type_key=object_type_key)
        db.add(row)

    row.source = payload.source
    if payload.source == "in_built":
        row.uploaded_filename = None
        row.sections_json = None
        row.diagram_section_key = None
        row.allow_ai_inferred = False
        row.raw_text = None
    else:
        row.uploaded_filename = payload.uploaded_filename
        row.sections_json = [s.model_dump() for s in payload.sections]
        row.diagram_section_key = payload.diagram_section_key
        row.allow_ai_inferred = payload.allow_ai_inferred
        row.raw_text = payload.raw_text
    row.updated_at = datetime.now(timezone.utc)
    row.updated_by = user.name

    db.commit()
    db.refresh(row)

    in_built_sections = (
        [DocumentTemplateSection(**s) for s in get_template_sections(object_type_key)] if document_type == "FSD" else None
    )
    return DocumentTemplateOut(
        document_type=row.document_type,
        object_type_key=row.object_type_key,
        source=row.source,
        uploaded_filename=row.uploaded_filename,
        sections=[DocumentTemplateSection(**s) for s in row.sections_json] if row.sections_json else None,
        diagram_section_key=row.diagram_section_key,
        allow_ai_inferred=row.allow_ai_inferred,
        updated_at=row.updated_at,
        updated_by=row.updated_by,
        in_built_sections=in_built_sections,
        generation_available=document_type in _GENERATION_AVAILABLE_DOC_TYPES,
    )
