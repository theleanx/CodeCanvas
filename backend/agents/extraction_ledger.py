"""
Step 1 of the FSD Creation pipeline: turn N raw input sources into one
Extraction Ledger -- a flat list of atomic facts, each tied back to exactly
the source and quote it came from.

This step deliberately does NOT try to write FSD prose yet. Its only job is
extraction with citation, which keeps the hard "don't hallucinate" problem
small and checkable: a fact either traces back to a real quote in a real
source, or it doesn't belong in the ledger at all.
"""

from __future__ import annotations

import uuid

import anthropic

from backend.config import ANTHROPIC_API_KEY, AGENT_MODEL, MAX_TOKENS_LEDGER
from backend.schemas import SourceDocument, LedgerEntry
from backend.agents.json_utils import check_not_truncated, extract_json
from backend.token_usage import TokenUsage, usage_from_response

SYSTEM_PROMPT = """You are the Extraction Ledger step of an SAP functional-spec \
drafting pipeline. You read one or more source documents and extract atomic \
facts and requirements -- nothing else.

Rules, strictly:
1. Every fact you output must be traceable to a specific quote in a specific \
source. If you cannot point at the text it came from, do not output it.
2. Do not summarize across sources into a new claim neither source actually \
makes. If source A says X and source B says Y and they conflict, extract BOTH \
as separate facts -- do not merge, reconcile, or pick a winner. Conflict \
resolution happens in a later step, by a human.
3. Do not infer unstated details (dates, owners, numbers, technical approach) \
even if they seem like reasonable guesses. If it is not stated, it does not \
go in the ledger.
4. Extract requirements, constraints, problem statements, impacts, scope \
boundaries, and proposed approaches -- not incidental chit-chat.
5. For each fact, give your best guess at which FSD section it belongs to \
(topic_hint), from this fixed list: business_background, context, \
business_problem, business_impact, business_requirement, solution_approach, \
scope, functional_design, technical_approach. If genuinely unclear, use null.

Output ONLY a JSON array, no prose before or after, no markdown fence. Each \
element: {"fact": str, "source_id": str, "source_quote": str, "topic_hint": str|null}
"""


def build_extraction_ledger(sources: list[SourceDocument]) -> tuple[list[LedgerEntry], TokenUsage]:
    if not sources:
        return [], TokenUsage()

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    sources_block = "\n\n".join(
        f"=== SOURCE id={s.source_id} type={s.doc_type} label={s.label!r} ===\n{s.text}"
        for s in sources
    )

    response = client.messages.create(
        model=AGENT_MODEL,
        max_tokens=MAX_TOKENS_LEDGER,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": sources_block}],
    )

    check_not_truncated(response.stop_reason, MAX_TOKENS_LEDGER)
    raw_text = "".join(block.text for block in response.content if block.type == "text")
    items = extract_json(raw_text)

    valid_source_ids = {s.source_id for s in sources}
    ledger: list[LedgerEntry] = []
    for item in items:
        if item.get("source_id") not in valid_source_ids:
            # Refuse anything that doesn't cite a real source -- a model
            # inventing a source_id is exactly the failure mode this step
            # exists to prevent.
            continue
        ledger.append(
            LedgerEntry(
                entry_id=f"led_{uuid.uuid4().hex[:8]}",
                fact=item["fact"],
                source_id=item["source_id"],
                source_quote=item.get("source_quote", ""),
                topic_hint=item.get("topic_hint"),
            )
        )
    return ledger, usage_from_response(response)
