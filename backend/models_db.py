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

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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


class TrackedObject(Base):
    __tablename__ = "tracked_objects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(30))  # Report | Interface | Conversion | Enhancement | Form | Workflow
    module: Mapped[str] = mapped_column(String(20))  # SD | MM | PP | QM | WM/EWM | FI/CO | BTP
    complexity: Mapped[str] = mapped_column(String(10), default="Medium")  # Low | Medium | High

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

    request_id: Mapped[str] = mapped_column(String(64), default="")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)

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
