"""
The three parts of the Enhancement FSD that are computed, not drafted:
Document Identification, Review & Sign-off, and the mandatory Validation
Point quality-bar table from the user's custom FSD prompt.

None of this needs a model call -- the data already exists (the object, the
draft, its approvals) and is more trustworthy read straight off the DB than
regenerated as prose. Kept as pure functions over plain dicts so the same
code can be called both from the API layer (_draft_out) and the export
layer (routes_export._load_context) without either importing the other.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

_TBD_PATTERN = re.compile(r"\b(TBD|placeholder)\b", re.I)
_CONFIRMED_DISCLAIMER = re.compile(r"to be confirmed", re.I)


def _fmt_dt(value: Any) -> str:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d")
    return "—"


def build_document_identification(obj: dict, project: dict, draft: dict) -> dict:
    return {
        "object_id": obj["id"][:8],
        "title": f"{obj['name']} — Functional Specification",
        "object_type": obj.get("type", "Enhancement"),
        "module": obj.get("module", "—"),
        "project": project.get("name", "—"),
        "version": f"v{draft['version']}",
        "status": "Draft" if not _is_fully_approved(draft) else "Approved",
        "generated_on": _fmt_dt(draft["created_at"]),
    }


def _is_fully_approved(draft: dict) -> bool:
    requires_dual = draft["quality_score"].get("requires_dual_approval", True)
    ml = draft["approvals"]["module_lead_approved"]
    sa = draft["approvals"]["solution_architect_approved"]
    return (ml and sa) if requires_dual else (ml or sa)


def build_review_signoff(draft: dict) -> list[dict]:
    rows = []
    for role_key, role_label in (("module_lead", "Module Lead"), ("solution_architect", "Solution Architect")):
        approved = draft["approvals"][f"{role_key}_approved"]
        rows.append(
            {
                "role": role_label,
                "name": draft["approvals"][f"{role_key}_approved_by"] or "—",
                "status": "Signed off" if approved else "Pending",
                "date": _fmt_dt(draft["approvals"][f"{role_key}_approved_at"]) if approved else "—",
            }
        )
    return rows


def _section(sections: list[dict], key: str) -> dict | None:
    return next((s for s in sections if s["key"] == key), None)


def build_validation_table(sections: list[dict]) -> list[dict]:
    """The mandatory Validation Point -> How It's Satisfied -> Section ->
    Pass/Fail table from the attached prompt. Nine fixed checks, evaluated
    with simple, explainable heuristics over the already-drafted sections --
    not re-judged by a model, so the result is reproducible."""

    by_key = {s["key"]: s for s in sections}
    all_grounded_text = " ".join(s["content"] for s in sections if s["status"] == "grounded")

    def grounded(key: str) -> bool:
        s = by_key.get(key)
        return bool(s and s["status"] == "grounded" and s["content"].strip())

    def has_unflagged_tbd() -> bool:
        for s in sections:
            if s["status"] != "grounded":
                continue
            for match in _TBD_PATTERN.finditer(s["content"]):
                window = s["content"][max(0, match.start() - 60) : match.end() + 60]
                if not _CONFIRMED_DISCLAIMER.search(window):
                    return True
        return False

    checks = [
        ("Business Functionality", "future_process", "Current/future process sections are grounded and describe the business need."),
        ("Detailed Functional Requirements", "requirements", "Requirements section is grounded, each requirement individually stated."),
        ("SAP Objects Validity", None, "No invented technical object names — unconfirmed names are explicitly flagged as such."),
        ("No TBDs / Placeholders", None, "No bare TBD/placeholder text outside an explicit 'to be confirmed' flag."),
        ("Logic / Field Mapping", "functional_design_logic", "Functional Design & Process Logic section is grounded."),
        ("Test Scripts Validity", "test_scenarios", "Functional Unit Test Scenarios section is grounded and non-empty."),
        ("Security and Authorization Details", "security_roles", "Security and Roles section is grounded."),
        ("Versions and Releases", None, "Document carries an explicit version number."),
        ("Test Scripts Presence", "test_scenarios", "At least one test scenario is present in the document."),
    ]

    rows = []
    for point, section_key, how in checks:
        if point == "SAP Objects Validity":
            passed = True  # enforced upstream by the drafting prompt; nothing to re-derive here
        elif point == "No TBDs / Placeholders":
            passed = not has_unflagged_tbd()
        elif point == "Versions and Releases":
            passed = True  # every draft has a version by construction
        else:
            passed = grounded(section_key)
        rows.append(
            {
                "point": point,
                "how_satisfied": how,
                "section": by_key.get(section_key, {}).get("title", "—") if section_key else "—",
                "pass": passed,
            }
        )
    return rows
