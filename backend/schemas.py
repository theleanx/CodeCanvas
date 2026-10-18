"""
Core data model for the FSD Creation agent.

Everything downstream (the API, the quality score, the FSD Review UI) is built
on this shape, so it's kept deliberately small and literal:

    SourceDocument  -- one piece of raw input (typed context, BRD, transcript,
                        a Project Brain doc). Each gets a source_id so every
                        later fact can point back at exactly where it came from.

    LedgerEntry      -- one atomic fact/requirement extracted from a source,
                        with the source it came from and the exact text that
                        supports it. This is the "Extraction Ledger" from the
                        architecture doc -- the thing that makes grounding
                        checkable instead of just asserted.

    FSDSection       -- one section of the generated FSD, always in one of
                        three states: grounded, needs_input, or conflict.
                        There is no fourth state where content is invented
                        without ledger support -- that's the whole point.
"""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


class SourceDocument(BaseModel):
    source_id: str = Field(..., description="Stable id, e.g. 'typed_context', 'brd', 'transcript', 'project_brain:SOW.pdf'")
    label: str = Field(..., description="Human-readable label shown in citations, e.g. 'BRD_CustomerMaster_v2.docx'")
    doc_type: str = Field(..., description="e.g. 'Typed Context', 'Business Requirement Document', 'Meeting Transcript', 'Process Flow Diagram', 'Project Brain'")
    text: str = Field(..., description="Raw extracted text of the document/transcript/typed note")


class LedgerEntry(BaseModel):
    entry_id: str
    fact: str = Field(..., description="One atomic requirement or fact, stated plainly")
    source_id: str
    source_quote: str = Field(..., description="The exact (or tightly paraphrased) text this fact is grounded in")
    topic_hint: Optional[str] = Field(None, description="Which FSD section this most likely belongs to, per the model's own read")


FSDSectionStatus = Literal["grounded", "needs_input", "conflict"]

FSD_TEMPLATE_SECTIONS: list[dict] = [
    {"key": "business_background", "title": "Business Background"},
    {"key": "context", "title": "Context"},
    {"key": "business_problem", "title": "Business Problem"},
    {"key": "business_impact", "title": "Business Impact"},
    {"key": "business_requirement", "title": "Business Requirement"},
    {"key": "solution_approach", "title": "Solution Approach"},
    {"key": "scope", "title": "Scope"},
    {"key": "functional_design", "title": "Functional Design"},
    {"key": "technical_approach", "title": "Technical Approach"},
]

# A second, much more specific template used only for object type
# "Enhancement" -- modeled directly on the custom development-ready FSD
# prompt the user supplied (SAP custom Extension / Enhancement objects).
# Document Identification, the Validation table, and Review & Sign-off are
# NOT in this list: they're derived from object/draft/approval metadata in
# backend/fsd_enhancement_meta.py rather than drafted by the model, since
# that data already exists and is more reliable computed than generated.
ENHANCEMENT_TEMPLATE_SECTIONS: list[dict] = [
    {"key": "requirements", "title": "Requirements"},
    {"key": "solution_options", "title": "Solution Options"},
    {"key": "current_functionality", "title": "Current Functionality"},
    {"key": "future_process", "title": "Future Process / Required Functionality"},
    {"key": "functional_design_logic", "title": "Functional Design & Process Logic"},
    {"key": "process_flow", "title": "Process Flow"},
    {"key": "performance_criteria", "title": "Performance Criteria"},
    {"key": "error_handling", "title": "Error Handling"},
    {"key": "dependencies_config", "title": "Dependencies & Dependent Configuration"},
    {"key": "assumptions_constraints", "title": "Assumptions & Constraints"},
    {"key": "security_roles", "title": "Security and Roles"},
    {"key": "test_scenarios", "title": "Functional Unit Test Scenarios"},
]

# The one section (per the attached prompt) that must carry rendered
# diagrams -- a process-flow flowchart always, plus a screen wireframe
# whenever the object has a user-facing surface.
ENHANCEMENT_DIAGRAM_SECTION_KEY = "process_flow"


def get_template_sections(object_type: str | None) -> list[dict]:
    """Which FSD template an object type drafts against. Enhancement gets
    the richer, diagram-bearing template; everything else keeps the
    original generic nine-section one."""
    if object_type == "Enhancement":
        return ENHANCEMENT_TEMPLATE_SECTIONS
    return FSD_TEMPLATE_SECTIONS


class FSDSection(BaseModel):
    key: str
    title: str
    status: FSDSectionStatus
    content: str = Field("", description="Drafted text. Empty (or a short pointer) when status != grounded")
    grounded_in: list[str] = Field(default_factory=list, description="entry_ids from the ledger this section draws on")
    needs_input_detail: Optional[str] = Field(None, description="What's missing, when status == needs_input")
    conflict_detail: Optional[str] = Field(None, description="Both positions and their sources, when status == conflict")
    images: dict[str, str] = Field(
        default_factory=dict,
        description="Rendered diagrams for this section, as {label: base64-png-bytes}. Only ever "
        "populated on the Enhancement template's 'process_flow' section (a flowchart, plus a "
        "wireframe when the object has a user-facing surface). Never model-generated pixels -- "
        "always rendered deterministically server-side from structured, model-supplied content.",
    )


class QualityScore(BaseModel):
    green_pct: float
    yellow_pct: float
    red_pct: float
    overall_pct: float
    tier: Literal["pass", "pass_with_condition", "not_advisable"]
    requires_dual_approval: bool
    red_items: list[str]
    yellow_items: list[str]


class FSDDraft(BaseModel):
    sections: list[FSDSection]
    ledger: list[LedgerEntry]
    quality_score: QualityScore
