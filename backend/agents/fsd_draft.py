"""
Step 2 of the FSD Creation pipeline: turn the Extraction Ledger into the nine
default FSD sections.

The contract that matters: a section is only ever grounded, needs_input, or
conflict. There is no path where the model fills a gap with a plausible
guess -- the prompt forbids it, and the schema doesn't have a slot for it.
"""

from __future__ import annotations

import anthropic

from backend.config import ANTHROPIC_API_KEY, AGENT_MODEL, MAX_TOKENS_DRAFT
from backend.schemas import LedgerEntry, FSDSection, FSD_TEMPLATE_SECTIONS
from backend.agents.json_utils import extract_json, format_ledger_block

SYSTEM_PROMPT = """You are the Draft Generation step of an SAP functional-spec \
drafting pipeline. You are given an Extraction Ledger -- a list of facts, each \
already tied to a source -- and you write the nine sections of a Functional \
Specification Document using ONLY those facts.

Rules, strictly:
1. Never invent content. If a section has no ledger entries that speak to it, \
set its status to "needs_input", leave content empty, and write a one- or \
two-sentence needs_input_detail describing specifically what's missing (not \
a generic "no input provided").
2. If two or more ledger entries relevant to the same section state different, \
incompatible things (e.g. two different proposed technical approaches, or two \
different scope boundaries), set status to "conflict". Do not pick one. Write \
content as a short neutral summary that both positions exist, and put the full \
detail -- both positions, each with the entry_id and source_id it came from -- \
in conflict_detail.
3. If a section IS grounded, write clear, professional FSD prose for it, and \
list every entry_id from the ledger that content draws on in grounded_in. \
Grounded prose must not go beyond what the cited entries actually support.
4. Section order and keys are fixed -- output exactly these nine keys in this \
order: business_background, context, business_problem, business_impact, \
business_requirement, solution_approach, scope, functional_design, \
technical_approach.

Output ONLY a JSON array of exactly nine objects, no prose before or after, no \
markdown fence. Each element:
{"key": str, "status": "grounded"|"needs_input"|"conflict", "content": str, \
"grounded_in": [str], "needs_input_detail": str|null, "conflict_detail": str|null}
"""


def generate_fsd_draft(ledger: list[LedgerEntry]) -> list[FSDSection]:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    response = client.messages.create(
        model=AGENT_MODEL,
        max_tokens=MAX_TOKENS_DRAFT,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": format_ledger_block(ledger)}],
    )

    raw_text = "".join(block.text for block in response.content if block.type == "text")
    items = extract_json(raw_text)

    valid_entry_ids = {e.entry_id for e in ledger}
    title_by_key = {s["key"]: s["title"] for s in FSD_TEMPLATE_SECTIONS}

    sections: list[FSDSection] = []
    for item in items:
        key = item["key"]
        grounded_in = [eid for eid in item.get("grounded_in", []) if eid in valid_entry_ids]
        sections.append(
            FSDSection(
                key=key,
                title=title_by_key.get(key, key),
                status=item["status"],
                content=item.get("content", ""),
                grounded_in=grounded_in,
                needs_input_detail=item.get("needs_input_detail"),
                conflict_detail=item.get("conflict_detail"),
            )
        )
    return sections
