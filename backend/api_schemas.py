"""Pydantic request/response shapes for the CRUD API layer.

Kept separate from backend/schemas.py (the agent's own in-memory shapes)
and from backend/models_db.py (the ORM rows) on purpose: this is the one
layer allowed to change shape to suit the frontend without dragging the
other two along with it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from backend.schemas import FSDSection, LedgerEntry, QualityScore, SourceDocument


# --- Auth --------------------------------------------------------------------

UserRole = Literal["admin", "module_lead", "solution_architect", "contributor"]


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: UserRole

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserOut


# --- Projects --------------------------------------------------------------

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    kind: Literal["Greenfield", "Brownfield"] = "Greenfield"
    system_description: str = ""
    industry: str = ""
    geography: str = ""


class ProjectOut(BaseModel):
    id: str
    name: str
    kind: str
    system_description: str
    industry: str
    geography: str
    object_count: int
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Objects -----------------------------------------------------------------

ObjectType = Literal["Report", "Interface", "Conversion", "Enhancement", "Form", "Workflow"]
ObjectModule = Literal["SD", "MM", "PP", "QM", "WM/EWM", "FI/CO", "BTP"]
ObjectComplexity = Literal["Low", "Medium", "High"]
PipelineStage = Literal["Not Started", "In Progress", "Blocked", "On Hold", "Complete"]


class ObjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    type: ObjectType
    module: ObjectModule
    complexity: ObjectComplexity = "Medium"


class ObjectOut(BaseModel):
    id: str
    project_id: str
    name: str
    type: str
    module: str
    complexity: str
    fsd_status: str
    feasibility_status: str
    tsd_status: str
    code_review_status: str
    unit_test_status: str
    code_status: str
    latest_fsd_version: Optional[int] = None

    model_config = {"from_attributes": True}


# --- FSD drafts --------------------------------------------------------------

class FsdGenerateRequest(BaseModel):
    sources: list[SourceDocument] = Field(..., min_length=1)
    note: str = ""


class ApprovalPatch(BaseModel):
    role: Literal["module_lead", "solution_architect"]
    approved: bool  # false = withdraw this approval


class FsdDraftSummary(BaseModel):
    id: str
    version: int
    created_at: datetime
    request_id: str
    duration_ms: int
    overall_pct: float
    tier: str
    note: str

    model_config = {"from_attributes": True}


class ApprovalState(BaseModel):
    module_lead_approved: bool
    module_lead_approved_by: Optional[str] = None
    module_lead_approved_at: Optional[datetime] = None
    solution_architect_approved: bool
    solution_architect_approved_by: Optional[str] = None
    solution_architect_approved_at: Optional[datetime] = None


class FsdDraftOut(BaseModel):
    id: str
    object_id: str
    version: int
    created_at: datetime
    request_id: str
    duration_ms: int
    sources: list[SourceDocument]
    ledger: list[LedgerEntry]
    sections: list[FSDSection]
    quality_score: QualityScore
    approvals: ApprovalState
    note: str
