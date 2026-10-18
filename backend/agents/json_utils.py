"""Small shared helpers for the agent prompting steps."""

from __future__ import annotations

import json
import re

from backend.schemas import LedgerEntry


def extract_json(raw: str):
    """Claude is asked to return raw JSON, but models sometimes wrap it in a
    ```json fence anyway. Strip that defensively instead of trusting the
    prompt alone -- this is the kind of boring robustness that matters once
    this runs unattended."""
    text = raw.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)


def format_ledger_block(ledger: list[LedgerEntry]) -> str:
    """Shared by every drafting step -- the same ledger, formatted the same
    way, regardless of which template it's being drafted against."""
    lines = []
    for entry in ledger:
        lines.append(
            f"- entry_id={entry.entry_id} source_id={entry.source_id} "
            f"topic_hint={entry.topic_hint}\n"
            f"  fact: {entry.fact}\n"
            f"  quote: {entry.source_quote!r}"
        )
    return "\n".join(lines) if lines else "(ledger is empty -- every section needs_input)"
