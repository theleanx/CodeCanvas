"""
Turns a saved FsdDraft row into an actual document, in three formats.

All three builders walk the same underlying shape (FsdDraftOut-equivalent
dict plus the owning object/project), so a change to what's "in" an FSD
export only needs to happen in the three build_* functions below, not in
three unrelated places.
"""

from __future__ import annotations

import base64
import io
from datetime import datetime, timezone
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

STATUS_LABEL = {"grounded": "Grounded", "needs_input": "Needs Input", "conflict": "Conflict Flagged"}


def _title(obj: dict, project: dict) -> str:
    return f"{obj['name']} — Functional Specification Document"


def _fmt_dt(value: Any) -> str:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return "—"


# --- Markdown ----------------------------------------------------------------

def build_markdown(draft: dict, obj: dict, project: dict) -> str:
    q = draft["quality_score"]
    lines: list[str] = [
        f"# {_title(obj, project)}",
        "",
        f"**Project:** {project['name']}  ",
        f"**Object:** {obj['name']} ({obj['type']}, {obj['module']})  ",
        f"**Version:** {draft['version']}  ",
        f"**Generated:** {_fmt_dt(draft['created_at'])}  ",
        f"**Quality Score:** {q['overall_pct']:.0f}% ({q['tier'].replace('_', ' ')})",
        "",
    ]

    if draft.get("document_identification"):
        di = draft["document_identification"]
        lines += [
            "## Document Identification",
            "",
            f"| Object ID | Type | Module | Project | Version | Status |",
            "|---|---|---|---|---|---|",
            f"| {di['object_id']} | {di['object_type']} | {di['module']} | {di['project']} | {di['version']} | {di['status']} |",
            "",
        ]

    if draft.get("validation_table"):
        lines += ["## Validation", "", "| Validation Point | How It's Satisfied | Section | Pass/Fail |", "|---|---|---|---|"]
        for row in draft["validation_table"]:
            mark = "✅ Pass" if row["pass"] else "❌ Fail"
            lines.append(f"| {row['point']} | {row['how_satisfied']} | {row['section']} | {mark} |")
        lines.append("")

    if draft.get("review_signoff"):
        lines += ["## Review and Sign-off", "", "| Role | Name | Status | Date |", "|---|---|---|---|"]
        for row in draft["review_signoff"]:
            lines.append(f"| {row['role']} | {row['name']} | {row['status']} | {row['date']} |")
        lines.append("")

    lines += [
        "## Approvals",
        "",
        "| Role | Status | Approved By | Approved At |",
        "|---|---|---|---|",
        f"| Module Lead | {'Approved' if draft['approvals']['module_lead_approved'] else 'Pending'} "
        f"| {draft['approvals']['module_lead_approved_by'] or '—'} "
        f"| {_fmt_dt(draft['approvals']['module_lead_approved_at']) if draft['approvals']['module_lead_approved_at'] else '—'} |",
        f"| Solution Architect | {'Approved' if draft['approvals']['solution_architect_approved'] else 'Pending'} "
        f"| {draft['approvals']['solution_architect_approved_by'] or '—'} "
        f"| {_fmt_dt(draft['approvals']['solution_architect_approved_at']) if draft['approvals']['solution_architect_approved_at'] else '—'} |",
        "",
    ]

    for i, s in enumerate(draft["sections"], start=1):
        lines.append(f"## {i}. {s['title']}")
        if s["status"] == "grounded":
            lines.append("")
            lines.append(s["content"] or "_(no content)_")
        else:
            detail = s.get("conflict_detail") if s["status"] == "conflict" else s.get("needs_input_detail")
            lines.append("")
            lines.append(f"> **{STATUS_LABEL[s['status']]}** — {detail or 'No detail recorded.'}")
        for label, b64 in (s.get("images") or {}).items():
            lines.append("")
            lines.append(f"**{label}**")
            lines.append("")
            lines.append(f"![{label}](data:image/png;base64,{b64})")
        lines.append("")

    lines.append("## Extraction Ledger")
    lines.append("")
    lines.append("Every atomic fact the agent pulled from the inputs, cited back to its source.")
    lines.append("")
    lines.append("| Fact | Source | Quote |")
    lines.append("|---|---|---|")
    for e in draft["ledger"]:
        fact = e["fact"].replace("|", "\\|")
        quote = e["source_quote"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {fact} | {e['source_id']} | {quote} |")
    lines.append("")
    lines.append(f"_Exported from CodeCanvas · request_id {draft['request_id'][:8]} · {draft['duration_ms'] / 1000:.1f}s generation time_")

    return "\n".join(lines)


# --- Word (.docx) --------------------------------------------------------

STATUS_COLOR = {
    "needs_input": RGBColor(0xB4, 0x5B, 0x00),
    "conflict": RGBColor(0xB9, 0x1C, 0x1C),
}


def build_docx(draft: dict, obj: dict, project: dict) -> bytes:
    doc = Document()

    title = doc.add_heading(_title(obj, project), level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT

    q = draft["quality_score"]
    meta = doc.add_paragraph()
    meta.add_run(
        f"Project: {project['name']}   |   Object: {obj['name']} ({obj['type']}, {obj['module']})   |   "
        f"Version: {draft['version']}   |   Generated: {_fmt_dt(draft['created_at'])}   |   "
        f"Quality Score: {q['overall_pct']:.0f}% ({q['tier'].replace('_', ' ')})"
    ).italic = True

    if draft.get("document_identification"):
        di = draft["document_identification"]
        doc.add_heading("Document Identification", level=1)
        id_table = doc.add_table(rows=1, cols=6)
        id_table.style = "Light Grid Accent 1"
        for i, h in enumerate(["Object ID", "Type", "Module", "Project", "Version", "Status"]):
            id_table.rows[0].cells[i].text = h
        row = id_table.add_row().cells
        for i, v in enumerate([di["object_id"], di["object_type"], di["module"], di["project"], di["version"], di["status"]]):
            row[i].text = str(v)

    if draft.get("validation_table"):
        doc.add_heading("Validation", level=1)
        v_table = doc.add_table(rows=1, cols=4)
        v_table.style = "Light Grid Accent 1"
        for i, h in enumerate(["Validation Point", "How It's Satisfied", "Section", "Pass/Fail"]):
            v_table.rows[0].cells[i].text = h
        for vr in draft["validation_table"]:
            row = v_table.add_row().cells
            row[0].text = vr["point"]
            row[1].text = vr["how_satisfied"]
            row[2].text = vr["section"]
            row[3].text = "Pass" if vr["pass"] else "Fail"

    if draft.get("review_signoff"):
        doc.add_heading("Review and Sign-off", level=1)
        rs_table = doc.add_table(rows=1, cols=4)
        rs_table.style = "Light Grid Accent 1"
        for i, h in enumerate(["Role", "Name", "Status", "Date"]):
            rs_table.rows[0].cells[i].text = h
        for rr in draft["review_signoff"]:
            row = rs_table.add_row().cells
            row[0].text = rr["role"]
            row[1].text = rr["name"]
            row[2].text = rr["status"]
            row[3].text = rr["date"]

    doc.add_heading("Approvals", level=1)
    table = doc.add_table(rows=1, cols=4)
    table.style = "Light Grid Accent 1"
    hdr = table.rows[0].cells
    for i, h in enumerate(["Role", "Status", "Approved By", "Approved At"]):
        hdr[i].text = h
    for role_key, role_label in (("module_lead", "Module Lead"), ("solution_architect", "Solution Architect")):
        row = table.add_row().cells
        row[0].text = role_label
        row[1].text = "Approved" if draft["approvals"][f"{role_key}_approved"] else "Pending"
        row[2].text = draft["approvals"][f"{role_key}_approved_by"] or "—"
        at = draft["approvals"][f"{role_key}_approved_at"]
        row[3].text = _fmt_dt(at) if at else "—"

    for i, s in enumerate(draft["sections"], start=1):
        doc.add_heading(f"{i}. {s['title']}", level=1)
        if s["status"] == "grounded":
            doc.add_paragraph(s["content"] or "(no content)")
        else:
            detail = s.get("conflict_detail") if s["status"] == "conflict" else s.get("needs_input_detail")
            p = doc.add_paragraph()
            run = p.add_run(f"{STATUS_LABEL[s['status']]} — {detail or 'No detail recorded.'}")
            run.bold = True
            run.font.color.rgb = STATUS_COLOR.get(s["status"], RGBColor(0, 0, 0))
        for label, b64 in (s.get("images") or {}).items():
            caption = doc.add_paragraph()
            caption.add_run(label).bold = True
            doc.add_picture(io.BytesIO(base64.b64decode(b64)), width=Inches(5.5))

    doc.add_heading("Extraction Ledger", level=1)
    doc.add_paragraph("Every atomic fact the agent pulled from the inputs, cited back to its source.")
    ledger_table = doc.add_table(rows=1, cols=3)
    ledger_table.style = "Light Grid Accent 1"
    lh = ledger_table.rows[0].cells
    for i, h in enumerate(["Fact", "Source", "Quote"]):
        lh[i].text = h
    for e in draft["ledger"]:
        row = ledger_table.add_row().cells
        row[0].text = e["fact"]
        row[1].text = e["source_id"]
        row[2].text = e["source_quote"]

    footer = doc.add_paragraph()
    footer_run = footer.add_run(
        f"Exported from CodeCanvas · request_id {draft['request_id'][:8]} · {draft['duration_ms'] / 1000:.1f}s generation time"
    )
    footer_run.font.size = Pt(8)
    footer_run.italic = True

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# --- PDF -----------------------------------------------------------------
# reportlab over weasyprint/wkhtmltopdf deliberately -- pure-Python wheel,
# no system libraries (cairo/pango/chromium) to install in the Docker image.

def build_pdf(draft: dict, obj: dict, project: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=LETTER, topMargin=0.75 * inch, bottomMargin=0.75 * inch, leftMargin=0.75 * inch, rightMargin=0.75 * inch
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("FSDH1", parent=styles["Heading1"], spaceBefore=14, spaceAfter=6)
    h0 = ParagraphStyle("FSDH0", parent=styles["Title"], spaceAfter=4)
    body = ParagraphStyle("FSDBody", parent=styles["BodyText"], spaceAfter=8, leading=14)
    meta = ParagraphStyle("FSDMeta", parent=styles["BodyText"], textColor=colors.HexColor("#555555"), spaceAfter=14)
    flagged_needs_input = ParagraphStyle("FSDFlagYellow", parent=body, textColor=colors.HexColor("#8a5a00"))
    flagged_conflict = ParagraphStyle("FSDFlagRed", parent=body, textColor=colors.HexColor("#991b1b"))

    story: list[Any] = [Paragraph(_title(obj, project), h0)]

    q = draft["quality_score"]
    story.append(
        Paragraph(
            f"Project: {project['name']} | Object: {obj['name']} ({obj['type']}, {obj['module']}) | "
            f"Version: {draft['version']} | Generated: {_fmt_dt(draft['created_at'])} | "
            f"Quality Score: {q['overall_pct']:.0f}% ({q['tier'].replace('_', ' ')})",
            meta,
        )
    )

    story.append(Paragraph("Approvals", h1))
    approval_rows = [["Role", "Status", "Approved By", "Approved At"]]
    for role_key, role_label in (("module_lead", "Module Lead"), ("solution_architect", "Solution Architect")):
        at = draft["approvals"][f"{role_key}_approved_at"]
        approval_rows.append(
            [
                role_label,
                "Approved" if draft["approvals"][f"{role_key}_approved"] else "Pending",
                draft["approvals"][f"{role_key}_approved_by"] or "—",
                _fmt_dt(at) if at else "—",
            ]
        )
    approval_table = Table(approval_rows, colWidths=[1.4 * inch, 1 * inch, 1.8 * inch, 1.8 * inch])
    approval_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f3f7")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cfd4dc")),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    if draft.get("document_identification"):
        di = draft["document_identification"]
        story.append(Paragraph("Document Identification", h1))
        id_rows = [
            ["Object ID", "Type", "Module", "Project", "Version", "Status"],
            [di["object_id"], di["object_type"], di["module"], di["project"], di["version"], di["status"]],
        ]
        id_table = Table(id_rows, colWidths=[0.8 * inch, 0.9 * inch, 0.7 * inch, 1.3 * inch, 0.6 * inch, 0.8 * inch])
        id_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f3f7")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cfd4dc")),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(id_table)

    if draft.get("validation_table"):
        story.append(Paragraph("Validation", h1))
        v_rows = [["Validation Point", "How It's Satisfied", "Section", "Pass/Fail"]]
        for vr in draft["validation_table"]:
            v_rows.append(
                [Paragraph(vr["point"], body), Paragraph(vr["how_satisfied"], body), Paragraph(vr["section"], body), "Pass" if vr["pass"] else "Fail"]
            )
        v_table = Table(v_rows, colWidths=[1.6 * inch, 2.4 * inch, 1.4 * inch, 0.7 * inch], repeatRows=1)
        v_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f3f7")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cfd4dc")),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(v_table)

    if draft.get("review_signoff"):
        story.append(Paragraph("Review and Sign-off", h1))
        rs_rows = [["Role", "Name", "Status", "Date"]] + [
            [rr["role"], rr["name"], rr["status"], rr["date"]] for rr in draft["review_signoff"]
        ]
        rs_table = Table(rs_rows, colWidths=[1.4 * inch, 1.8 * inch, 1.2 * inch, 1.2 * inch])
        rs_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f3f7")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cfd4dc")),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(rs_table)

    for i, s in enumerate(draft["sections"], start=1):
        story.append(Paragraph(f"{i}. {s['title']}", h1))
        if s["status"] == "grounded":
            story.append(Paragraph((s["content"] or "(no content)").replace("\n", "<br/>"), body))
        else:
            detail = s.get("conflict_detail") if s["status"] == "conflict" else s.get("needs_input_detail")
            style = flagged_conflict if s["status"] == "conflict" else flagged_needs_input
            story.append(Paragraph(f"<b>{STATUS_LABEL[s['status']]}</b> — {detail or 'No detail recorded.'}", style))
        for label, b64 in (s.get("images") or {}).items():
            story.append(Paragraph(f"<b>{label}</b>", body))
            img_buf = io.BytesIO(base64.b64decode(b64))
            with PILImage.open(img_buf) as pil_img:
                w, h = pil_img.size
            img_buf.seek(0)
            max_w = 5.5 * inch
            display_w = min(max_w, w)
            display_h = display_w * (h / w)
            story.append(Image(img_buf, width=display_w, height=display_h))
            story.append(Spacer(1, 8))

    story.append(Paragraph("Extraction Ledger", h1))
    story.append(Paragraph("Every atomic fact the agent pulled from the inputs, cited back to its source.", body))
    ledger_rows = [["Fact", "Source", "Quote"]]
    for e in draft["ledger"]:
        ledger_rows.append(
            [
                Paragraph(e["fact"], body),
                Paragraph(e["source_id"], body),
                Paragraph(e["source_quote"], body),
            ]
        )
    ledger_table = Table(ledger_rows, colWidths=[2.3 * inch, 1.2 * inch, 2.5 * inch], repeatRows=1)
    ledger_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f3f7")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cfd4dc")),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(ledger_table)

    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            f"Exported from CodeCanvas · request_id {draft['request_id'][:8]} · {draft['duration_ms'] / 1000:.1f}s generation time",
            ParagraphStyle("FSDFooter", parent=styles["BodyText"], fontSize=7, textColor=colors.HexColor("#888888")),
        )
    )

    doc.build(story)
    return buf.getvalue()


