"""Job descriptions as readable, safe HTML.

Scraped descriptions arrive as plain text, HTML-escaped text (`AI &amp; Data`), markdown-ish
text (`- bullets`, `## headings`, `**bold**`) or, rarely, escaped HTML (`&lt;p&gt;`). Nothing
from the source is trusted as markup: entities are decoded, any tags are reduced to line
breaks and dropped, everything is escaped, and only then are paragraphs, bullet lists,
headings and bold added back by us."""
import html
import re

from markupsafe import Markup, escape

_BREAK_TAGS = re.compile(r"<\s*(?:br|/p|/div|/li|/ul|/ol|/h[1-6]|/tr)\s*/?\s*>", re.I)
_LI_TAG = re.compile(r"<\s*li\b[^>]*>", re.I)
_ANY_TAG = re.compile(r"<[^>]*>")
_BULLET = re.compile(r"^\s*(?:[-*•·▪◦]|\d{1,2}[.)])\s+(.+)$")
_MD_HEADING = re.compile(r"^\s*#{1,6}\s+(.+?)\s*#*\s*$")
_LABEL_HEADING = re.compile(r"^\s*([A-Z][^.!?:]{1,60}):\s*$")
_BOLD = re.compile(r"\*\*(.+?)\*\*")


def _decode(text):
    # Some sources escape twice (&amp;amp;); two rounds covers them without looping on data.
    for _ in range(2):
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded
    return text


def _heading(line):
    for pattern in (_MD_HEADING, _LABEL_HEADING):
        match = pattern.match(line)
        if match:
            return match.group(1).rstrip(" :")
    stripped = line.strip()
    letters = [c for c in stripped if c.isalpha()]
    if 3 <= len(stripped) <= 60 and letters and stripped.isupper() and not stripped.endswith("."):
        return stripped.title()
    return None


def _inline(text):
    """Escaped text with **bold** turned into <strong> (the only inline markup kept)."""
    return _BOLD.sub(r"<strong>\1</strong>", str(escape(text.strip())))


def format_description(text):
    if not text or not str(text).strip():
        return Markup("")
    text = _decode(str(text)).replace("\r\n", "\n").replace("\r", "\n")
    text = _LI_TAG.sub("\n- ", _BREAK_TAGS.sub("\n", text))
    text = _decode(_ANY_TAG.sub("", text)).replace("\xa0", " ")

    out, paragraph, bullets = [], [], []

    def flush():
        if paragraph:
            out.append("<p>" + "<br>".join(_inline(line) for line in paragraph) + "</p>")
            paragraph.clear()
        if bullets:
            out.append("<ul>" + "".join(f"<li>{_inline(item)}</li>" for item in bullets) + "</ul>")
            bullets.clear()

    for line in text.split("\n"):
        if not line.strip():
            flush()
            continue
        bullet = _BULLET.match(line)
        if bullet:
            if paragraph:
                flush()
            bullets.append(bullet.group(1))
            continue
        heading = _heading(line)
        if heading:
            flush()
            out.append(f"<h3>{_inline(heading)}</h3>")
            continue
        if bullets:
            flush()
        paragraph.append(line)
    flush()
    return Markup("\n".join(out))


def plain_text(text, limit=12000):
    """The description as plain text (entities decoded, tags dropped, whitespace tidied),
    for the local LLM to read."""
    if not text:
        return ""
    text = _decode(str(text)).replace("\r\n", "\n").replace("\r", "\n")
    text = _LI_TAG.sub("\n- ", _BREAK_TAGS.sub("\n", text))
    text = _decode(_ANY_TAG.sub("", text)).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()[:limit]
