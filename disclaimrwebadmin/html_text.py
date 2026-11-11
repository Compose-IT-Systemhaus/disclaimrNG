"""Turn an HTML e-mail signature (as written in the TinyMCE editor) into plain text."""

from __future__ import annotations

import re

from lxml import html as lxml_html

BLOCKS = {
    "p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "table", "ul", "ol",
    "blockquote",
}  # fmt: skip
CELLS = {"td", "th"}
SKIPPED = {"img", "script", "style"}
IMAGE_PLACEHOLDER = re.compile(r'\{image\["[^"]*"\]\}')

# Markers used while walking, resolved in html_to_text().
BLOCK, CELL_GAP = "\x00", "\x01"


def _link(el, text: str) -> str:
    href = (el.get("href") or "").strip()
    bare = re.sub(r"^(mailto|tel):", "", href, flags=re.I)
    if not href or text.strip() in ("", href, bare):
        return text
    return f"{text} <{href}>"


def _walk(el) -> str:
    """Text of `el` including its children, but not its own tail."""
    tag = el.tag
    if not isinstance(tag, str) or tag in SKIPPED:  # comments, images, ...
        return ""
    if tag == "br":
        return "\n"
    if tag == "hr":
        return f"{BLOCK}--{BLOCK}"
    parts = [re.sub(r"[ \t\r\n]+", " ", el.text or "")]
    cells = 0
    for child in el:
        if child.tag in CELLS:
            parts.append(CELL_GAP if cells else "")
            cells += 1
        parts.append(_walk(child))
        parts.append(re.sub(r"[ \t\r\n]+", " ", child.tail or ""))
    text = "".join(parts)
    if tag == "a":
        text = _link(el, text)
    return f"{BLOCK}{text}{BLOCK}" if tag in BLOCKS else text


def html_to_text(html: str) -> str:
    """Return the plain-text rendering of `html`; template placeholders stay untouched."""
    if not html.strip():
        return ""
    text = _walk(lxml_html.fromstring(f"<div>{html}</div>"))
    # Source whitespace between blocks vanishes here; a lone &nbsp; (empty paragraph) stays a blank line.
    text = re.sub(r" *\x00[ \x00]*", "\n", text).replace("\xa0", " ")
    lines = []
    for line in text.split("\n"):
        clean = IMAGE_PLACEHOLDER.sub("", re.sub(r"[ \t]+", " ", line))
        clean = re.sub(rf" ?{CELL_GAP} ?", "  ", clean).strip()
        if clean or not IMAGE_PLACEHOLDER.search(line):  # drop lines emptied by an image tag
            lines.append(clean)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