# --- Intake Validation PDF -------------------------------------------------
# A separate report from the FSD export above -- this one is the readiness
# assessment itself (verdict, radar, quality checks, corrections, the
# itemized checklist), not the FSD content. Same reportlab conventions.

IV_STATUS_COLOR = {
    "pass": colors.HexColor("#1a7f37"),
    "warn": colors.HexColor("#8a5a00"),
    "fail": colors.HexColor("#991b1b"),
    "cannot_verify": colors.HexColor("#555555"),
}
IV_STATUS_LABEL = {"pass": "Pass", "warn": "Warn", "fail": "Fail", "cannot_verify": "Cannot Verify"}
IV_SEVERITY_LABEL = {"critical": "CRITICAL", "high": "HIGH", "medium": "MEDIUM", "low": "LOW"}
IV_VERDICT_LABEL = {"ready": "Ready", "needs_correction": "Needs Correction", "not_ready": "Not Ready"}


def build_intake_validation_pdf(draft: dict, obj: dict, project: dict) -> bytes:
    iv = draft.get("intake_validation")
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=LETTER, topMargin=0.75 * inch, bottomMargin=0.75 * inch, leftMargin=0.75 * inch, rightMargin=0.75 * inch
    )
    styles = getSampleStyleSheet()
    h0 = ParagraphStyle("IVH0", parent=styles["Title"], spaceAfter=4)
    h1 = ParagraphStyle("IVH1", parent=styles["Heading1"], spaceBefore=14, spaceAfter=6)
    body = ParagraphStyle("IVBody", parent=styles["BodyText"], spaceAfter=8, leading=14)
    meta = ParagraphStyle("IVMeta", parent=styles["BodyText"], textColor=colors.HexColor("#555555"), spaceAfter=14)
    cell = ParagraphStyle("IVCell", parent=styles["BodyText"], fontSize=8, leading=10)

    story: list[Any] = [
        Paragraph(f"{obj['name']} — Intake Validation Assessment", h0),
        Paragraph(
            f"Project: {project['name']} | Object: {obj['name']} ({obj['type']}, {obj['module']}) | FSD Version: {draft['version']}",
            meta,
        ),
    ]

    if not iv:
        story.append(
            Paragraph(
                "No Intake Validation result is available for this draft "
                f"({draft.get('intake_validation_status', 'pending')}"
                + (f": {draft['intake_validation_error']}" if draft.get("intake_validation_error") else "")
                + ").",
                body,
            )
        )
        doc.build(story)
        return buf.getvalue()

    verdict_style = ParagraphStyle("IVVerdict", parent=styles["Heading2"], textColor=IV_STATUS_COLOR.get(
        "pass" if iv["verdict"] == "ready" else ("fail" if iv["verdict"] == "not_ready" else "warn")
    ))
    story.append(Paragraph(f"{IV_VERDICT_LABEL.get(iv['verdict'], iv['verdict'])} · {iv['overall_pct']:.0f}%", verdict_style))
    story.append(Paragraph(iv["assessment"], body))

    story.append(Paragraph("Readiness by Dimension", h1))
    radar_rows = [["Dimension", "Score"]] + [
        [dim.replace("_", " ").title(), f"{score}/100"] for dim, score in iv["radar"].items()
    ]
    radar_table = Table(radar_rows, colWidths=[2.2 * inch, 1 * inch])
    radar_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f3f7")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cfd4dc")),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ]
        )
    )
    story.append(radar_table)

    story.append(Paragraph("Quality Checks", h1))
    qc_rows = [["Check", "Status", "Finding", "Suggestion"]]
    for qc in iv["quality_checks"]:
        qc_rows.append(
            [
                Paragraph(qc["title"], cell),
                Paragraph(IV_STATUS_LABEL.get(qc["status"], qc["status"]), cell),
                Paragraph(qc["finding"], cell),
                Paragraph(qc.get("suggestion") or "—", cell),
            ]
        )
    qc_table = Table(qc_rows, colWidths=[1.3 * inch, 0.7 * inch, 2.3 * inch, 2.2 * inch], repeatRows=1)
    qc_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f3f7")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cfd4dc")),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(qc_table)

    if iv.get("corrections"):
        story.append(Paragraph("Corrections Required", h1))
        for c in iv["corrections"]:
            story.append(
                Paragraph(
                    f"<b>{IV_SEVERITY_LABEL.get(c['severity'], c['severity'].upper())}</b> — {c['text']}",
                    ParagraphStyle("IVCorrection", parent=body, textColor=IV_STATUS_COLOR.get(
                        "fail" if c["severity"] in ("critical", "high") else "warn"
                    )),
                )
            )

    story.append(Paragraph("Intake Checklist", h1))
    checklist_rows = [["ID", "Category", "Severity", "Check", "Status", "Finding"]]
    for item in iv["checklist"]:
        checklist_rows.append(
            [
                item["item_id"],
                item["category"],
                item["severity"],
                Paragraph(item["check"], cell),
                IV_STATUS_LABEL.get(item["status"], item["status"]),
                Paragraph(item["finding"], cell),
            ]
        )
    checklist_table = Table(
        checklist_rows, colWidths=[0.55 * inch, 0.75 * inch, 0.55 * inch, 1.7 * inch, 0.7 * inch, 1.95 * inch], repeatRows=1
    )
    checklist_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f3f7")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cfd4dc")),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(checklist_table)

    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            "Generated by CodeCanvas's Intake Validation agent. Checklist items marked \"Cannot Verify\" would "
            "require a live SAP system connection this tool does not have -- they describe what's named in the "
            "document, not whether it exists in any real system.",
            ParagraphStyle("IVFooter", parent=styles["BodyText"], fontSize=7, textColor=colors.HexColor("#888888")),
        )
    )

    doc.build(story)
    return buf.getvalue()
