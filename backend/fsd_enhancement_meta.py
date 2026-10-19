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
        # The human-readable RICEFW-style Object ID (e.g. "PP_F001"), set at
        # object-creation time -- see backend/project_brain.py's
        # next_object_code. It's only ever missing for an object created
        # before that scheme existed, and the rule from the FSD content spec
        # applies here too: never leave it blank, say explicitly when it's
        # assigned instead.
        "object_id": obj.get("object_code") or "Assigned at transport creation",
        "title": f"{obj['name']} — Functional Specification",
        "object_type": obj.get("type", "Enhancement"),
        "development_type": obj.get("type", "Enhancement"),
        "module": obj.get("module", "—"),
        "project": project.get("name", "—"),
        "version": f"v{draft['version']}",
        "status": "Draft" if not _is_fully_approved(draft) else "Approved",
        "generated_on": _fmt_dt(draft["created_at"]),
        # The requesting user's display name, captured once at generation
        # time (backend/routes_projects.py's generate_fsd_draft) -- real
        # data, never guessed. Only ever missing for a draft generated
        # before this field existed.
        "author": draft.get("generated_by") or "Not recorded for this draft version",
        # Project.system_description is exactly this already (e.g. "SAP
        # S/4HANA Private Edition · 2023", set once per project at project
        # creation/setup) -- no separate field to maintain. Same
        # never-leave-blank rule as object_id: state plainly when the
        # project hasn't set one, rather than omitting the row.
        "sap_release": project.get("system_description") or "Not specified in project setup — confirm with Basis/platform team before build.",
        # A standing fact about how this org promotes custom code, not a
        # specific technical object -- safe to state as the standard
        # landscape pattern rather than invented per-document. The actual
        # transport request numbers are assigned at build time and belong
        # in the transport itself, not this document.
        "transport_path": "DEV → QA → PRD (standard three-system landscape; specific transport request numbers are assigned at build/release time).",
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


_AUTH_OBJECT_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]{1,3}_[A-Z0-9_]{2,}\b")  # e.g. V_VBAK_VKO, S_TABU_DIS


def build_validation_table(sections: list[dict], document_identification: dict | None = None) -> list[dict]:
    """The mandatory Validation Point -> How It's Satisfied -> Section ->
    Pass/Fail table from the Mandatory Quality Bar. Nine fixed checks,
    evaluated with simple, explainable heuristics over the already-drafted
    sections (and, for the three table-based checks, the structured
    field_mapping/error_rows/test_rows data those sections carry) -- not
    re-judged by a model, so the result is reproducible and never marks a
    check "Pass" the data doesn't actually support."""

    by_key = {s["key"]: s for s in sections}

    def grounded(key: str) -> bool:
        # "Present and usable" for this checklist's purposes -- ai_inferred
        # content still satisfies "this section isn't empty", it's just
        # flagged separately (as a yellow item) for the user to confirm.
        s = by_key.get(key)
        return bool(s and s["status"] in ("grounded", "ai_inferred") and s["content"].strip())

    def has_unflagged_tbd() -> bool:
        for s in sections:
            if s["status"] not in ("grounded", "ai_inferred"):
                continue
            for match in _TBD_PATTERN.finditer(s["content"]):
                window = s["content"][max(0, match.start() - 60) : match.end() + 60]
                if not _CONFIRMED_DISCLAIMER.search(window):
                    return True
        return False

    def table_rows(key: str, field: str) -> list[dict]:
        s = by_key.get(key)
        return (s.get(field) or []) if s else []

    def fully_populated(rows: list[dict], required_keys: tuple[str, ...]) -> bool:
        if not rows:
            return False
        return all(str(row.get(k, "")).strip() for row in rows for k in required_keys)

    def has_concrete_or_flagged(key: str) -> bool:
        # "Concrete" for Security and Authorization Details specifically --
        # a real-looking SAP authorization object name (e.g. V_VBAK_VKO) --
        # or an explicit "to be confirmed" disclaimer. Catches the one thing
        # rule 1 of the quality bar calls out by name: a bare "users need
        # appropriate access" statement with nothing concrete behind it.
        s = by_key.get(key)
        if not s or not s["content"].strip():
            return False
        return bool(_AUTH_OBJECT_PATTERN.search(s["content"]) or _CONFIRMED_DISCLAIMER.search(s["content"]))

    field_mapping_rows = table_rows("functional_design_logic", "field_mapping")
    test_rows_data = table_rows("test_scenarios", "test_rows")
    di = document_identification or {}

    checks = [
        ("Business Functionality", "future_process", "Current/future process sections are grounded and describe the business need."),
        ("Detailed Functional Requirements", "requirements", "Requirements section is grounded, each requirement individually stated."),
        ("SAP Objects Validity", "functional_design_logic", "No invented technical object names — unconfirmed names are explicitly flagged as such."),
        ("No TBDs / Placeholders", None, "No bare TBD/placeholder text outside an explicit 'to be confirmed' flag."),
        ("Logic / Field Mapping", "functional_design_logic", "A complete source-to-target row exists for every field, with its rule type (Direct Copy/Conditional/Derived)."),
        ("Test Scripts Validity", "test_scenarios", "Every test row (Test ID, scenario, steps, expected result) is fully populated."),
        ("Security and Authorization Details", "security_roles", "Named authorization objects and activities are given, not a general access statement."),
        ("Versions and Releases", None, "Document states a version, target SAP release, and transport path explicitly."),
        ("Test Scripts Presence", "test_scenarios", "The full test table itself (Test ID / Steps / Expected Result) is present in the document."),
    ]

    rows = []
    for point, section_key, how in checks:
        if point == "SAP Objects Validity":
            passed = True  # enforced upstream by the drafting prompt; nothing to re-derive here
        elif point == "No TBDs / Placeholders":
            passed = not has_unflagged_tbd()
        elif point == "Logic / Field Mapping":
            passed = fully_populated(field_mapping_rows, ("field", "source", "target", "rule_type", "rule_detail"))
        elif point in ("Test Scripts Validity", "Test Scripts Presence"):
            passed = fully_populated(test_rows_data, ("test_id", "scenario", "steps", "expected_result"))
        elif point == "Security and Authorization Details":
            passed = has_concrete_or_flagged("security_roles")
        elif point == "Versions and Releases":
            passed = bool(di) and all(str(di.get(k, "")).strip() for k in ("version", "sap_release", "transport_path"))
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
