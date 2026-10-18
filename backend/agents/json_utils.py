"""Small shared helpers for the agent prompting steps."""

from __future__ import annotations

import json
import re

from backend.schemas import LedgerEntry


class ResponseTruncated(Exception):
    """Raised instead of letting a truncated response fail as a cryptic
    json.loads parse error ('Unterminated string...'). Callers should check
    response.stop_reason and raise this before calling extract_json, so the
    user sees an actionable message pointing at the token budget instead of
    a JSON syntax complaint that gives no hint why."""


def check_not_truncated(stop_reason: str, max_tokens: int) -> None:
    if stop_reason == "max_tokens":
        raise ResponseTruncated(
            f"The model's response was cut off at the {max_tokens}-token limit before finishing "
            "its JSON -- this input is larger than the configured budget can draft in one pass. "
            "Increase the relevant MAX_TOKENS_* setting, or trim the source documents."
        )


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
