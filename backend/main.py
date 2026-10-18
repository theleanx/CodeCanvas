"""
CodeCanvas backend API.

Two layers on top of the proven agent pipeline (backend/agents/pipeline.py):

  - backend/routes_projects.py  -- real persistence: projects, objects,
    versioned FSD drafts, approvals. This is what the frontend uses.
  - backend/routes_documents.py -- server-side .docx/.pdf/.txt/.md text
    extraction for uploaded reference documents.

/api/fsd/generate below is the original stateless endpoint from before
persistence existed. It's kept as-is (no DB, no object to attach to) since
it's still useful for a quick one-off run or a smoke test.

Run locally with:
    uvicorn backend.main:app --reload --port 8000

Then open http://localhost:8000/docs for interactive API docs.
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.auth import get_current_user
from backend.config import ANTHROPIC_API_KEY
from backend.db import Base, SessionLocal, engine, run_lightweight_migrations
from backend.models_db import User
from backend.schemas import SourceDocument, FSDDraft, FSD_TEMPLATE_SECTIONS
from backend.agents.pipeline import run_fsd_creation
from backend.seed import seed_if_empty
from backend import routes_auth, routes_documents, routes_export, routes_projects

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("codecanvas")

app = FastAPI(
    title="CodeCanvas API",
    description="FSD Creation agent: extraction ledger -> grounded draft -> quality score, plus project/object storage.",
    version="0.2.0",
)

# Wide open for local/dev use. Tighten this to the real frontend origin(s)
# before this ever goes anywhere near production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    run_lightweight_migrations()
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()


app.include_router(routes_auth.router)
app.include_router(routes_projects.router)
app.include_router(routes_documents.router)
app.include_router(routes_export.router)


# ---------------------------------------------------------------------------
# Legacy stateless endpoint (no DB involved) -- kept for quick one-off runs,
# now also behind login like everything else.
# ---------------------------------------------------------------------------

class SourceDocumentIn(BaseModel):
    source_id: str = Field(..., description="Stable id, e.g. 'brd', 'typed_context', 'project_brain:SOW.pdf'")
    label: str = Field(..., description="Human-readable label, e.g. 'BRD_CustomerMaster_v2.docx'")
    doc_type: str = Field(..., description="e.g. 'Business Requirement Document', 'Typed Context', 'Meeting Transcript'")
    text: str = Field(..., description="Raw extracted text")


class FSDGenerateRequest(BaseModel):
    sources: list[SourceDocumentIn] = Field(..., min_length=1)


class FSDGenerateResponse(BaseModel):
    request_id: str
    duration_ms: int
    draft: FSDDraft


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "agent_key_configured": bool(ANTHROPIC_API_KEY),
        "template_sections": [s["key"] for s in FSD_TEMPLATE_SECTIONS],
    }


@app.post("/api/fsd/generate", response_model=FSDGenerateResponse)
def generate_fsd(payload: FSDGenerateRequest, user: User = Depends(get_current_user)):
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY is not configured on the server.")

    request_id = str(uuid.uuid4())
    sources = [SourceDocument(**s.model_dump()) for s in payload.sources]

    logger.info("fsd_generate(legacy) start request_id=%s sources=%s", request_id, [s.source_id for s in sources])
    started = time.monotonic()
    try:
        draft = run_fsd_creation(sources)
    except Exception as exc:
        logger.exception("fsd_generate(legacy) failed request_id=%s", request_id)
        raise HTTPException(status_code=502, detail=f"Agent pipeline failed: {exc}") from exc
    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info("fsd_generate(legacy) done request_id=%s duration_ms=%s", request_id, duration_ms)

    return FSDGenerateResponse(request_id=request_id, duration_ms=duration_ms, draft=draft)


# ---------------------------------------------------------------------------
# Serve the built frontend (frontend/dist) from this same service, so a
# single deploy (one Docker image, one host) covers both API and UI --
# no separate static site, no cross-origin base-URL config needed. Only
# kicks in when the built assets actually exist (the Dockerfile builds
# them); local `uvicorn --reload` dev still runs frontend separately via
# `npm run dev` against this backend, same as before.
# ---------------------------------------------------------------------------

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        # Any path not already matched by an API route or /assets above
        # falls through to here -- always hand back index.html so React
        # Router's client-side routes (e.g. /projects/abc) work on a hard
        # reload or direct link, not just client-side navigation.
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
