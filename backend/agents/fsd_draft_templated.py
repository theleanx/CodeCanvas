"""
Drafting step for a client-specific FSD template (Project Brain ->
Document Templates, source == "client_specific"): the same ledger-grounded
drafting as backend/agents/fsd_draft.py and fsd_draft_enhancement.py, but
against an arbitrary, admin-supplied section list instead of one of the two
built-in ones.

This is deliberately a third function rather than a generalization bolted
onto the existing two -- fsd_draft.py and fsd_draft_enhancement.py stay
exactly as they were (zero regression risk for every object that still
uses the in-built templates), and this one is only ever called when
routes_projects.py has actually resolved a client-specific
ProjectDocumentTemplate for the object being drafted.
"""

from __future__ import annotations

import anthropic

from backend.config import ANTHROPIC_API_KEY, AGENT_MODEL, MAX_TOKENS_ENHANCEMENT_DRAFT
from backend.diagrams import render_flow_diagram, render_wireframe
from backend.schemas import LedgerEntry, FSDSection
from backend.agents.json_utils import check_not_truncated, extract_json, format_ledger_block
from backend.token_usage import TokenUsage, usage_from_response

_BASE_RULES = """You are the Draft Generation step of an SAP functional-spec \
drafting pipeline, writing a Functional Specification Document against a \
client-specific template this project configured. You are given an \
Extraction Ledger -- a list of facts, each already tied to a source -- and \
you write every section listed below using those facts.

Rules, strictly:
1. Never invent content. If a section has no ledger entries that speak to \
it at all, set its status to "needs_input", leave content empty, and write \
a one- or two-sentence needs_input_detail describing specifically what's \
missing (not a generic "no input provided").
2. If two or more ledger entries relevant to the same section state \
different, incompatible things, set status to "conflict" instead of \
picking one or guessing. Put both positions, each with entry_id and \
source_id, in conflict_detail, and a short neutral summary in content.
3. If a section IS grounded, list every entry_id it draws on in \
grounded_in. Write clear, professional FSD-register prose -- no marketing \
language, no hedging filler -- and never go beyond what the cited entries \
actually support.
4. Never invent real SAP technical facts: table names, structure names, \
BAdI/user-exit/enhancement-spot names, authorization objects, program \
names. If you reference one from the ledger, use exactly what's stated. If \
you need to name a kind of technical object but don't have a real name for \
it from the ledger, write it as a placeholder explicit about being \
unconfirmed, e.g. "a custom Z-table (name to be confirmed against the \
system)" -- never a plausible-sounding invented name.
5. Never hardcode a business-configurable value directly in logic. Where \
the content implies one (a threshold, a list of valid codes, a currency \
limit), say it should be driven by a TVARVC variable, a BRF+ decision \
table, or a Z-customizing table, and name which kind and why.
"""

_AI_INFERRED_RULE = """6. When a section has NOTHING at all bearing on it in the ledger, don't \
stop at needs_input by default. First try to write it from general SAP \
domain knowledge of how this kind of object is normally built. If you can \
produce a genuinely useful, SAP-accurate section this way, set status to \
"ai_inferred", write the content, and set ai_inferred_note to one or two \
sentences naming what you inferred and that it must be confirmed against \
the project's actual requirements -- never present this as grounded, and \
never put an entry_id in grounded_in for it. Only fall back to \
"needs_input" when the gap is genuinely business-specific and nothing in \
general SAP knowledge could fill it usefully.
"""

_NO_AI_INFERRED_RULE = """6. Never use "ai_inferred" as a status for this template -- a section \
with nothing in the ledger is always "needs_input", however confident a \
general-knowledge guess might be. This template's project configured it \
to stop and ask rather than infer.
"""

_DIAGRAM_RULE_TEMPLATE = """7. The "{key}" section needs two extra things beyond normal content:
   a) "flow_steps": an ordered list of the business-process steps this \
object participates in, each {{"actor": short role/system name or null, \
"label": one sentence describing that step}}. 3-8 steps, in the order they \
actually happen.
   b) "wireframe": if this object has ANY user-facing surface (a screen, a \
tab, a report layout, a field the user interacts with), {{"screen_title": \
short title, "fields": ordered list of plain field labels shown on it}}. \
If there is truly no user-facing surface, set "wireframe" to null.
   Content for this section should be a short prose description of the \
flow itself; flow_steps/wireframe carry the structured version that gets \
rendered as diagrams, so don't duplicate the full step list in content.
"""


