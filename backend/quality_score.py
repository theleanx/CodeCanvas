"""
v0 FSD Intake Quality Score.

The PRD flags the exact scoring rubric as an open decision -- this is a
first, documented pass at it, not the final answer. It exists so the score
on the FSD Review screen means something checkable instead of being a number
pulled from nowhere.

Method:
  - The 9 template sections are the "must-fix" checks. A section that is
    needs_input or conflict is a RED item -- the FSD cannot be trusted as-is.
  - Two cross-cutting SHOULD-fix checks run over the grounded content as a
    whole (not tied to one section): is security/authorization impact
    addressed anywhere, and are edge cases / exception scenarios addressed
    anywhere. Missing either is a YELLOW item -- these match the two sample
    yellow findings already shown on the FSD Review wireframe.
  - Everything else (grounded sections, passed cross-cutting checks) is GREEN.
  - overall_pct == green_pct, which is what puts the approval-threshold rule
    (>90 pass / 80-90 pass with condition / <80 not advisable) directly in
    terms of how much of the FSD is actually solid.
"""

from __future__ import annotations

import re

from backend.schemas import FSDSection, QualityScore

CROSS_CUTTING_CHECKS = [
    (
        "security_authorization",
        "Security / authorization impact is not defined anywhere in the draft.",
        re.compile(r"\b(security|authoriz|access control|role[- ]based)\b", re.I),
    ),
    (
        "edge_case_coverage",
        "Edge cases / exception scenarios are not addressed anywhere in the draft.",
        re.compile(r"\b(edge case|exception|error handling|fallback|boundary condition)\b", re.I),
    ),
]


def compute_quality_score(sections: list[FSDSection]) -> QualityScore:
    total_checks = len(sections) + len(CROSS_CUTTING_CHECKS)

    red_items: list[str] = []
    yellow_items: list[str] = []
    green_count = 0

    for section in sections:
        if section.status == "needs_input":
            red_items.append(f"{section.title}: {section.needs_input_detail or 'no supporting input provided'}")
        elif section.status == "conflict":
            red_items.append(f"{section.title}: {section.conflict_detail or 'conflicting inputs, unresolved'}")
        elif section.status == "ai_inferred":
            # Usable content, but not grounded in the project's own
            # documents -- a should-verify, not a must-fix-before-use.
            yellow_items.append(
                f"{section.title}: AI-inferred from general SAP knowledge, not the project's own documents — "
                f"{section.ai_inferred_note or 'confirm or correct before relying on it'}"
            )
        else:
            green_count += 1

    all_grounded_text = " ".join(s.content for s in sections if s.status in ("grounded", "ai_inferred"))
    for _key, message, pattern in CROSS_CUTTING_CHECKS:
        if pattern.search(all_grounded_text):
            green_count += 1
        else:
            yellow_items.append(message)

    red_count = len(red_items)
    yellow_count = len(yellow_items)

    green_pct = round(100 * green_count / total_checks, 1)
    yellow_pct = round(100 * yellow_count / total_checks, 1)
    red_pct = round(100 * red_count / total_checks, 1)

    overall_pct = green_pct

    if overall_pct > 90:
        tier = "pass"
    elif overall_pct >= 80:
        tier = "pass_with_condition"
    else:
        tier = "not_advisable"

    return QualityScore(
        green_pct=green_pct,
        yellow_pct=yellow_pct,
        red_pct=red_pct,
        overall_pct=overall_pct,
        tier=tier,
        requires_dual_approval=overall_pct < 80,
        red_items=red_items,
        yellow_items=yellow_items,
    )
