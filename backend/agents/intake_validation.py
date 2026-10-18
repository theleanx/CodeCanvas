"""
Intake Validation: a second, independent assessment of a finished FSD draft.

Where the FSD Creation pipeline's own QualityScore (backend/quality_score.py)
asks a narrow, mechanical question -- "does every section trace back to a
source document" -- this agent asks a broader one: "is this document actually
ready to hand to a developer?" It judges structure, specificity, testability,
and SAP delivery norms (clean-core approach, authorization, error handling,
dependencies), the same kind of audit an experienced reviewer would do before
signing off a spec.

It has no connection to a live SAP system, unlike the enterprise tool this
was modeled after (which verifies named objects -- BAdIs, tables, Fiori app
IDs -- against one via an MCP server). Rather than silently skip that or fake
a verdict, the prompt below is explicit: checklist items that would require
live-system verification get "cannot_verify", not a guessed pass or fail.
"""

from __future__ import annotations

import anthropic

from backend.config import ANTHROPIC_API_KEY, AGENT_MODEL, MAX_TOKENS_INTAKE_VALIDATION
from backend.intake_checklist import QUALITY_CHECK_DEFINITIONS, checklist_for_object_type
from backend.schemas import FSDSection, IntakeValidationResult
from backend.agents.json_utils import check_not_truncated, extract_json

SYSTEM_PROMPT = """You are the Intake Validation step of an SAP functional-spec \
delivery pipeline -- the quality gate a document passes through before a \
developer picks it up. You read a finished Functional Spec Document (FSD) \
and assess whether it is genuinely ready to build from, the way an \
experienced SAP solution architect reviewing a colleague's spec would.

You are judging the DOCUMENT ITSELF: whether it is clear, complete, \
internally consistent, and specific enough to build and test from. You have \
no connection to a live SAP system, so you cannot confirm that a named BAdI, \
table, or Fiori app ID actually exists or is released in any real system --\
never guess at that. For any checklist item that would require live-system \
verification to answer with confidence, set its status to "cannot_verify" \
and say so plainly in the finding (e.g. "Table EBAN is named but cannot be \
confirmed against a live system -- no SAP connection available"). Judge \
everything else -- is it named at all, is it specific, is it internally \
consistent -- which you CAN assess from the text alone.

Rules:
1. Be concrete. Every finding should reference what the document actually \
says (or doesn't), not a generic template sentence. Two different documents \
should never get the same finding text.
2. "pass" means genuinely solid, not merely present. A section that exists \
but is vague, generic, or internally inconsistent is "warn" at best.
3. "fail" is for a clear, material gap -- something a developer could not \
proceed without. "warn" is for something present but incomplete, ambiguous, \
or unconfirmed. Don't over-use "fail": most real gaps in an otherwise solid \
document are warnings, not failures.
4. The radar scores (0-100 each) are independent dimensions, not all the \
same number re-used eight times -- a document can be very clear (high \
Clarity) while still missing performance details (low Performance).
5. overall_pct is your own weighted judgment of the whole document's \
readiness, not a mechanical average of the radar scores (it may differ \
from their average). verdict: "ready" for genuinely build-ready (minor \
polish only), "needs_correction" for real but fixable gaps, "not_ready" \
for a document that needs substantial rework before it should be reviewed \
again.
6. corrections is a flat, prioritized list across everything you found -- \
not grouped by section. Order most severe first. Each entry is one \
specific, actionable instruction (name the section/field/assumption it \
refers to), not a restatement of a finding. Include at most ~15.
7. Grade every quality_check definition given to you, and every checklist \
item given to you -- do not add or drop items, do not invent new ones.
8. Output nothing but the single JSON object below, with all seven top-level \
keys present every time, even for a document that is almost entirely empty \
-- a sparse document still gets full quality_checks/corrections/checklist \
arrays (mostly "fail"/low scores), never a shortened or early-terminated \
response. Never include an aside, a self-correction, a note about your own \
process, or any text of any kind before or after the one JSON object -- if \
you notice a mistake while writing, simply continue and get the rest of the \
object right; do not restart, comment on it, or stop early.

Output ONLY a JSON object, no prose before or after, no markdown fence:
{
  "verdict": "ready"|"needs_correction"|"not_ready",
  "overall_pct": number (0-100),
  "radar": {"clarity": int, "completeness": int, "feasibility": int, "technical_detail": int, "business_value": int, "security": int, "performance": int, "compliance": int},
  "assessment": str (2-5 sentences, like a reviewer's summary -- name the specific strengths and the specific gaps that drove the verdict),
  "quality_checks": [{"key": str, "title": str, "status": "pass"|"warn"|"fail", "finding": str, "suggestion": str|null}],
  "corrections": [{"severity": "critical"|"high"|"medium"|"low", "text": str}],
  "checklist": [{"item_id": str, "category": str, "severity": str, "check": str, "status": "pass"|"warn"|"fail"|"cannot_verify", "finding": str}]
}
"""


