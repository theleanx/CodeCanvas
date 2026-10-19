import os
import secrets

from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# JWT signing secret. If none is set, generate one for this process -- fine
# for a single dev instance (tokens just stop validating on restart), but a
# real deployment MUST set CODECANVAS_JWT_SECRET to a fixed, private value,
# or every restart invalidates every session.
JWT_SECRET = os.environ.get("CODECANVAS_JWT_SECRET") or secrets.token_hex(32)
JWT_ALGORITHM = "HS256"
JWT_EXPIRES_MINUTES = 60 * 24 * 7  # 7 days -- a demo/internal tool, not a bank

# Swappable per the PRD's "model-agnostic backend" open decision -- for v0
# this is the only place the model name is pinned.
AGENT_MODEL = os.environ.get("CODECANVAS_AGENT_MODEL", "claude-sonnet-5")

# The ledger step extracts one JSON entry (fact/source_id/source_quote/
# topic_hint) per atomic fact across ALL source documents combined -- a real
# object with several reference documents (BRD, transcripts, a linked repo's
# docs, Project Brain excerpts, plus any queued regenerate context) can
# produce well over the 30-40 entries that fit in 4096 tokens, truncating
# mid-array before the draft step even runs. Raised to match MAX_TOKENS_DRAFT.
MAX_TOKENS_LEDGER = 8192
MAX_TOKENS_DRAFT = 8192
# The Enhancement template drafts twelve richer sections (plus structured
# flow_steps/wireframe data for the diagrams) in one JSON response -- 8192
# wasn't enough headroom and silently truncated mid-string on longer inputs,
# which surfaced to the user as a cryptic "Unterminated string" JSON error
# instead of a clear one. Doubled, with an explicit truncation check below
# as a second line of defense if a draft is ever still big enough to hit it.
# Raised again after the content spec got considerably denser (every field
# named explicitly in requirements, a full 5-column error-handling table
# with 3+ mandatory scenarios, a test script with one row per field/branch/
# error-row) -- a complex object can now legitimately need 20+ test rows
# alone.
# Raised a third time for the Mandatory Quality Bar: error_handling and
# test_scenarios now carry their detail as structured error_rows/test_rows
# (JSON objects, which cost more tokens per fact than the equivalent prose
# line did) instead of duplicating it in both prose and structured form, and
# functional_design_logic gained a brand-new field_mapping table (one row
# per requirement field) with no prose-side reduction to offset it.
MAX_TOKENS_ENHANCEMENT_DRAFT = 24000

# The Intake Validation assessment (backend/agents/intake_validation.py)
# grades a finished FSD against ~18-20 checklist items plus ~8 quality
# checks, a radar score, a narrative, and a prioritized corrections list,
# all in one JSON response. Sized generously from the start, having
# already been burned twice today by budgets sized too close to the edge.
MAX_TOKENS_INTAKE_VALIDATION = 12000

# --- Export / push integrations ---------------------------------------------
# Both are optional -- the download endpoints (Markdown/Word/PDF) need none
# of this. These only gate the two "push" buttons; each is turned off until
# its own env vars are set, and the endpoint says so plainly rather than
# crashing.

# GitHub: a classic or fine-grained Personal Access Token with "contents:
# write" on the target repo. Generate one at
# https://github.com/settings/tokens, then set both of these on the host
# (Render: service -> Environment).
GITHUB_EXPORT_TOKEN = os.environ.get("GITHUB_EXPORT_TOKEN")
GITHUB_EXPORT_REPO = os.environ.get("GITHUB_EXPORT_REPO")  # "owner/repo"
GITHUB_EXPORT_BASE_PATH = os.environ.get("GITHUB_EXPORT_BASE_PATH", "fsd-exports")

# Google Drive: a service account JSON key (its whole contents, as one env
# var) with access to a target shared folder. Create the service account in
# Google Cloud Console, enable the Drive API, then share the destination
# Drive folder with the service account's email (found in the JSON key as
# "client_email") as an Editor -- a service account has no storage of its
# own, so without a shared folder every upload fails on quota.
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
GOOGLE_DRIVE_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
