"""The full FSD Creation agent pipeline: inputs -> ledger -> draft -> score.

This is the one function the API layer (and, later, the frontend) calls.
Nothing in here is SAP-specific or UI-specific -- it's pure agent logic,
which is exactly why it's worth proving out before any of that exists.
"""

from __future__ import annotations

from backend.schemas import SourceDocument, FSDDraft, ResolvedFsdTemplate
from backend.agents.extraction_ledger import build_extraction_ledger
from backend.agents.fsd_draft import generate_fsd_draft
from backend.agents.fsd_draft_enhancement import generate_enhancement_fsd_draft
from backend.agents.fsd_draft_templated import generate_templated_fsd_draft
from backend.quality_score import compute_quality_score


def run_fsd_creation(
    sources: list[SourceDocument],
    object_type: str | None = None,
    template: ResolvedFsdTemplate | None = None,
) -> FSDDraft:
    """template is None for the overwhelming majority of runs -- the
    in-built generic/Enhancement templates, exactly as before this
    parameter existed. It's only set when routes_projects.py resolved a
    "client_specific" ProjectDocumentTemplate for this object's type, in
    which case its section list entirely replaces the in-built one."""
    ledger, ledger_usage = build_extraction_ledger(sources)
    if template is not None:
        sections, draft_usage = generate_templated_fsd_draft(
            ledger, template.sections, template.diagram_section_key, template.allow_ai_inferred
        )
    elif object_type == "Enhancement":
        sections, draft_usage = generate_enhancement_fsd_draft(ledger)
    else:
        sections, draft_usage = generate_fsd_draft(ledger)
    score = compute_quality_score(sections)
    return FSDDraft(sections=sections, ledger=ledger, quality_score=score, token_usage=ledger_usage + draft_usage)
