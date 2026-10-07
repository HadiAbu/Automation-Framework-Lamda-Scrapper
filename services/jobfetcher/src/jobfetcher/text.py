from __future__ import annotations

import html
import re

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def html_to_text(raw: str) -> str:
    """Greenhouse sends entity-escaped HTML: unescape, drop tags, unescape again."""
    text = html.unescape(raw)
    text = _TAG.sub(" ", text)
    text = html.unescape(text)
    return _SPACE.sub(" ", text).strip()
