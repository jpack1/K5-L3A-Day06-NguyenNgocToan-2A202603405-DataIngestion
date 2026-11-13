"""Fixed-size and structure-aware chunking. Chunks never cross a page, so `page` stays exact."""
import re

from .models import Chunk, DocumentPage

# Section headings such as "5.2 For loop" or "10.4 Conditionals and looping in dictionaries".
_HEADING = re.compile(r"^\d+\.\d+ [A-Z]")
# A wrapped prose line in this PDF is ~100+ chars; a shorter line ends a paragraph/heading/code line.
_FULL_LINE = 80


def _chunk(page: DocumentPage, idx: int, start: int, end: int, strategy: str) -> Chunk:
    return Chunk(
        chunk_id=f"{page.document_id}:p{page.page}:{strategy}{idx}",
        document_id=page.document_id,
        source=page.source,
        page=page.page,
        text=page.text[start:end],
        metadata={**page.metadata, "char_start": start, "char_end": end},
    )


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    """Character windows of `size` with `overlap`, restarted on every page."""
    if not 0 <= overlap < size:
        raise ValueError("need 0 <= overlap < size")
    chunks, start, text = [], 0, page.text
    while start < len(text):
        end = min(start + size, len(text))
        if text[start:end].strip():
            chunks.append(_chunk(page, len(chunks), start, end, "f"))
        if end == len(text):
            break
        start = end - overlap
    return chunks


def _paragraphs(text: str) -> list[tuple[int, int, bool]]:
    """(start, end, is_heading) spans; a paragraph ends after a short line or before a heading."""
    spans, pos, cur, prev_short = [], 0, None, True
    for line in text.split("\n"):
        start, end = pos, pos + len(line)
        pos = end + 1
        heading = bool(_HEADING.match(line))
        if cur is None or prev_short or heading or cur[2]:
            if cur:
                spans.append(tuple(cur))
            cur = [start, end, heading]
        else:
            cur[1] = end
        prev_short = len(line) < _FULL_LINE
    if cur:
        spans.append(tuple(cur))
    return spans


def _split_long(text: str, start: int, end: int, max_size: int) -> list[tuple[int, int]]:
    """Split an oversized paragraph at the last sentence end, else the last space, before max_size."""
    parts = []
    while end - start > max_size:
        window = text[start:start + max_size]
        cut = max(window.rfind(". "), window.rfind(".\n"))
        cut = cut + 1 if cut > max_size // 3 else window.rfind(" ")
        cut = cut if cut > 0 else max_size
        parts.append((start, start + cut))
        start += cut
    parts.append((start, end))
    return parts


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    """Greedily pack whole paragraphs up to max_size; a section heading always starts a new chunk."""
    spans = []
    for s, e, heading in _paragraphs(page.text):
        for i, (ps, pe) in enumerate(_split_long(page.text, s, e, max_size)):
            spans.append((ps, pe, heading and i == 0))

    chunks, cur = [], None
    for s, e, heading in spans:
        if cur and (heading or e - cur[0] > max_size):
            chunks.append(cur)
            cur = None
        cur = [cur[0], e] if cur else [s, e]
    if cur:
        chunks.append(cur)
    return [_chunk(page, i, s, e, "p") for i, (s, e) in enumerate(chunks) if page.text[s:e].strip()]