def _build_system_prompt(sections: list[dict], diagram_section_key: str | None, allow_ai_inferred: bool) -> str:
    rule_num = 6
    parts = [_BASE_RULES]
    parts.append(_AI_INFERRED_RULE if allow_ai_inferred else _NO_AI_INFERRED_RULE)
    rule_num += 1

    if diagram_section_key:
        parts.append(_DIAGRAM_RULE_TEMPLATE.format(key=diagram_section_key))
        rule_num += 1

    section_order = ", ".join(s["key"] for s in sections)
    parts.append(
        f"{rule_num}. Section order and keys are fixed -- output exactly these "
        f"{len(sections)} keys in this order: {section_order}.\n"
    )

    status_values = '"grounded"|"needs_input"|"conflict"' + ('|"ai_inferred"' if allow_ai_inferred else "")
    schema_fields = (
        f'{{"key": str, "status": {status_values}, "content": str, '
        f'"grounded_in": [str], "needs_input_detail": str|null, "conflict_detail": str|null'
    )
    if allow_ai_inferred:
        schema_fields += ', "ai_inferred_note": str|null (set only when status == "ai_inferred")'
    if diagram_section_key:
        schema_fields += (
            f', "flow_steps": [{{"actor": str|null, "label": str}}]|null (ONLY on "{diagram_section_key}"), '
            f'"wireframe": {{"screen_title": str, "fields": [str]}}|null (ONLY on "{diagram_section_key}")'
        )
    schema_fields += "}"

    parts.append(
        f"Output ONLY a JSON array of exactly {len(sections)} objects, no prose before or after, "
        f"no markdown fence. Each element:\n{schema_fields}\n"
    )
    return "\n".join(parts)


def generate_templated_fsd_draft(
    ledger: list[LedgerEntry],
    sections: list[dict],
    diagram_section_key: str | None,
    allow_ai_inferred: bool,
) -> tuple[list[FSDSection], TokenUsage]:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    system_prompt = _build_system_prompt(sections, diagram_section_key, allow_ai_inferred)

    response = client.messages.create(
        model=AGENT_MODEL,
        max_tokens=MAX_TOKENS_ENHANCEMENT_DRAFT,
        system=system_prompt,
        messages=[{"role": "user", "content": format_ledger_block(ledger)}],
    )
    check_not_truncated(response.stop_reason, MAX_TOKENS_ENHANCEMENT_DRAFT)

    raw_text = "".join(block.text for block in response.content if block.type == "text")
    items = extract_json(raw_text)

    valid_entry_ids = {e.entry_id for e in ledger}
    title_by_key = {s["key"]: s["title"] for s in sections}

    result: list[FSDSection] = []
    for item in items:
        key = item["key"]
        status = item["status"]
        grounded_in = [eid for eid in item.get("grounded_in", []) if eid in valid_entry_ids]

        images: dict[str, str] = {}
        if diagram_section_key and key == diagram_section_key:
            flow_steps = item.get("flow_steps") or []
            try:
                images["Process Flow Diagram"] = render_flow_diagram(flow_steps)
            except Exception:
                pass
            wireframe = item.get("wireframe")
            if wireframe:
                try:
                    images["Screen Wireframe"] = render_wireframe(
                        wireframe.get("screen_title", "Screen"), wireframe.get("fields") or []
                    )
                except Exception:
                    pass

        result.append(
            FSDSection(
                key=key,
                title=title_by_key.get(key, key),
                status=status,
                content=item.get("content", ""),
                grounded_in=grounded_in if status == "grounded" else [],
                needs_input_detail=item.get("needs_input_detail"),
                conflict_detail=item.get("conflict_detail"),
                ai_inferred_note=item.get("ai_inferred_note") if status == "ai_inferred" else None,
                images=images,
            )
        )
    return result, usage_from_response(response)
