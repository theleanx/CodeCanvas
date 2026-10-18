"""
Renders the two images the Enhancement FSD template requires: a business
process-flow flowchart, and (when the object has a user-facing surface) a
screen wireframe.

Deliberately NOT done via Mermaid/Graphviz/a headless browser -- all three
need extra system packages or a Chromium install in the Docker image, which
is exactly the weight this project has avoided elsewhere (reportlab over
weasyprint, for the same reason). Pillow is pure-Python, already a
transitive dependency (reportlab pulls it in), and ships a scalable default
font (Pillow >= 10.1) so no system font package is needed either.

Both renderers take plain structured data (ordered steps / field labels),
not pixel coordinates from the model -- the model says WHAT belongs in the
diagram, this module decides WHERE it goes. That keeps the image
deterministic and reviewable, in the same spirit as the ledger: content
comes from the agent, layout does not.
"""

from __future__ import annotations

import base64
import io
import textwrap

from PIL import Image, ImageDraw, ImageFont

_INK = (26, 34, 51)
_MUTED = (100, 116, 139)
_WHITE = (255, 255, 255)
_BOX_FILL = (234, 240, 253)
_BOX_BORDER = (42, 91, 215)
_ARROW = (100, 116, 139)
_BG = (255, 255, 255)
_SWIMLANE_BORDER = (226, 229, 236)
_SWIMLANE_LABEL_BG = (16, 26, 51)

_FONT_BODY = ImageFont.load_default(size=18)
_FONT_LABEL = ImageFont.load_default(size=15)
_FONT_TITLE = ImageFont.load_default(size=22)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    if not text:
        return [""]
    # textwrap doesn't know pixel widths, so widen/narrow the character
    # budget until lines actually fit -- good enough for short diagram labels.
    for width_chars in (60, 50, 40, 32, 26, 20, 16):
        lines = textwrap.wrap(text, width=width_chars) or [text]
        if all(draw.textlength(line, font=font) <= max_width for line in lines):
            return lines
    return textwrap.wrap(text, width=14) or [text]


