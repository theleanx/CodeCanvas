"""Document text-extraction endpoint (multipart upload -> plain text)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel

from backend.auth import get_current_user
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
