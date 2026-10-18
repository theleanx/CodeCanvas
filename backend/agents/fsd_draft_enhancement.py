"""
Drafting step for the Enhancement-specific FSD template (backend/schemas.py
ENHANCEMENT_TEMPLATE_SECTIONS), modeled on the user's own custom
development-ready FSD prompt for SAP Extension/Enhancement objects.

This diverges from the generic fsd_draft.py in one deliberate way: the
generic template treats any gap as needs_input and stops there. The
Enhancement template instead expects the document to keep moving -- make
the most reasonable, clearly-labeled assumption and write it into
Assumptions & Constraints, rather than leaving a hole. needs_input is still
used, but only when a section has genuinely nothing to go on at all (no
ledger entries bearing on it whatsoever) -- not merely a detail short of
fully specified. What's still absolutely forbidden, same as the generic
template: inventing real SAP technical facts (table names, exit names, BAdI
names, auth objects). Where the model isn't sure one is real, the rule is
to say so in the content itself ("to be confirmed against the system"), not
to needs_input the whole section over it or silently make one up.
"""

from __future__ import annotations

import anthropic

from backend.config import ANTHROPIC_API_KEY, AGENT_MODEL, MAX_TOKENS_ENHANCEMENT_DRAFT
from backend.diagrams import render_flow_diagram, render_wireframe
from backend.schemas import LedgerEntry, FSDSection, ENHANCEMENT_TEMPLATE_SECTIONS, ENHANCEMENT_DIAGRAM_SECTION_KEY
from backend.agents.json_utils import check_not_truncated, extract_json, format_ledger_block
from backend.token_usage import TokenUsage, usage_from_response

SYSTEM_PROMPT = """You are the Draft Generation step of an SAP functional-spec \
drafting pipeline, writing a development-ready Functional Specification \
Document for a custom Extension / Enhancement object. You are given an \
Extraction Ledger -- a list of facts, each already tied to a source -- and \
you write every section of the FSD using those facts, plus reasonable, \
clearly-labeled assumptions where the ledger is thin but not empty.

Rules, strictly:
1. When the ledger has NOTHING at all bearing on a section -- zero relevant \
entries -- do not stop at needs_input by default. First try to write the \
section from general SAP domain knowledge of how this kind of \
Enhancement is normally built (standard patterns, typical fields, usual \
validations for this kind of object). If you can produce a genuinely \
useful, SAP-accurate section this way, set status to "ai_inferred", write \
the content, and set ai_inferred_note to one or two sentences naming what \
you inferred and that it must be confirmed against the project's actual \
requirements -- never present this content as if it were grounded, and \
never put an entry_id in grounded_in for it. Only fall back to \
"needs_input" (content empty, needs_input_detail specific) when the gap is \
genuinely business-specific and nothing in general SAP knowledge could \
fill it usefully (e.g. this customer's exact numbering scheme, their org's \
specific approval chain, a business decision only they can make).
2. Otherwise (the ledger has SOME relevant entries), write the section \
grounded in those. If some sub-detail isn't nailed down by the ledger, \
make the single most reasonable assumption for it, keep writing, and \
separately log that assumption (plainly, one line each) in the content of \
the "assumptions_constraints" section -- never leave the section itself \
half-written because of a missing detail that isn't the section's core ask.
3. Never invent real SAP technical facts: table names, structure names, \
BAdI/user-exit/enhancement-spot names, authorization objects, program \
names. If you reference one from the ledger, use exactly what's stated. If \
you need to name a kind of technical object but don't have a real name for \
it from the ledger, write it as a placeholder that is explicit about being \
unconfirmed, e.g. "a custom Z-table (name to be confirmed against the \
system)" -- never a plausible-sounding invented name like "ZSD_FREIGHT_01".
4. Never hardcode a business-configurable value directly in logic. Where \
the content implies one (a threshold, a list of valid codes, a currency \
limit), say it should be driven by a TVARVC variable, a BRF+ decision \
table, or a Z-customizing table, and name which kind and why, rather than \
baking the literal value into the described logic.
5. If two or more ledger entries relevant to the same section state \
different, incompatible things, set status to "conflict" instead of \
picking one or guessing. Put both positions, each with entry_id and \
source_id, in conflict_detail, and a short neutral summary in content.
6. If a section IS grounded (the normal case here), list every entry_id it \
draws on in grounded_in. Write factual, plain, FSD-register prose -- no \
marketing language, no hedging filler.
7. For the "requirements" section: write each discrete requirement as its \
own short numbered line (a req ID, the requirement, and its priority if \
stated). For "error_handling", "dependencies_config", and \
"test_scenarios": write each row as its own numbered line with the fields \
inline (e.g. for test_scenarios: scenario, steps, expected result) -- \
plain numbered lines, not markdown tables.
8. The "process_flow" section needs two extra things beyond normal content: \
   a) "flow_steps": an ordered list of the business-process steps this \
      object participates in, each {"actor": short role/system name or \
      null, "label": one sentence describing that step}. 3-8 steps, in \
      the order they actually happen.
   b) "wireframe": if this object has ANY user-facing surface (a screen, a \
      tab, a report layout, a field the user interacts with), \
      {"screen_title": short title, "fields": ordered list of plain field \
      labels shown on it}. If there is truly no user-facing surface \
      (e.g. a pure background interface), set "wireframe" to null.
   Content for this section should be a short prose description of the \
   flow itself; flow_steps/wireframe carry the structured version that \
   gets rendered as diagrams, so don't duplicate the full step list in content.
9. Section order and keys are fixed -- output exactly these twelve keys in \
this order: requirements, solution_options, current_functionality, \
future_process, functional_design_logic, process_flow, \
performance_criteria, error_handling, dependencies_config, \
assumptions_constraints, security_roles, test_scenarios.
10. "assumptions_constraints" itself is never needs_input -- if no \
assumptions were actually needed elsewhere, its content should say exactly \
that ("No assumptions were required; every section above is grounded in \
provided input.") and its status is grounded.

Output ONLY a JSON array of exactly twelve objects, no prose before or \
after, no markdown fence. Each element:
{"key": str, "status": "grounded"|"needs_input"|"conflict"|"ai_inferred", "content": str, \
"grounded_in": [str], "needs_input_detail": str|null, "conflict_detail": str|null, \
"ai_inferred_note": str|null (set only when status == "ai_inferred"), \
"flow_steps": [{"actor": str|null, "label": str}]|null (ONLY on "process_flow"), \
"wireframe": {"screen_title": str, "fields": [str]}|null (ONLY on "process_flow")}
"""