def _to_base64_png(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def render_flow_diagram(steps: list[dict]) -> str:
    """steps: ordered list of {"actor": str|None, "label": str}.

    Renders a top-to-bottom flowchart: one rounded box per step, with its
    actor/swimlane shown as a small pill above the box, connected by
    downward arrows. Returns a base64-encoded PNG (no data: prefix)."""
    if not steps:
        steps = [{"actor": None, "label": "(no process steps provided)"}]

    width = 760
    box_w = 560
    box_x = (width - box_w) // 2
    pad_y = 28
    gap = 56

    scratch = Image.new("RGB", (10, 10), _BG)
    draw = ImageDraw.Draw(scratch)

    heights: list[int] = []
    wrapped: list[list[str]] = []
    for step in steps:
        lines = _wrap(draw, step.get("label", ""), _FONT_BODY, box_w - 40)
        wrapped.append(lines)
        line_h = 24
        box_h = max(64, 28 + len(lines) * line_h)
        if step.get("actor"):
            box_h += 26
        heights.append(box_h)

    total_h = pad_y * 2 + sum(heights) + gap * (len(steps) - 1) + 20
    img = Image.new("RGB", (width, total_h), _BG)
    draw = ImageDraw.Draw(img)

    y = pad_y
    centers_x = width // 2
    for i, (step, lines, box_h) in enumerate(zip(steps, wrapped, heights)):
        actor = step.get("actor")
        text_top = y
        if actor:
            pill_text = actor.upper()
            pill_w = draw.textlength(pill_text, font=_FONT_LABEL) + 24
            draw.rounded_rectangle(
                [centers_x - pill_w / 2, y, centers_x + pill_w / 2, y + 22],
                radius=11,
                fill=_SWIMLANE_LABEL_BG,
            )
            draw.text((centers_x, y + 11), pill_text, font=_FONT_LABEL, fill=_WHITE, anchor="mm")
            text_top = y + 26

        draw.rounded_rectangle(
            [box_x, text_top, box_x + box_w, text_top + (box_h - (26 if actor else 0))],
            radius=14,
            outline=_BOX_BORDER,
            width=2,
            fill=_BOX_FILL,
        )
        step_no_w = 30
        draw.ellipse(
            [box_x - step_no_w / 2 - 6, text_top + 10, box_x + step_no_w / 2 - 6, text_top + 10 + step_no_w],
            fill=_BOX_BORDER,
        )
        draw.text(
            (box_x - 6, text_top + 10 + step_no_w / 2),
            str(i + 1),
            font=_FONT_LABEL,
            fill=_WHITE,
            anchor="mm",
        )
        ty = text_top + 16
        for line in lines:
            draw.text((centers_x, ty + 10), line, font=_FONT_BODY, fill=_INK, anchor="mm")
            ty += 24

        if i < len(steps) - 1:
            arrow_top = y + box_h
            arrow_bottom = arrow_top + gap
            draw.line([(centers_x, arrow_top), (centers_x, arrow_bottom - 10)], fill=_ARROW, width=2)
            draw.polygon(
                [
                    (centers_x - 7, arrow_bottom - 10),
                    (centers_x + 7, arrow_bottom - 10),
                    (centers_x, arrow_bottom),
                ],
                fill=_ARROW,
            )
        y += box_h + gap

    return _to_base64_png(img)


def render_wireframe(screen_title: str, fields: list[str]) -> str:
    """fields: ordered list of plain field labels (e.g. "Customer PO Number").
    Renders a generic screen/tab mockup: a title bar and a stacked column of
    labeled input boxes -- enough to visualize the surface without claiming
    pixel-exact UI fidelity. Returns a base64-encoded PNG (no data: prefix)."""
    if not fields:
        fields = ["(no user-facing fields provided)"]

    width = 640
    margin = 24
    row_h = 54
    title_h = 56
    footer_h = 56
    height = title_h + margin * 2 + len(fields) * row_h + footer_h

    img = Image.new("RGB", (width, height), _BG)
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle([0, 0, width - 1, height - 1], radius=10, outline=_SWIMLANE_BORDER, width=2, fill=_BG)
    draw.rounded_rectangle([0, 0, width - 1, title_h], radius=10, fill=_SWIMLANE_LABEL_BG)
    draw.rectangle([0, title_h - 10, width - 1, title_h], fill=_SWIMLANE_LABEL_BG)
    draw.text((margin, title_h / 2), screen_title or "Screen", font=_FONT_TITLE, fill=_WHITE, anchor="lm")
    for i, dot_x in enumerate((width - 30, width - 54, width - 78)):
        draw.ellipse([dot_x - 5, title_h / 2 - 5, dot_x + 5, title_h / 2 + 5], fill=(174, 182, 204))

    y = title_h + margin
    label_w = 190
    for field in fields:
        draw.text((margin, y + row_h / 2 - 20), field, font=_FONT_LABEL, fill=_MUTED, anchor="lm")
        box_x0 = margin
        box_x1 = width - margin
        box_y0 = y + row_h / 2 - 2
        box_y1 = y + row_h - 8
        draw.rounded_rectangle([box_x0, box_y0, box_x1, box_y1], radius=6, outline=(203, 210, 223), width=2, fill=(249, 250, 252))
        y += row_h

    btn_w, btn_h = 120, 34
    draw.rounded_rectangle(
        [width - margin - btn_w, height - footer_h / 2 - btn_h / 2, width - margin, height - footer_h / 2 + btn_h / 2],
        radius=8,
        fill=_BOX_BORDER,
    )
    draw.text((width - margin - btn_w / 2, height - footer_h / 2), "Save", font=_FONT_LABEL, fill=_WHITE, anchor="mm")

    return _to_base64_png(img)
