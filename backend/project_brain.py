"""
Project Brain's non-document-template plumbing: per-project object-type /
module / complexity vocabularies, the Object ID scheme built from them, and
the object-level "overall status" roll-up.

Kept separate from routes_project_brain.py (the CRUD endpoints) so this
logic -- seeding defaults, generating the next id, computing overall status
-- can be called from routes_projects.py too (object creation, object
listing) without the two route modules importing each other.
"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from backend.models_db import (
    OBJECT_TYPE_INTERNAL_KEYS,
    ProjectComplexityConfig,
    ProjectModuleConfig,
    ProjectObjectIdCounter,
    ProjectObjectTypeConfig,
    TrackedObject,
)

# Defaults mirror exactly what the app shipped with before Project Brain
# existed, so an existing project's dropdowns look identical until someone
# actually edits them. (label, id_prefix) per internal key, and the default
# module/complexity lists.
_DEFAULT_TYPE_PREFIXES: dict[str, str] = {
    "Report": "R",
    "Interface": "I",
    "Conversion": "C",
    "Enhancement": "E",
    "Form": "F",
    "Workflow": "W",
}
_DEFAULT_MODULES = ["SD", "MM", "PP", "QM", "WM/EWM", "FI/CO", "BTP"]
_DEFAULT_COMPLEXITIES = ["Low", "Medium", "High"]


def _sanitize_id_code(value: str) -> str:
    code = re.sub(r"[^A-Za-z0-9]", "", value).upper()
    return code or "X"


def ensure_default_configs(db: Session, project_id: str) -> None:
    """Seeds all three config tables for a project the first time anything
    touches them -- called defensively wherever Project Brain config is
    read or an object is created, so both a brand-new project and one that
    existed before this feature shipped end up with a full, editable set
    instead of an empty one. A no-op (one cheap existence check each) once
    a project already has rows."""
    if db.query(ProjectObjectTypeConfig).filter(ProjectObjectTypeConfig.project_id == project_id).first() is None:
        for i, key in enumerate(OBJECT_TYPE_INTERNAL_KEYS):
            db.add(
                ProjectObjectTypeConfig(
                    project_id=project_id,
                    internal_key=key,
                    display_label=key,
                    id_prefix=_DEFAULT_TYPE_PREFIXES[key],
                    enabled=True,
                    sort_order=i,
                )
            )

    if db.query(ProjectModuleConfig).filter(ProjectModuleConfig.project_id == project_id).first() is None:
        for i, name in enumerate(_DEFAULT_MODULES):
            db.add(
                ProjectModuleConfig(
                    project_id=project_id,
                    name=name,
                    id_code=_sanitize_id_code(name),
                    enabled=True,
                    sort_order=i,
                )
            )

    if db.query(ProjectComplexityConfig).filter(ProjectComplexityConfig.project_id == project_id).first() is None:
        for i, name in enumerate(_DEFAULT_COMPLEXITIES):
            db.add(ProjectComplexityConfig(project_id=project_id, name=name, enabled=True, sort_order=i))

    db.commit()


def next_object_code(db: Session, project_id: str, module_name: str, type_internal_key: str) -> str:
    """"{module id_code}_{type id_prefix}{seq:03d}", e.g. "PP_F001". The
    counter is keyed by project+module+type and only ever increments --
    deleting an object never frees its number, so two objects can never
    collide on the same display id."""
    ensure_default_configs(db, project_id)

    module_cfg = (
        db.query(ProjectModuleConfig)
        .filter(ProjectModuleConfig.project_id == project_id, ProjectModuleConfig.name == module_name)
        .first()
    )
    module_code = module_cfg.id_code if module_cfg else _sanitize_id_code(module_name)

    type_cfg = (
        db.query(ProjectObjectTypeConfig)
        .filter(
            ProjectObjectTypeConfig.project_id == project_id,
            ProjectObjectTypeConfig.internal_key == type_internal_key,
        )
        .first()
    )
    type_prefix = type_cfg.id_prefix if type_cfg else _DEFAULT_TYPE_PREFIXES.get(type_internal_key, type_internal_key[:1].upper())

    # No row-level locking here -- this is a single-instance demo tool with
    # one request creating one object at a time in practice, not a
    # high-concurrency system worth the dialect-conditional complexity of
    # SELECT ... FOR UPDATE (which SQLite doesn't support anyway). Two
    # truly simultaneous creates for the same module+type could in theory
    # read the same next_seq before either commits; worst case is a gap or
    # a rare duplicate suffix, not data loss or a crash.
    key = f"{module_code}_{type_prefix}"
    counter = (
        db.query(ProjectObjectIdCounter)
        .filter(ProjectObjectIdCounter.project_id == project_id, ProjectObjectIdCounter.key == key)
        .first()
    )
    if counter is None:
        counter = ProjectObjectIdCounter(project_id=project_id, key=key, next_seq=1)
        db.add(counter)
        db.flush()

    seq = counter.next_seq
    counter.next_seq = seq + 1
    db.flush()

    return f"{key}{seq:03d}"


# --- Overall status roll-up -------------------------------------------------
# A single at-a-glance status, computed (never separately stored) so it can
# never drift out of sync with the per-stage statuses it's built from -- the
# same lesson the Intake Validation "pending spinner" bug taught earlier in
# this project's history.

_STAGE_ORDER: list[tuple[str, str]] = [
    ("fsd_status", "FSD"),
    ("feasibility_status", "Feasibility"),
    ("tsd_status", "TSD"),
    ("code_review_status", "Code Review"),
    ("unit_test_status", "Unit Test"),
    ("code_status", "Code"),
]


def compute_overall_status(obj: TrackedObject) -> str:
    if obj.cancelled:
        return "Cancelled"

    statuses = [getattr(obj, col) for col, _label in _STAGE_ORDER]
    if all(s == "Not Started" for s in statuses):
        return "Not Started"
    if all(s == "Complete" for s in statuses):
        return "Complete"

    for col, label in _STAGE_ORDER:
        status = getattr(obj, col)
        if status != "Complete":
            return f"{label} {status}"

    return "Complete"  # unreachable -- every stage was Complete, caught above
