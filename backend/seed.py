"""
Seeds the database with the same placeholder projects/objects that used to
live in the frontend's lib/mockData.ts, so switching the UI from mock data
to the real API doesn't change what anyone sees on first run. Only runs
when the projects table is empty -- safe to call on every startup.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.auth import hash_password
from backend.models_db import Project, TrackedObject, User

# Dev/demo-only credentials. Every seeded account shares this password so
# the demo is usable out of the box -- a real deployment would never do
# this; it'd require each user to set their own on first login.
DEMO_PASSWORD = "codecanvas123"


def seed_users_if_empty(db: Session) -> None:
    if db.query(User).count() > 0:
        return

    users = [
        User(email="admin@codecanvas.demo", name="CodeCanvas Admin", role="admin",
             password_hash=hash_password(DEMO_PASSWORD)),
        User(email="priya.nair@codecanvas.demo", name="Priya Nair", role="module_lead",
             password_hash=hash_password(DEMO_PASSWORD)),
        # Seeded with the real operator's own email so they can log in as
        # themselves in this demo, under the Solution Architect persona
        # the wireframe and PRD already use.
        User(email="ankit.buffalo@gmail.com", name="Ankit Sharma", role="solution_architect",
             password_hash=hash_password(DEMO_PASSWORD)),
    ]
    db.add_all(users)
    db.commit()


def seed_if_empty(db: Session) -> None:
    seed_users_if_empty(db)

    if db.query(Project).count() > 0:
        return

    westlake = Project(
        name="Westlake Chemicals",
        kind="Greenfield",
        system_description="SAP S/4HANA Private Edition · 2023",
        industry="Chemical",
        geography="US, Germany",
    )
    meijer = Project(
        name="Meijer AP Modernization",
        kind="Brownfield",
        system_description="SAP S/4HANA · 2022",
        industry="Retail",
        geography="US",
    )
    tennant = Project(
        name="Tennant — 3PL EMEA",
        kind="Brownfield",
        system_description="SAP S/4HANA · 2021",
        industry="Industrial Manufacturing",
        geography="Global",
    )
    csl = Project(
        name="CSL OneERP",
        kind="Greenfield",
        system_description="SAP S/4HANA Private Edition · 2024",
        industry="Life Sciences",
        geography="Global",
    )
    db.add_all([westlake, meijer, tennant, csl])
    db.flush()  # assign ids

    westlake_objects = [
        TrackedObject(
            project_id=westlake.id, name="Sales Order Enhancement", type="Enhancement", module="SD",
            complexity="High", fsd_status="In Progress", feasibility_status="Complete",
        ),
        TrackedObject(
            project_id=westlake.id, name="Customer Master IDoc", type="Interface", module="SD",
            complexity="Medium", fsd_status="Complete", feasibility_status="Complete", tsd_status="In Progress",
        ),
        TrackedObject(
            project_id=westlake.id, name="Credit Release Exception Report", type="Report", module="FI/CO",
            complexity="Low", fsd_status="Complete", feasibility_status="Complete", tsd_status="Complete",
            code_review_status="In Progress", code_status="In Progress",
        ),
        TrackedObject(
            project_id=westlake.id, name="Legacy Pricing Conversion", type="Conversion", module="SD",
            complexity="High", fsd_status="On Hold", feasibility_status="On Hold",
        ),
        TrackedObject(
            project_id=westlake.id, name="Export Compliance Form", type="Form", module="SD",
            complexity="Medium", fsd_status="Blocked",
        ),
        TrackedObject(
            project_id=westlake.id, name="Batch Release Workflow", type="Workflow", module="QM",
            complexity="Medium", fsd_status="Complete", feasibility_status="Complete", tsd_status="Complete",
            code_review_status="Complete", unit_test_status="Complete", code_status="Complete",
        ),
        TrackedObject(
            project_id=westlake.id, name="Inbound EDI 850 Mapping", type="Interface", module="MM",
            complexity="Low", fsd_status="Complete", feasibility_status="Complete", tsd_status="Complete",
            code_review_status="Complete", unit_test_status="In Progress", code_status="Complete",
        ),
    ]
    db.add_all(westlake_objects)

    meijer_objects = [
        TrackedObject(project_id=meijer.id, name="Invoice Exception Workbench", type="Enhancement", module="FI/CO", complexity="High"),
    ]
    db.add_all(meijer_objects)

    db.commit()
