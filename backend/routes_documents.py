"""Document text-extraction endpoints: multipart upload -> plain text, and
(below) a repository/document link -> plain text, for the "Link to repo"
Reference Documents option."""

from __future__ import annotations

import re
import urllib.parse

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.auth import get_current_user
from backend.config import GITHUB_EXPORT_TOKEN
from backend.documents import UnsupportedDocumentType, extract_text

router = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])


class DocumentExtractResponse(BaseModel):
    filename: str
    text: str
    char_count: int


@router.post("/documents/extract", response_model=DocumentExtractResponse)
async def extract_document(file: UploadFile):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail=f'"{file.filename}" is empty.')

    try:
        text = extract_text(file.filename or "unnamed", content)
    except UnsupportedDocumentType as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return DocumentExtractResponse(filename=file.filename or "unnamed", text=text, char_count=len(text))


# --- fetch-by-link -------------------------------------------------------
# Lets Reference Documents point at a URL instead of pasting/uploading --
# either a specific file in a GitHub repo (blob or raw link) or any other
# plain URL. Only single-file fetches: listing/crawling a whole repo is out
# of scope here, so a bare repo root link is rejected with a clear message
# rather than silently pulling nothing useful.

_GITHUB_BLOB_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/blob/(?P<ref>[^/]+)/(?P<path>.+)$"
)


class LinkFetchRequest(BaseModel):
    url: str = Field(..., min_length=1)


class LinkFetchResponse(BaseModel):
    label: str
    text: str
    char_count: int


def _github_blob_to_raw(url: str) -> tuple[str, dict[str, str]]:
    """A github.com/owner/repo/blob/<ref>/<path> link isn't fetchable
    directly (it's an HTML page) -- rewrite it to the raw content URL, and
    attach the configured export token as a bearer header so private repos
    work too when GITHUB_EXPORT_TOKEN is set (harmless no-op on public ones)."""
    match = _GITHUB_BLOB_RE.match(url)
    if not match:
        return url, {}
    raw_url = (
        f"https://raw.githubusercontent.com/{match['owner']}/{match['repo']}/"
        f"{match['ref']}/{match['path']}"
    )
    headers = {"Authorization": f"token {GITHUB_EXPORT_TOKEN}"} if GITHUB_EXPORT_TOKEN else {}
    return raw_url, headers


@router.post("/documents/fetch-link", response_model=LinkFetchResponse)
async def fetch_document_link(payload: LinkFetchRequest):
    url = payload.url.strip()
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=422, detail="That doesn't look like a valid http(s) URL.")

    if re.match(r"^https?://github\.com/[^/]+/[^/]+/?$", url):
        raise HTTPException(
            status_code=422,
            detail="That's a repo root, not a file -- link directly to one file in it "
            "(open the file on GitHub and copy that URL) rather than the repo homepage.",
        )

    fetch_url, headers = _github_blob_to_raw(url)
    filename = urllib.parse.unquote(fetch_url.rsplit("/", 1)[-1] or "document")

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(fetch_url, headers=headers)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach that URL: {exc}") from exc

    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Nothing found at that URL (404). Check the link and try again.")
    if resp.status_code in (401, 403):
        raise HTTPException(
            status_code=resp.status_code,
            detail="Access denied fetching that URL -- if it's a private repo, set GITHUB_EXPORT_TOKEN "
            "on the server with read access to it.",
        )
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Fetching that URL failed ({resp.status_code}).")

    content = resp.content
    if not content:
        raise HTTPException(status_code=400, detail="That URL returned an empty response.")

    try:
        text = extract_text(filename, content)
    except UnsupportedDocumentType:
        # No recognizable extension (e.g. a URL with no file suffix) -- fall
        # back to treating it as plain text rather than refusing outright.
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=422,
                detail="Couldn't read that as text -- supported file types are .txt, .md, .docx, .pdf.",
            ) from None

    return LinkFetchResponse(label=filename, text=text, char_count=len(text))
