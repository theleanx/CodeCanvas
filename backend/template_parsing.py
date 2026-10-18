"""
Best-effort section-heading extraction for an uploaded client FSD/TSD/etc.
template -- turns a .docx/.pdf/.txt/.md file into an ordered list of
{"key", "title"} section definitions for Project Brain's "client-specific
template" flow.

Deliberately not trying to be perfect: whatever this detects is shown to
the admin as an editable, reorderable list before anything is saved (see
routes_project_brain.py's upload endpoint), so a a missed or extra heading
here is a two-click fix, not a silent data problem. .docx gets real
heading-style detection; .pdf/.txt/.md fall back to simpler heuristics.
"""

from __future__ import annotations

import io
import re

import docx  # python-docx
from pypdf import PdfReader

from backend.documents import UnsupportedDocumentType, _decode_text, _extension

_MD_HEADING_RE = re.compile(r"^#{1,3}\s+(.+?)\s*$")
# A short, title-case-ish line with no terminal punctuation reads as a
# heading in a plain-text template (ALL CAPS, or Title Case, under ~80
# chars, no trailing period) -- a loose heuristic, intentionally generous
# since the admin reviews the result either way.
_PLAIN_HEADING_RE = re.compile(r"^(?:[A-Z][A-Za-z0-9 /&'()-]{2,78}|[A-Z0-9 /&'()-]{3,78})$")


def _slugify(title: str, used: set[str]) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", title.strip().lower()).strip("_") or "section"
    candidate = key
    i = 2
    while candidate in used:
        candidate = f"{key}_{i}"
        i += 1
    used.add(candidate)
    return candidate


def _sections_from_titles(titles: list[str]) -> list[dict]:
    used: set[str] = set()
    return [{"key": _slugify(t, used), "title": t} for t in titles if t.strip()]


def _extract_docx_headings(content: bytes) -> list[dict]:
    document = docx.Document(io.BytesIO(content))
    titles: list[str] = []
    for para in document.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style_name = (para.style.name if para.style else "") or ""
        if style_name.lower().startswith("heading") or style_name.lower() == "title":
            titles.append(text)

    if not titles:
        raise UnsupportedDocumentType(
            "Couldn't find any heading-styled paragraphs in that .docx (Heading 1/2/Title styles). "
            "Either apply heading styles to the section titles and re-upload, or add sections manually below."
        )
    return _sections_from_titles(titles)


def _extract_markdown_headings(text: str) -> list[dict]:
    titles = [m.group(1).strip() for line in text.splitlines() if (m := _MD_HEADING_RE.match(line))]
    if titles:
        return _sections_from_titles(titles)

    # No markdown syntax -- fall back to the plain-text heuristic: a short,
    # heading-shaped line standing alone (blank lines on both sides, or at
    # the very start/end of the document).
    lines = text.splitlines()
    titles = []
    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line or not _PLAIN_HEADING_RE.match(line):
            continue
        before_blank = i == 0 or not lines[i - 1].strip()
        after_blank = i == len(lines) - 1 or not lines[i + 1].strip()
        if before_blank and after_blank:
            titles.append(line)
    return _sections_from_titles(titles)


def _extract_pdf_headings(content: bytes) -> list[dict]:
    reader = PdfReader(io.BytesIO(content))
    text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
    if not text.strip():
        raise UnsupportedDocumentType(
            "Couldn't extract any text from that PDF (it's likely scanned/image-only). "
            "Try a .docx with heading styles, or add sections manually below."
        )
    return _extract_markdown_headings(text)


def extract_template_sections(filename: str, content: bytes) -> tuple[list[dict], str]:
    """Returns (sections, raw_text). Raises UnsupportedDocumentType with a
    clear, actionable message on anything it can't confidently parse --
    the caller's response still lets the admin start from an empty list
    and add sections by hand rather than being stuck."""
    ext = _extension(filename)

    if ext == ".docx":
        sections = _extract_docx_headings(content)
        raw_text = "\n".join(p.text for p in docx.Document(io.BytesIO(content)).paragraphs if p.text.strip())
    elif ext in (".txt", ".md"):
        raw_text = _decode_text(content)
        sections = _extract_markdown_headings(raw_text)
        if not sections:
            raise UnsupportedDocumentType(
                "Couldn't detect section headings in that file. Use '## Heading' markdown syntax, "
                "or add sections manually below."
            )
    elif ext == ".pdf":
        sections = _extract_pdf_headings(content)
        reader = PdfReader(io.BytesIO(content))
        raw_text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
    else:
        raise UnsupportedDocumentType(
            f'"{filename}" has an unsupported extension ({ext or "none"}). Supported: .docx, .pdf, .txt, .md.'
        )

    return sections, raw_text
