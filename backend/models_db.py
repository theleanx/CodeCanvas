"""
SQLAlchemy ORM models for real persistence: Project -> TrackedObject -> FsdDraft.

These are deliberately separate from backend/schemas.py (the agent's own
Pydantic shapes). schemas.py describes what the FSD Creation agent produces
in memory; these describe what gets stored and how it relates to a project
and an object. FsdDraft stores the agent's ledger/sections/quality_score as
JSON blobs rather than normalizing them into their own tables -- each draft
is an immutable snapshot (a "version"), so there's nothing to update inside
one after it's created, which is exactly the case JSON columns are for.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


ROLES = ("admin", "module_lead", "solution_architect", "contributor")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), default="contributor")  # see ROLES above
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20), default="Greenfield")  # Greenfield | Brownfield
    system_description: Mapped[str] = mapped_column(String(300), default="")
    industry: Mapped[str] = mapped_column(String(100), default="")
    geography: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    objects: Mapped[list["TrackedObject"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="TrackedObject.created_at"
    )


PIPELINE_STAGES = ("Not Started", "In Progress", "Blocked", "On Hold", "Complete")

# The six object-type categories are fixed in code -- they're what actually
# select an FSD template and an Intake Validation checklist (see
# backend/intake_checklist.py and backend/agents/pipeline.py). A project can
# relabel them for its own client (ProjectObjectTypeConfig.display_label)
# but never introduce a genuinely new behavioral category -- see the
# "Rename only" decision recorded in the Project Brain commit.
OBJECT_TYPE_INTERNAL_KEYS = ("Report", "Interface", "Conversion", "Enhancement", "Form", "Workflow")
DOCUMENT_TYPES = ("FSD", "TSD", "Code Review", "Test Script")

# Project Repository categories (backend/routes_project_documents.py) -- the
# fixed set of project-level reference documents a team keeps alongside the
# object pipeline: engagement-level artifacts (SOW, BPML, PDD, FDD, Big
# Rocks), project-specific Skill files (consulting playbooks/know-how for
# this engagement, distinct from the app's own built-in skills), and an
# Other bucket for anything that doesn't fit those. Order here is display
# order in the UI's category filter/grouping.
PROJECT_DOCUMENT_CATEGORIES = ("SOW", "BPML", "PDD", "FDD", "Big Rocks", "Skills", "Other")


class TrackedObject(Base):
    __tablename__ = "tracked_objects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    # Always one of OBJECT_TYPE_INTERNAL_KEYS, regardless of what the project
    # has relabeled it to for display -- every place that branches on type
    # (template selection, checklist selection) keys off this internal value.
    type: Mapped[str] = mapped_column(String(30))
    # The project's own module vocabulary (ProjectModuleConfig) -- stored as
    # whatever string that project configured (e.g. "SD", or a client's own
    # name for it), not validated against a fixed list.
    module: Mapped[str] = mapped_column(String(40))
    complexity: Mapped[str] = mapped_column(String(20), default="Medium")

    # Human-friendly display id, e.g. "PP_F001" -- {module id-code}_{type
    # prefix}{zero-padded sequence}, assigned once at creation from
    # ProjectObjectIdCounter and never reused or reassigned. Nullable only
    # for the migration-safety reason explained throughout this file:
    # objects created before this feature existed just show no code.
    object_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    # Whole-object cancellation -- distinct from any one stage's status
    # (Blocked/On Hold are about a specific stage being stuck; this is "the
    # object itself is scrapped"). Nullable for the same migration-safety
    # reason; None reads the same as False everywhere this is used.
    cancelled: Mapped[bool | None] = mapped_column(Boolean, default=False, nullable=True)

    fsd_status: Mapped[str] = mapped_column(String(20), default="Not Started")
    feasibility_status: Mapped[str] = mapped_column(String(20), default="Not Started")
    tsd_status: Mapped[str] = mapped_column(String(20), default="Not Started")
    code_review_status: Mapped[str] = mapped_column(String(20), default="Not Started")
    unit_test_status: Mapped[str] = mapped_column(String(20), default="Not Started")
    code_status: Mapped[str] = mapped_column(String(20), default="Not Started")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    project: Mapped[Project] = relationship(back_populates="objects")
    fsd_drafts: Mapped[list["FsdDraft"]] = relationship(
        back_populates="object", cascade="all, delete-orphan", order_by="FsdDraft.version"
    )


# --- Project Brain: per-project terminology + document templates -----------
# Everything below is scoped to one project (cascades on project delete, same
# as TrackedObject) and lets that project's admin adapt CodeCanvas to how
# their specific client names things, without touching the fixed behavioral
# categories any agent logic keys off of.

class ProjectObjectTypeConfig(Base):
    """One row per (project, internal object-type category). Seeded with
    all six OBJECT_TYPE_INTERNAL_KEYS for every project (backend/
    project_brain_defaults.py) so there's always a full set to edit, never
    a blank slate. display_label is purely cosmetic; id_prefix feeds Object
    ID generation; enabled hides a category from "new object" without
    touching any object that already used it."""

    __tablename__ = "project_object_type_configs"
    __table_args__ = (UniqueConstraint("project_id", "internal_key", name="uq_potc_project_internal_key"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    internal_key: Mapped[str] = mapped_column(String(30))  # one of OBJECT_TYPE_INTERNAL_KEYS
    display_label: Mapped[str] = mapped_column(String(60))
    id_prefix: Mapped[str] = mapped_column(String(10))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class ProjectModuleConfig(Base):
    """A project's own list of SAP module values -- freely named (a client
    may call it something other than the SAP-standard code), with a short
    id_code used only for Object ID generation (kept separate from `name`
    so e.g. "WM/EWM" can still produce a clean "WMEWM" id segment)."""

    __tablename__ = "project_module_configs"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_pmc_project_name"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(40))  # the value actually stored on TrackedObject.module
    id_code: Mapped[str] = mapped_column(String(10))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class ProjectComplexityConfig(Base):
    __tablename__ = "project_complexity_configs"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_pcc_project_name"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(30))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class ProjectObjectIdCounter(Base):
    """A monotonic, never-reused counter per (project, "{module id_code}_
    {type id_prefix}") combination -- e.g. key="PP_F" produces PP_F001,
    PP_F002, .... Deleting the object that used a number never frees it,
    so two objects can never end up sharing a display id."""

    __tablename__ = "project_object_id_counters"
    __table_args__ = (UniqueConstraint("project_id", "key", name="uq_poic_project_key"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    key: Mapped[str] = mapped_column(String(40))
    next_seq: Mapped[int] = mapped_column(Integer, default=1)


class ProjectDocumentTemplate(Base):
    """Which template drives drafting for one (project, document_type,
    object-type category) combination. source == "in_built" (the default
    for every combination until someone uploads one) means the existing,
    hardcoded Python template is used exactly as before -- the fields below
    are only populated for source == "client_specific".

    Only FSD actually has a generation agent today (backend/agents/
    fsd_draft_templated.py reads sections_json/diagram_section_key/
    allow_ai_inferred). TSD / Code Review / Test Script configs can be
    saved ahead of time but aren't consumed by anything yet -- same honest
    "not built yet" posture as those stages elsewhere in the app."""

    __tablename__ = "project_document_templates"
    __table_args__ = (
        UniqueConstraint("project_id", "document_type", "object_type_key", name="uq_pdt_project_doctype_objtype"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    document_type: Mapped[str] = mapped_column(String(30))  # one of DOCUMENT_TYPES
    object_type_key: Mapped[str] = mapped_column(String(30))  # one of OBJECT_TYPE_INTERNAL_KEYS
    source: Mapped[str] = mapped_column(String(20), default="in_built")  # "in_built" | "client_specific"

    uploaded_filename: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Ordered [{"key": str, "title": str}, ...] -- replaces the built-in
    # template's section list entirely for this (document_type, object
    # type) once source == "client_specific". Auto-extracted from the
    # upload's headings, then admin-editable before saving.
    sections_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Which section key (if any) gets the Enhancement-style rendered
    # flow-diagram/wireframe treatment -- generalizes the old fixed
    # ENHANCEMENT_DIAGRAM_SECTION_KEY constant into an admin choice.
    diagram_section_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # Whether a section with nothing in the ledger may be filled from
    # general SAP knowledge (ai_inferred, clearly flagged) instead of
    # always stopping at needs_input -- mirrors the Enhancement template's
    # own default (True) vs the generic template's (False); admin-settable
    # per client template regardless of which object-type family it's for.
    allow_ai_inferred: Mapped[bool] = mapped_column(Boolean, default=False)
    # The uploaded file's own extracted text, kept so an admin can
    # re-download/review what was uploaded; not fed back into drafting.
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    updated_by: Mapped[str | None] = mapped_column(String(200), nullable=True)


class ProjectDocument(Base):
    """One uploaded file in a project's Repository (SOW, BPML, PDD, FDD, Big
    Rocks, project-specific Skill files, or Other) -- general reference
    material for the engagement, not consumed by any generation agent.
    Deliberately distinct from ProjectDocumentTemplate above: that one
    stores only extracted text to drive FSD section generation; this one
    stores the original file bytes so the exact uploaded document (a signed
    SOW PDF, a BPML Visio export, a roadmap deck) can be downloaded back
    unchanged. No text extraction, no parsing -- a file cabinet, not an
    input to the pipeline."""

    __tablename__ = "project_documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    category: Mapped[str] = mapped_column(String(20))  # one of PROJECT_DOCUMENT_CATEGORIES

    filename: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(150), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[bytes] = mapped_column(LargeBinary)

    notes: Mapped[str] = mapped_column(String(500), default="")
    uploaded_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class FsdDraft(Base):
    __tablename__ = "fsd_drafts"
    # Belt-and-suspenders against a double-fired generate request (e.g. a
    # retried request, or a client bug) ever creating two rows that both
    # claim the same version number for the same object.
    __table_args__ = (UniqueConstraint("object_id", "version", name="uq_fsd_drafts_object_version"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    object_id: Mapped[str] = mapped_column(ForeignKey("tracked_objects.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)

    sources_json: Mapped[list] = mapped_column(JSON)      # the SourceDocumentIn list used for this run
    ledger_json: Mapped[list] = mapped_column(JSON)        # list[LedgerEntry]
    sections_json: Mapped[list] = mapped_column(JSON)      # list[FSDSection]
    quality_score_json: Mapped[dict] = mapped_column(JSON) # QualityScore

    # The Intake Validation assessment -- a second, independent LLM call
    # (backend/agents/intake_validation.py) that runs right after a draft is
    # generated. Nullable/status-tracked rather than required: it must never
    # be allowed to fail the FSD generation itself, so a failure here is
    # recorded, not raised, and the user gets a "re-run" action instead of a
    # lost draft.
    intake_validation_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # IntakeValidationResult
    # Nullable (not NOT NULL default="pending") specifically so the lightweight
    # migration in backend/db.py can ADD COLUMN this onto an existing,
    # already-populated table without a DEFAULT clause -- a plain ALTER TABLE
    # ADD COLUMN ... NOT NULL fails against existing rows on Postgres. New
    # rows still get "pending" from the Python-side default below; existing
    # rows read back as NULL, which the API layer treats the same as "pending".
    intake_validation_status: Mapped[str | None] = mapped_column(String(20), default="pending", nullable=True)
    intake_validation_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Token usage + which model produced this run (backend/token_usage.py).
    # Nullable for the same migration-safety reason as the Intake Validation
    # columns above -- drafts generated before this tracking existed just
    # read back as None, which the API layer treats as "not tracked" rather
    # than a zero-cost run. run_breakdown_json is {"ledger_and_draft": {...},
    # "intake_validation": {...}} -- each value a TokenUsage dict (real
    # input/output token counts; cost is derived at read time, never stored,
    # so a pricing-table correction applies retroactively to old drafts too).
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    run_breakdown_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # "in_built" | "client_specific" | None (drafts from before Project
    # Brain templates existed). Drives whether the Enhancement template's
    # computed Document Identification / Validation table attach to this
    # draft -- those are keyed to the in-built Enhancement template's own
    # fixed section keys, so they're only meaningful when this draft
    # actually used that template, not an arbitrary client one.
    template_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    template_name: Mapped[str | None] = mapped_column(String(300), nullable=True)

    request_id: Mapped[str] = mapped_column(String(64), default="")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    # The real, logged-in requester's display name at generation time -- the
    # "author" the Enhancement template's Document Identification needs.
    # Captured once, here, rather than re-derived later: whoever approves or
    # exports this draft afterwards shouldn't change who it says authored it.
    generated_by: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Who actually approved, not a fixed assignee -- any logged-in user
    # with the matching role (enforced in routes_projects.py) can approve;
    # these record who really did, replacing the earlier hardcoded names.
    module_lead_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    module_lead_approved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    module_lead_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    solution_architect_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    solution_architect_approved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    solution_architect_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    note: Mapped[str] = mapped_column(Text, default="")  # e.g. "Regenerated Scope section"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    object: Mapped[TrackedObject] = relationship(back_populates="fsd_drafts")
