"""
CRUD + FSD-generation routes, scoped to projects and objects.

This is the real persistence layer the frontend now talks to instead of
its old lib/mockData.ts. The actual agent logic (ledger -> draft -> score)
is untouched -- it still lives in backend/agents/pipeline.py. What's new
here is wrapping that call so each run is saved as an immutable, versioned
FsdDraft row tied to a TrackedObject, with real approval state.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.agents.pipeline import run_fsd_creation
from backend.api_schemas import (
    ApprovalPatch,
    FsdDraftOut,
    FsdDraftSummary,
    FsdGenerateRequest,
    ObjectCreate,
    ObjectOut,
    ObjectStatusPatch,
    ProjectCreate,
    ProjectOut,
    ApprovalState,
)
from backend.auth import get_current_user
from backend.db import get_db
from backend.fsd_enhancement_meta import build_document_identification, build_review_signoff, build_validation_table
from backend.models_db import FsdDraft, Project, TrackedObject, User

logger = logging.getLogger("codecanvas")

# Every route in this router requires a logged-in user. Role-specific
# restrictions (e.g. only a Solution Architect can approve as one) are
# layered on top of individual routes below via require_role(...).
router = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])


# --- helpers -----------------------------------------------------------------

def _project_out(db: Session, project: Project) -> ProjectOut:
    count = db.query(func.count(TrackedObject.id)).filter(TrackedObject.project_id == project.id).scalar() or 0
    return ProjectOut(
        id=project.id,
        name=project.name,
        kind=project.kind,
        system_description=project.system_description,
        industry=project.industry,
        geography=project.geography,
        object_count=count,
        updated_at=project.updated_at,
    )


def _object_out(db: Session, obj: TrackedObject) -> ObjectOut:
    latest_version = (
        db.query(func.max(FsdDraft.version)).filter(FsdDraft.object_id == obj.id).scalar()
    )
    return ObjectOut(
        id=obj.id,
        project_id=obj.project_id,
        name=obj.name,
        type=obj.type,
        module=obj.module,
        complexity=obj.complexity,
        fsd_status=obj.fsd_status,
        feasibility_status=obj.feasibility_status,
        tsd_status=obj.tsd_status,
        code_review_status=obj.code_review_status,
        unit_test_status=obj.unit_test_status,
        code_status=obj.code_status,
        latest_fsd_version=latest_version,
    )


def _draft_out(db: Session, draft: FsdDraft) -> FsdDraftOut:
    out = FsdDraftOut(
        id=draft.id,
        object_id=draft.object_id,
        version=draft.version,
        created_at=draft.created_at,
        request_id=draft.request_id,
        duration_ms=draft.duration_ms,
        sources=draft.sources_json,
        ledger=draft.ledger_json,
        sections=draft.sections_json,
        quality_score=draft.quality_score_json,
        note=draft.note,
        approvals=ApprovalState(
            module_lead_approved=draft.module_lead_approved,
            module_lead_approved_by=draft.module_lead_approved_by,
            module_lead_approved_at=draft.module_lead_approved_at,
            solution_architect_approved=draft.solution_architect_approved,
            solution_architect_approved_by=draft.solution_architect_approved_by,
            solution_architect_approved_at=draft.solution_architect_approved_at,
        ),
    )

    # Document Identification / Review & Sign-off / the Validation table are
    # only part of the Enhancement template -- computed here (not drafted by
    # the model) from data that already exists, so they're always accurate.
    obj = db.get(TrackedObject, draft.object_id)
    if obj and obj.type == "Enhancement":
        project = db.get(Project, obj.project_id)
        draft_dict = out.model_dump()
        out.document_identification = build_document_identification(
            {"id": obj.id, "name": obj.name, "type": obj.type, "module": obj.module},
            {"name": project.name if project else "—"},
            draft_dict,
        )
        out.review_signoff = build_review_signoff(draft_dict)
        out.validation_table = build_validation_table(draft.sections_json)

    return out


def _get_project_or_404(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"No project with id {project_id}")
    return project


def _get_object_or_404(db: Session, object_id: str) -> TrackedObject:
    obj = db.get(TrackedObject, object_id)
    if not obj:
        raise HTTPException(status_code=404, detail=f"No object with id {object_id}")
    return obj


def _get_draft_or_404(db: Session, draft_id: str) -> FsdDraft:
    draft = db.get(FsdDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail=f"No FSD draft with id {draft_id}")
    return draft


# --- projects ------------------------------------------------------------

@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).order_by(Project.updated_at.desc()).all()
    return [_project_out(db, p) for p in projects]


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(**payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return _project_out(db, project)


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = _get_project_or_404(db, project_id)
    return _project_out(db, project)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Destructive and irreversible (cascades to every object and FSD draft
    # in it), so restricted to the two senior roles -- a module_lead or
    # contributor can't take this action, but a solution_architect (the
    # role driving this app day to day) isn't locked out of a feature they
    # explicitly asked for just because they aren't also seeded as admin.
    if user.role not in ("admin", "solution_architect"):
        raise HTTPException(status_code=403, detail="Only an admin or solution architect can delete a project.")
    project = _get_project_or_404(db, project_id)
    db.delete(project)
    db.commit()


@router.get("/projects/{project_id}/objects", response_model=list[ObjectOut])
def list_objects(project_id: str, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)
    objs = (
        db.query(TrackedObject)
        .filter(TrackedObject.project_id == project_id)
        .order_by(TrackedObject.created_at)
        .all()
    )
    return [_object_out(db, o) for o in objs]


@router.post("/projects/{project_id}/objects", response_model=ObjectOut, status_code=201)
def create_object(project_id: str, payload: ObjectCreate, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)
    obj = TrackedObject(project_id=project_id, **payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return _object_out(db, obj)


# --- objects ---------------------------------------------------------------

@router.get("/objects/{object_id}", response_model=ObjectOut)
def get_object(object_id: str, db: Session = Depends(get_db)):
    obj = _get_object_or_404(db, object_id)
    return _object_out(db, obj)


# Maps the API's stage name to the actual column on TrackedObject.
_STAGE_COLUMN = {
    "fsd": "fsd_status",
    "feasibility": "feasibility_status",
    "tsd": "tsd_status",
    "code_review": "code_review_status",
    "unit_test": "unit_test_status",
    "code": "code_status",
}


@router.patch("/objects/{object_id}/status", response_model=ObjectOut)
def set_object_stage_status(object_id: str, payload: ObjectStatusPatch, db: Session = Depends(get_db)):
    obj = _get_object_or_404(db, object_id)
    # A manual override (e.g. putting FSD On Hold) is a deliberate choice,
    # so it sticks -- the automatic status moves elsewhere in this file
    # (on generate, on approval) only happen as a side effect of someone
    # actually doing something on that stage, not of this endpoint.
    setattr(obj, _STAGE_COLUMN[payload.stage], payload.status)
    db.commit()
    db.refresh(obj)
    return _object_out(db, obj)


# --- FSD drafts --------------------------------------------------------------

@router.get("/objects/{object_id}/fsd-drafts", response_model=list[FsdDraftSummary])
def list_fsd_drafts(object_id: str, db: Session = Depends(get_db)):
    _get_object_or_404(db, object_id)
    drafts = (
        db.query(FsdDraft).filter(FsdDraft.object_id == object_id).order_by(FsdDraft.version.desc()).all()
    )
    return [
        FsdDraftSummary(
            id=d.id,
            version=d.version,
            created_at=d.created_at,
            request_id=d.request_id,
            duration_ms=d.duration_ms,
            overall_pct=d.quality_score_json.get("overall_pct", 0),
            tier=d.quality_score_json.get("tier", "not_advisable"),
            note=d.note,
        )
        for d in drafts
    ]


@router.get("/objects/{object_id}/fsd-drafts/latest", response_model=FsdDraftOut)
def get_latest_fsd_draft(object_id: str, db: Session = Depends(get_db)):
    _get_object_or_404(db, object_id)
    draft = (
        db.query(FsdDraft).filter(FsdDraft.object_id == object_id).order_by(FsdDraft.version.desc()).first()
    )
    if not draft:
        raise HTTPException(status_code=404, detail="No FSD draft has been generated for this object yet.")
    return _draft_out(db, draft)


@router.get("/fsd-drafts/{draft_id}", response_model=FsdDraftOut)
def get_fsd_draft(draft_id: str, db: Session = Depends(get_db)):
    return _draft_out(db, _get_draft_or_404(db, draft_id))


@router.post("/objects/{object_id}/fsd-drafts", response_model=FsdDraftOut, status_code=201)
def generate_fsd_draft(object_id: str, payload: FsdGenerateRequest, db: Session = Depends(get_db)):
    obj = _get_object_or_404(db, object_id)

    next_version = (db.query(func.max(FsdDraft.version)).filter(FsdDraft.object_id == object_id).scalar() or 0) + 1

    request_id = str(uuid.uuid4())
    logger.info("fsd_generate start request_id=%s object_id=%s version=%s", request_id, object_id, next_version)
    started = time.monotonic()
    try:
        agent_draft = run_fsd_creation(payload.sources, obj.type)
    except Exception as exc:
        logger.exception("fsd_generate failed request_id=%s", request_id)
        raise HTTPException(status_code=502, detail=f"Agent pipeline failed: {exc}") from exc
    duration_ms = int((time.monotonic() - started) * 1000)

    draft = FsdDraft(
        object_id=object_id,
        version=next_version,
        sources_json=[s.model_dump() for s in payload.sources],
        ledger_json=[e.model_dump() for e in agent_draft.ledger],
        sections_json=[s.model_dump() for s in agent_draft.sections],
        quality_score_json=agent_draft.quality_score.model_dump(),
        request_id=request_id,
        duration_ms=duration_ms,
        note=payload.note or (f"Generated from {len(payload.sources)} source(s)" if next_version == 1 else "Regenerated"),
    )
    db.add(draft)

    # A freshly generated draft is, by definition, not yet approved -- move
    # the object's FSD pipeline stage to In Progress unless it's already
    # further along than that shouldn't be possible, but don't regress a
    # Blocked/On Hold object's status just because someone generated a draft.
    if obj.fsd_status in ("Not Started", "Complete"):
        obj.fsd_status = "In Progress"

    try:
        db.commit()
    except IntegrityError as exc:
        # Two concurrent requests both computed the same next_version. One
        # wins; the other gets a clean, explicit error instead of a silent
        # duplicate "version 1" (the uniqueness constraint on
        # (object_id, version) is what actually catches this).
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Another FSD generation for this object just completed -- refresh and try again.",
        ) from exc
    db.refresh(draft)
    logger.info("fsd_generate done request_id=%s duration_ms=%s version=%s", request_id, duration_ms, next_version)
    return _draft_out(db, draft)


@router.patch("/fsd-drafts/{draft_id}/approval", response_model=FsdDraftOut)
def set_approval(
    draft_id: str,
    payload: ApprovalPatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    draft = _get_draft_or_404(db, draft_id)

    # Only a user whose own role matches the approval role being set can
    # approve (or withdraw) it -- an admin can act as either, as the
    # operator override. This is what actually ties "who approved this" to
    # a real identity instead of the two hardcoded names the UI used to show.
    if user.role != "admin" and user.role != payload.role:
        raise HTTPException(
            status_code=403,
            detail=f"Only a {payload.role.replace('_', ' ')} (or admin) can set this approval -- you are {user.role.replace('_', ' ')}.",
        )

    now = datetime.now(timezone.utc) if payload.approved else None
    approver = user.name if payload.approved else None

    if payload.role == "module_lead":
        draft.module_lead_approved = payload.approved
        draft.module_lead_approved_by = approver
        draft.module_lead_approved_at = now
    else:
        draft.solution_architect_approved = payload.approved
        draft.solution_architect_approved_by = approver
        draft.solution_architect_approved_at = now

    requires_dual = draft.quality_score_json.get("requires_dual_approval", True)
    fully_approved = (
        draft.module_lead_approved and draft.solution_architect_approved
        if requires_dual
        else (draft.module_lead_approved or draft.solution_architect_approved)
    )

    obj = _get_object_or_404(db, draft.object_id)
    # Only this draft's own object, and only when this IS the latest version,
    # should approval state move the pipeline status. A full approval is a
    # real, meaningful event (the stage is genuinely done), so it always
    # wins. Withdrawing an approval without fully approving, though, follows
    # the same rule as generating a new draft: don't regress a manually set
    # Blocked/On Hold just because of this one action.
    latest_version = db.query(func.max(FsdDraft.version)).filter(FsdDraft.object_id == obj.id).scalar()
    if draft.version == latest_version:
        if fully_approved:
            obj.fsd_status = "Complete"
        elif obj.fsd_status in ("Not Started", "Complete"):
            obj.fsd_status = "In Progress"

    db.commit()
    db.refresh(draft)
    return _draft_out(db, draft)
