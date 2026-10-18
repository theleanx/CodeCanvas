"""
Proves the one thing that matters before anything else gets built: does the
FSD Creation agent ground correctly, flag a real gap, and flag a real
conflict -- instead of inventing content for either.

This is the exact scenario already shown on the FSD Review wireframe
(Sales Order Enhancement, Westlake Chemicals): a BRD and a typed instruction
that disagree on the technical approach, and no input anywhere about
business impact. A correct run should come back with:
  - Business Impact -> needs_input
  - Solution Approach -> conflict (BAdI vs. Fiori app)
  - everything else -> grounded

Run with:  python -m scripts.run_sample
"""

import json
import sys

sys.path.insert(0, ".")

from backend.schemas import SourceDocument
from backend.agents.pipeline import run_fsd_creation

BRD_TEXT = """
Westlake's sales order process relies on manual credit-block overrides during
month-end close. The EMEA sales operations team currently reviews every
blocked order by hand, which creates a bottleneck and delays order
confirmation by up to two business days during the last five business days
of each month, when order volume peaks.

Requirement: automate credit-block release for orders under a configurable
threshold when the customer's payment history meets defined criteria.
Exceptions should route to manual review. The system is S/4HANA Private
Edition, Sales & Distribution module, with credit management active via
FSCM.

Proposed technical approach: implement a BAdI on the credit check user exit
to evaluate the release criteria automatically.

In scope: automated release logic, an exception queue, and an audit log.
Out of scope: changes to the underlying credit scoring model.
"""

TYPED_CONTEXT = """
For the credit release automation on Westlake sales orders -- let's not use
a BAdI for this one. I want a custom Fiori approval app instead, so the
sales ops team has a proper UI to review exceptions rather than working
through SPRO or a user-exit log.
"""

SOURCES = [
    SourceDocument(
        source_id="brd",
        label="BRD_CustomerMaster_v2.docx",
        doc_type="Business Requirement Document",
        text=BRD_TEXT.strip(),
    ),
    SourceDocument(
        source_id="typed_context",
        label="Typed Context",
        doc_type="Typed Context",
        text=TYPED_CONTEXT.strip(),
    ),
]


def main():
    draft = run_fsd_creation(SOURCES)

    print("\n=== LEDGER ===")
    for entry in draft.ledger:
        print(f"[{entry.entry_id}] ({entry.source_id}, hint={entry.topic_hint}) {entry.fact}")

    print("\n=== SECTIONS ===")
    for section in draft.sections:
        print(f"\n-- {section.title} [{section.status}] --")
        if section.status == "grounded":
            print(section.content)
            print(f"   grounded_in: {section.grounded_in}")
        elif section.status == "needs_input":
            print(f"   NEEDS INPUT: {section.needs_input_detail}")
        else:
            print(f"   CONFLICT: {section.conflict_detail}")

    print("\n=== QUALITY SCORE ===")
    print(json.dumps(draft.quality_score.model_dump(), indent=2))


if __name__ == "__main__":
    main()
