"""
Push an exported FSD somewhere outside CodeCanvas: a GitHub repo, or a
Google Drive folder.

Both are optional integrations, each gated by its own env vars (see
backend/config.py). Neither uses this session's own credentials -- the
*deployed* CodeCanvas instance needs its own service-level credentials,
since it's a separate, standalone server that any logged-in user can push
from, not a single person's authenticated session.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass

import httpx

from backend.config import (
    GITHUB_EXPORT_BASE_PATH,
    GITHUB_EXPORT_REPO,
    GITHUB_EXPORT_TOKEN,
    GOOGLE_DRIVE_FOLDER_ID,
    GOOGLE_SERVICE_ACCOUNT_JSON,
)


class PushNotConfigured(Exception):
    """Raised when the target integration's env vars aren't set."""


@dataclass
class PushResult:
    url: str
    detail: str


# --- GitHub ------------------------------------------------------------------

def push_markdown_to_github(path_slug: str, filename: str, content: str, commit_message: str) -> PushResult:
    if not GITHUB_EXPORT_TOKEN or not GITHUB_EXPORT_REPO:
        raise PushNotConfigured(
            "GitHub push isn't configured on this server. Set GITHUB_EXPORT_TOKEN (a Personal Access Token with "
            "'Contents: write' on the target repo) and GITHUB_EXPORT_REPO ('owner/repo') in the environment."
        )

    repo_path = f"{GITHUB_EXPORT_BASE_PATH}/{path_slug}/{filename}"
    api_base = f"https://api.github.com/repos/{GITHUB_EXPORT_REPO}/contents/{repo_path}"
    headers = {
        "Authorization": f"Bearer {GITHUB_EXPORT_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    with httpx.Client(timeout=20) as client:
        # Look up the existing file's sha (if any) -- GitHub's Contents API
        # requires it on an update, or it refuses with 409/422 instead of
        # quietly overwriting.
        existing = client.get(api_base, headers=headers)
        sha = existing.json().get("sha") if existing.status_code == 200 else None

        payload = {
            "message": commit_message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        }
        if sha:
            payload["sha"] = sha

        resp = client.put(api_base, headers=headers, json=payload)
        if resp.status_code not in (200, 201):
            detail = resp.text[:500]
            raise RuntimeError(f"GitHub push failed ({resp.status_code}): {detail}")

        data = resp.json()
        html_url = data.get("content", {}).get("html_url", f"https://github.com/{GITHUB_EXPORT_REPO}")
        return PushResult(url=html_url, detail=f"Committed to {GITHUB_EXPORT_REPO}:{repo_path}")


# --- Google Drive --------------------------------------------------------

def push_docx_to_google_drive(filename: str, docx_bytes: bytes) -> PushResult:
    if not GOOGLE_SERVICE_ACCOUNT_JSON or not GOOGLE_DRIVE_FOLDER_ID:
        raise PushNotConfigured(
            "Google Drive push isn't configured on this server. Set GOOGLE_SERVICE_ACCOUNT_JSON (the full service "
            "account key JSON, as one env var) and GOOGLE_DRIVE_FOLDER_ID (a Drive folder shared with that service "
            "account's client_email as Editor) in the environment."
        )

    # Imported lazily -- these are heavier optional deps that only matter
    # once this integration is actually configured and used.
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    import io

    try:
        info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON.") from exc

    creds = service_account.Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/drive"])
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)

    media = MediaIoBaseUpload(
        io.BytesIO(docx_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        resumable=False,
    )
    file_metadata = {
        "name": filename,
        "parents": [GOOGLE_DRIVE_FOLDER_ID],
        # Converts the uploaded .docx into a native Google Doc on arrival,
        # so it opens directly as an editable Doc rather than a binary
        # attachment Drive can only preview.
        "mimeType": "application/vnd.google-apps.document",
    }

    created = drive.files().create(body=file_metadata, media_body=media, fields="id, webViewLink").execute()
    return PushResult(
        url=created["webViewLink"],
        detail=f"Uploaded to Google Drive folder {GOOGLE_DRIVE_FOLDER_ID} as a Google Doc",
    )