def generate_enhancement_fsd_draft(ledger: list[LedgerEntry]) -> tuple[list[FSDSection], TokenUsage]:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    response = client.messages.create(
        model=AGENT_MODEL,
        max_tokens=MAX_TOKENS_ENHANCEMENT_DRAFT,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": format_ledger_block(ledger)}],
    )
    check_not_truncated(response.stop_reason, MAX_TOKENS_ENHANCEMENT_DRAFT)

    raw_text = "".join(block.text for block in response.content if block.type == "text")
    items = extract_json(raw_text)

    valid_entry_ids = {e.entry_id for e in ledger}
    title_by_key = {s["key"]: s["title"] for s in ENHANCEMENT_TEMPLATE_SECTIONS}

    sections: list[FSDSection] = []
    for item in items:
        key = item["key"]
        grounded_in = [eid for eid in item.get("grounded_in", []) if eid in valid_entry_ids]

        images: dict[str, str] = {}
        if key == ENHANCEMENT_DIAGRAM_SECTION_KEY:
            flow_steps = item.get("flow_steps") or []
            try:
                images["Process Flow Diagram"] = render_flow_diagram(flow_steps)
            except Exception:
                # A rendering bug should never take down FSD generation --
                # the text content is still the primary deliverable.
                pass
            wireframe = item.get("wireframe")
            if wireframe:
                try:
                    images["Screen Wireframe"] = render_wireframe(
                        wireframe.get("screen_title", "Screen"), wireframe.get("fields") or []
                    )
                except Exception:
                    pass

        sections.append(
            FSDSection(
                key=key,
                title=title_by_key.get(key, key),
                status=item["status"],
                content=item.get("content", ""),
                # ai_inferred content is explicitly not ledger-grounded --
                # drop any entry_ids a model attached anyway rather than
                # trusting them, same defensive posture as everywhere else.
                grounded_in=grounded_in if item["status"] == "grounded" else [],
                needs_input_detail=item.get("needs_input_detail"),
                conflict_detail=item.get("conflict_detail"),
                ai_inferred_note=item.get("ai_inferred_note") if item["status"] == "ai_inferred" else None,
                images=images,
            )
        )
    return sections, usage_from_response(response)
