"""
Fixed knowledge base for the Intake Validation assessment -- analogous to a
Capgemini internal tool's "Func Spec Intake Checklist" (a 94-item bank
scored against a live SAP system via an MCP connection), but independently
authored and deliberately smaller for three reasons:

1. We have no live SAP system to verify named objects against -- the
   Intake Validation agent (backend/agents/intake_validation.py) is honest
   about that and marks those few checks "cannot_verify" rather than
   faking a Pass/Fail, instead of trying to reproduce a capability we
   don't have.
2. A single LLM call that grades 90+ items against all six SAP-object
   categories at once produces a large JSON response -- exactly the kind
   of oversized-output bug this session already hit twice today
   (backend/config.py's MAX_TOKENS_LEDGER/MAX_TOKENS_DRAFT history). Only
   the object's own type category is graded, not all six, keeping any one
   run to GENERAL (~12 items) + one type category (~6-8 items).
3. A smaller, curated bank that's actually accurate beats a padded one
   that chases parity for its own sake.

GENERAL applies to every object type. TYPE_CHECKLIST_ITEMS is keyed by
TrackedObject.type (Report | Interface | Conversion | Enhancement | Form |
Workflow) and only that one category runs per object -- no N/A noise for
categories that plainly don't apply.
"""

from __future__ import annotations

IntakeSeverity = str  # "critical" | "high" | "medium" | "low"

GENERAL_CHECKLIST_ITEMS: list[dict] = [
    {"id": "GEN-01", "severity": "critical", "check": "Is the business requirement clearly and unambiguously stated, with the problem and desired outcome both described?"},
    {"id": "GEN-02", "severity": "critical", "check": "Are document control details complete -- object ID, title, type, module, version, author, and named (not placeholder) reviewers/sign-off roles?"},
    {"id": "GEN-03", "severity": "high", "check": "Are scope boundaries and assumptions explicitly listed, including what is out of scope?"},
    {"id": "GEN-04", "severity": "high", "check": "Are dependencies on other objects, configuration, or prerequisite work clearly identified?"},
    {"id": "GEN-05", "severity": "high", "check": "Are error handling and exception scenarios described for the main failure modes?"},
    {"id": "GEN-06", "severity": "medium", "check": "Are test scenarios or acceptance criteria provided that cover positive, negative, and boundary cases?"},
    {"id": "GEN-07", "severity": "critical", "check": "Are security and authorization requirements explicitly addressed (roles, authorization objects, or an explicit statement that none are needed)?"},
    {"id": "GEN-08", "severity": "medium", "check": "Are performance expectations or data volumes stated wherever they would materially affect the design (batch windows, record counts, response times)?"},
    {"id": "GEN-09", "severity": "high", "check": "Is the organizational scope defined -- which company codes, plants, or org units this applies to?"},
    {"id": "GEN-10", "severity": "medium", "check": "Where the document proposes custom development, is the fit-gap rationale given (why standard SAP functionality/configuration doesn't cover this)?"},
    {"id": "GEN-11", "severity": "high", "check": "Is the document free of TBD/placeholder gaps -- unresolved decisions, 'to be named' roles, or unconfirmed assumptions standing in for facts?"},
    {"id": "GEN-12", "severity": "medium", "check": "Is data privacy/compliance addressed -- does the document state whether personal or sensitive data is involved?"},
]

