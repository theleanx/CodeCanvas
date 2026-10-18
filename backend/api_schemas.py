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

from backend.schemas import FSDSection, IntakeValidationResult, LedgerEntry, QualityScore, SourceDocument


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
    # Always one of the six fixed internal categories (models_db.
    # OBJECT_TYPE_INTERNAL_KEYS) -- a project can relabel these for display
    # (Project Brain) but never add a new one, so this stays a Literal.
    type: ObjectType
    # module/complexity are each validated against the project's own
    # Project Brain configuration at the route level (routes_projects.py),
    # not against a fixed Literal -- every project can define its own list.
    module: str = Field(..., min_length=1, max_length=40)
    complexity: str = Field("Medium", max_length=20)


PipelineStageKey = Literal["fsd", "feasibility", "tsd", "code_review", "unit_test", "code"]


class ObjectStatusPatch(BaseModel):
    stage: PipelineStageKey
    status: PipelineStage


class ObjectCancelPatch(BaseModel):
    cancelled: bool


class ObjectOut(BaseModel):
    id: str
    project_id: str
    name: str
    # Human-friendly display id, e.g. "PP_F001" -- None for objects created
    # before this feature existed.
    object_code: Optional[str] = None
    type: str
    module: str
    complexity: str
    cancelled: bool = False
    fsd_status: str
    feasibility_status: str
    tsd_status: str
    code_review_status: str
    unit_test_status: str
    code_status: str
    # Computed, never stored -- see backend/project_brain.py.
    # compute_overall_status: "Not Started" / "Complete" / "Cancelled", or
    # "{current stage} {its status}" (e.g. "TSD On Hold").
    overall_status: str = "Not Started"
    latest_fsd_version: Optional[int] = None

    model_config = {"from_attributes": True}


# --- FSD drafts --------------------------------------------------------------

class FsdGenerateRequest(BaseModel):
    sources: list[SourceDocument] = Field(..., min_length=1)
    note: str = ""


class ApprovalPatch(BaseModel):
    role: Literal["module_lead", "solution_architect"]
    approved: bool  # false = withdraw this approval


class TokenUsageOut(BaseModel):
    """Real token counts for one LLM call (or a sum of several), plus a
    dollar estimate -- None when the configured model isn't in the
    documented pricing table in backend/token_usage.py, rather than a
    guessed figure."""

    input_tokens: int
    output_tokens: int
    cost_usd: Optional[float] = None


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
    # Only populated for the Enhancement template -- Document Identification,
    # Review & Sign-off, and the mandatory Validation Point table. None for
    # every other object type, which still uses the generic nine-section FSD.
    document_identification: Optional[dict] = None
    review_signoff: Optional[list[dict]] = None
    validation_table: Optional[list[dict]] = None
    # Intake Validation runs as its own LLM call right after a draft is
    # generated and must never be allowed to fail the generation itself, so
    # it's tracked with a status rather than required: "pending" briefly
    # while generate_fsd_draft is still running it, "complete" with `result`
    # populated, or "failed" with `error` set and `result` None -- the
    # frontend offers a manual re-run in the failed case.
    intake_validation_status: Literal["pending", "complete", "failed"] = "pending"
    intake_validation: Optional[IntakeValidationResult] = None
    intake_validation_error: Optional[str] = None
    # Token usage, per pipeline step, for this draft's generation run plus
    # whichever Intake Validation attempt last succeeded or failed cleanly
    # (see backend/token_usage.py) -- None for drafts generated before this
    # tracking existed. A failed LLM call's tokens aren't counted (see
    # _run_intake_validation_safely): this is an estimate for the user's own
    # visibility, not a billing record.
    model_used: Optional[str] = None
    token_usage_breakdown: Optional[dict[str, TokenUsageOut]] = None
    token_usage_total: Optional[TokenUsageOut] = None
    # Which template actually drafted this -- "client_specific" means
    # document_identification/review_signoff/validation_table above are
    # always None even for an Enhancement-type object, since those three
    # are computed against the in-built Enhancement template's own fixed
    # section keys specifically, not any arbitrary client template.
    template_source: Optional[Literal["in_built", "client_specific"]] = None
    template_name: Optional[str] = None


# --- Project Brain: object-type/module/complexity config, document templates -

class ObjectTypeConfigOut(BaseModel):
    internal_key: str
    display_label: str
    id_prefix: str
    enabled: bool
    sort_order: int

    model_config = {"from_attributes": True}


class ObjectTypeConfigPatch(BaseModel):
    display_label: Optional[str] = Field(None, min_length=1, max_length=60)
    id_prefix: Optional[str] = Field(None, min_length=1, max_length=10)
    enabled: Optional[bool] = None


class ModuleConfigOut(BaseModel):
    id: str
    name: str
    id_code: str
    enabled: bool
    sort_order: int

    model_config = {"from_attributes": True}


class ModuleConfigCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=40)
    id_code: Optional[str] = Field(None, min_length=1, max_length=10)


class ModuleConfigPatch(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=40)
    id_code: Optional[str] = Field(None, min_length=1, max_length=10)
    enabled: Optional[bool] = None


class ComplexityConfigOut(BaseModel):
    id: str
    name: str
    enabled: bool
    sort_order: int

    model_config = {"from_attributes": True}


class ComplexityConfigCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=30)


class ComplexityConfigPatch(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=30)
    enabled: Optional[bool] = None


class DocumentTemplateSection(BaseModel):
    key: str
    title: str


class DocumentTemplateOut(BaseModel):
    document_type: str
    object_type_key: str
    source: Literal["in_built", "client_specific"] = "in_built"
    uploaded_filename: Optional[str] = None
    sections: Optional[list[DocumentTemplateSection]] = None
    diagram_section_key: Optional[str] = None
    allow_ai_inferred: bool = False
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None
    # The in-built default's own section list, for preview/comparison and as
    # what "Use In-Built" reverts to -- None where no in-built template
    # exists yet for this document_type (see generation_available below).
    in_built_sections: Optional[list[DocumentTemplateSection]] = None
    # True only for (document_type, object_type_key) combinations that an
    # actual generation agent consumes today -- just FSD for every type,
    # right now. A template can still be configured and saved for the
    # others ahead of their own generation step being built; the UI uses
    # this to say so honestly instead of implying it already does something.
    generation_available: bool = False


class DocumentTemplateUploadResponse(BaseModel):
    filename: str
    sections: list[DocumentTemplateSection]
    raw_text: str
    char_count: int


class DocumentTemplateSave(BaseModel):
    source: Literal["in_built", "client_specific"]
    uploaded_filename: Optional[str] = None
    sections: Optional[list[DocumentTemplateSection]] = None
    diagram_section_key: Optional[str] = None
    allow_ai_inferred: bool = False
    raw_text: Optional[str] = None
