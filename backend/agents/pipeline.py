"""The full FSD Creation agent pipeline: inputs -> ledger -> draft -> score.

This is the one function the API layer (and, later, the frontend) calls.
Nothing in here is SAP-specific or UI-specific -- it's pure agent logic,
which is exactly why it's worth proving out before any of that exists.
"""

from __future__ import annotations

from backend.schemas import SourceDocument, FSDDraft
from backend.agents.extraction_ledger import build_extraction_ledger
from backend.agents.fsd_draft import generate_fsd_draft
from backend.agents.fsd_draft_enhancement import generate_enhancement_fsd_draft
from backend.quality_score import compute_quality_score


def run_fsd_creation(sources: list[SourceDocument], object_type: str | None = None) -> FSDDraft:
    ledger, ledger_usage = build_extraction_ledger(sources)
    if object_type == "Enhancement":
        sections, draft_usage = generate_enhancement_fsd_draft(ledger)
    else:
        sections, draft_usage = generate_fsd_draft(ledger)
    score = compute_quality_score(sections)
    return FSDDraft(sections=sections, ledger=ledger, quality_score=score, token_usage=ledger_usage + draft_usage)