TYPE_CHECKLIST_ITEMS: dict[str, list[dict]] = {
    "Report": [
        {"id": "RPT-01", "severity": "high", "check": "Are output options defined (ALV grid, download to Excel, email, spool) and interactive features (drill-down, buttons) specified?"},
        {"id": "RPT-02", "severity": "high", "check": "Is the selection screen defined -- all parameters, their mandatory/optional status, defaults, and value help?"},
        {"id": "RPT-03", "severity": "medium", "check": "If the report updates data, are posting logic, locking, commit strategy, and a test-run/simulation mode defined?"},
        {"id": "RPT-04", "severity": "medium", "check": "Is the execution mode defined (online/background/scheduled), with frequency and job variant details for a background job?"},
        {"id": "RPT-05", "severity": "high", "check": "Is an authorization check defined for who can run the report and see its output?"},
    ],
    "Interface": [
        {"id": "INT-01", "severity": "critical", "check": "Is the direction and protocol defined -- inbound/outbound, and the mechanism (IDoc, API/OData, RFC, file)?"},
        {"id": "INT-02", "severity": "critical", "check": "Is a source-to-target field mapping provided, including transformation rules?"},
        {"id": "INT-03", "severity": "high", "check": "Are error handling and reprocessing defined for a failed or partial interface run?"},
        {"id": "INT-04", "severity": "medium", "check": "Is monitoring defined -- how failures are surfaced and to whom (e.g. failed IDocs, application log)?"},
        {"id": "INT-05", "severity": "high", "check": "Is the triggering event and frequency defined (real-time, scheduled batch, event-driven)?"},
        {"id": "INT-06", "severity": "high", "check": "Is authentication/security for the interface itself defined, separate from end-user authorization?"},
    ],
    "Conversion": [
        {"id": "CNV-01", "severity": "high", "check": "Is the legacy source system and extraction method identified?"},
        {"id": "CNV-02", "severity": "high", "check": "Are data cleansing and pre-load validation rules defined?"},
        {"id": "CNV-03", "severity": "critical", "check": "Are mock load cycles and a post-load reconciliation/validation report defined?"},
        {"id": "CNV-04", "severity": "medium", "check": "Is the data scope defined -- open vs. closed items, historical date range, cutover date?"},
        {"id": "CNV-05", "severity": "medium", "check": "Is the load sequence and dependency on other conversion objects defined?"},
        {"id": "CNV-06", "severity": "high", "check": "Is a rollback or fallback plan defined if the load fails mid-cutover?"},
    ],
    "Enhancement": [
        {"id": "ENH-01", "severity": "critical", "check": "Is the enhancement location identified (BAdI, user exit, enhancement spot, or custom field/logic)?"},
        {"id": "ENH-02", "severity": "high", "check": "Are the conditions under which the enhancement executes clearly restricted, so other processes aren't affected?"},
        {"id": "ENH-03", "severity": "critical", "check": "Is standard data updated only through standard BAPIs/APIs, never direct table updates -- and if a direct update is unavoidable, is it justified and is an activation/deactivation switch defined?"},
        {"id": "ENH-04", "severity": "medium", "check": "Is the impact on any existing enhancement at the same exit/BAdI assessed, including regression test scope?"},
        {"id": "ENH-05", "severity": "medium", "check": "Is the clean-core/extensibility approach stated (key-user extensibility, on-stack developer, side-by-side BTP)?"},
    ],
    "Form": [
        {"id": "FRM-01", "severity": "high", "check": "Is the output channel defined (print, email with attachment, archiving)?"},
        {"id": "FRM-02", "severity": "medium", "check": "Is a layout mock-up provided, with every field mapped to its data source?"},
        {"id": "FRM-03", "severity": "medium", "check": "Is the form technology and base template to use specified (Adobe, Smart Forms, SAPscript)?"},
        {"id": "FRM-04", "severity": "low", "check": "Are language/country-specific legal text and address format requirements addressed?"},
        {"id": "FRM-05", "severity": "low", "check": "Are special requirements (barcodes, signatures, watermarks) specified where applicable?"},
    ],
    "Workflow": [
        {"id": "WFL-01", "severity": "high", "check": "Is the triggering event and start condition for the workflow defined?"},
        {"id": "WFL-02", "severity": "critical", "check": "Are approval steps/levels and agent determination rules defined (org structure, role, responsibility rules, fallback agent)?"},
        {"id": "WFL-03", "severity": "high", "check": "Are deadlines, escalation, delegation, and notification requirements defined?"},
        {"id": "WFL-04", "severity": "high", "check": "Are outcomes for each decision defined (approve/reject/rework and the follow-on system actions)?"},
        {"id": "WFL-05", "severity": "medium", "check": "Is the workflow technology specified (Flexible Workflow, classic Business Workflow, SAP Build Process Automation)?"},
    ],
}

# The macro, document-level checks -- distinct from the itemized checklist
# above. These mirror "quality gates" rather than individual facts: each one
# asks the agent to judge the document as a whole against one concern.
QUALITY_CHECK_DEFINITIONS: list[dict] = [
    {"key": "business_functionality", "title": "Business Functionality Clearly Described",
     "look_for": "Business background, problem statement, and business impact are all present and specific, not generic."},
    {"key": "requirements_unambiguous", "title": "Functional Requirements Are Unambiguous",
     "look_for": "Field-level/process-level logic is detailed enough to build from, without contradictions between sections."},
    {"key": "no_placeholder_gaps", "title": "Document Contains No TBD/Placeholder Gaps",
     "look_for": "No literal TBD, 'to be named' reviewers, unconfirmed assumptions standing in for facts, or unresolved open questions."},
    {"key": "test_coverage", "title": "Test Scenarios Are Valid and Consistent",
     "look_for": "Test scenarios exist, cover the stated functional rules, and don't contradict them."},
    {"key": "security_defined", "title": "Security/Authorization Is Addressed",
     "look_for": "Roles, authorization objects, or an explicit no-additional-authorization-needed statement."},
    {"key": "dependencies_documented", "title": "Dependencies and Assumptions Are Documented",
     "look_for": "Upstream/downstream dependencies and assumptions are listed, not left implicit."},
    {"key": "versioning_signoff", "title": "Versioning and Sign-off Are Tracked",
     "look_for": "A version is stated and reviewer sign-off is attributable to named people, not placeholders."},
    {"key": "sap_objects_named", "title": "SAP Objects Named Are Specific",
     "look_for": "Concrete SAP objects (tables, BAdIs, transactions, Fiori apps) are named rather than described vaguely -- note this checks naming specificity in the document only, not existence on a live system."},
]

VERDICT_THRESHOLDS = {"ready": 85, "needs_correction": 60}  # below 60 -> not_ready


def checklist_for_object_type(object_type: str) -> list[dict]:
    """GENERAL plus the one type category that applies -- never all six."""
    return GENERAL_CHECKLIST_ITEMS + TYPE_CHECKLIST_ITEMS.get(object_type, [])
