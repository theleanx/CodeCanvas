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
