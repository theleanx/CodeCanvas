"""
Token usage + cost-estimate tracking for the LLM calls behind one FSD
generation (ledger extraction, draft/enhancement draft, and Intake
Validation).

Token counts are real: they come straight off each Anthropic API response's
`usage` field, never estimated. The dollar figure is a genuine estimate --
it exists only for the models priced in PRICING_PER_MTOK below (USD per
million tokens), sourced from Anthropic's own published pricing
(https://platform.claude.com/docs/en/about-claude/pricing, checked
2026-10-18). If the configured model isn't listed there, or Anthropic's
pricing has since changed, estimate_cost_usd returns None rather than
silently showing a number nobody kept current -- the UI then shows real
token counts with no $ figure instead of a wrong one.
"""

from __future__ import annotations

from pydantic import BaseModel


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


def usage_from_response(response) -> TokenUsage:
    usage = getattr(response, "usage", None)
    return TokenUsage(
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
    )


# USD per million tokens: (input_rate, output_rate). Last checked 2026-10-18
# against Anthropic's own pricing page -- update if that page changes, or if
# CODECANVAS_AGENT_MODEL is pointed at a model not listed here.
PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-sonnet-5": (2.00, 10.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-fable-5-1": (10.00, 50.00),
}


def estimate_cost_usd(model: str, usage: TokenUsage) -> float | None:
    rates = PRICING_PER_MTOK.get(model)
    if not rates:
        return None
    input_rate, output_rate = rates
    return (usage.input_tokens / 1_000_000) * input_rate + (usage.output_tokens / 1_000_000) * output_rate