def _format_fsd(sections: list[FSDSection]) -> str:
    parts = []
    for s in sections:
        parts.append(f"=== SECTION: {s.title} (status: {s.status}) ===")
        if s.status == "grounded":
            parts.append(s.content or "(empty)")
        elif s.status == "ai_inferred":
            parts.append(s.content or "(empty)")
            parts.append(f"[AI-inferred, not from the project's own documents: {s.ai_inferred_note}]")
        elif s.status == "needs_input":
            parts.append(f"[NEEDS INPUT: {s.needs_input_detail or 'no supporting input provided'}]")
        else:  # conflict
            parts.append(f"[CONFLICT: {s.conflict_detail or 'conflicting inputs, unresolved'}]")
        parts.append("")
    return "\n".join(parts)


def run_intake_validation(
    sections: list[FSDSection],
    object_name: str,
    object_type: str,
    object_module: str,
    project_name: str,
) -> IntakeValidationResult:
    """Occasionally the model leaks a self-correcting aside or closes the
    JSON object early instead of actually finishing it -- observed on a
    near-empty document (mostly needs_input sections), not a token-budget
    issue (stop_reason was "end_turn", well under the limit). The system
    prompt is explicit about never doing this, but a single retry is a
    cheap, standard safety net against the odd generation that still slips
    through, rather than surfacing "failed" to the user for something a
    second attempt would likely fix on its own."""
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            return _run_intake_validation_once(sections, object_name, object_type, object_module, project_name)
        except Exception as exc:
            last_error = exc
            if attempt == 0:
                continue
            raise
    raise last_error  # pragma: no cover -- unreachable, keeps type checkers happy


def _run_intake_validation_once(
    sections: list[FSDSection],
    object_name: str,
    object_type: str,
    object_module: str,
    project_name: str,
) -> IntakeValidationResult:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    checklist_items = checklist_for_object_type(object_type)

    checklist_block = "\n".join(
        f"- id={item['id']} category={object_type if item['id'][:3] != 'GEN' else 'General'} "
        f"severity={item['severity']}: {item['check']}"
        for item in checklist_items
    )
    quality_check_block = "\n".join(
        f"- key={qc['key']} title={qc['title']!r}: look for -- {qc['look_for']}" for qc in QUALITY_CHECK_DEFINITIONS
    )

    user_message = f"""OBJECT: {object_name} ({object_type}, module {object_module})
PROJECT: {project_name}

=== FSD DOCUMENT ===
{_format_fsd(sections)}

=== QUALITY CHECKS TO GRADE (grade all {len(QUALITY_CHECK_DEFINITIONS)}) ===
{quality_check_block}

=== CHECKLIST ITEMS TO GRADE (grade all {len(checklist_items)}) ===
{checklist_block}
"""

    response = client.messages.create(
        model=AGENT_MODEL,
        max_tokens=MAX_TOKENS_INTAKE_VALIDATION,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    check_not_truncated(response.stop_reason, MAX_TOKENS_INTAKE_VALIDATION)
    raw_text = "".join(block.text for block in response.content if block.type == "text")
    data = extract_json(raw_text)

    return IntakeValidationResult.model_validate(data)
