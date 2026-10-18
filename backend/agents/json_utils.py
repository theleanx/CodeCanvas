"""Small shared helper: Claude is asked to return raw JSON, but models
sometimes wrap it in a ```json fence anyway. Strip that defensively instead
of trusting the prompt alone -- this is the kind of boring robustness that
matters once this runs unattended."""

import json
import re


def extract_json(raw: str):
    text = raw.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)
