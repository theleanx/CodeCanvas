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

MAX_TOKENS_LEDGER = 4096
MAX_TOKENS_DRAFT = 8192

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
