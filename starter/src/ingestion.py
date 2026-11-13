"""Read and normalize source data."""
import re
import unicodedata
from pathlib import Path

from pypdf import PdfReader

from .models import DocumentPage

# OpenStax running footer, e.g. "116     5 • Loops" or "5.2 • For loop     119".
_FOOTER = re.compile(r"^\s*(\d+)\s{3,}\S.*$|^\S.*\S\s{3,}(\d+)\s*$")
_BOILERPLATE = "Access for free at openstax.org"


def _outline_ranges(reader: PdfReader) -> list[tuple[int, int, str]]:
    """Flatten the PDF outline into (start_page, level, title), 1-based pages."""
    out: list[tuple[int, int, str]] = []

    def walk(items, level):
        for it in items:
            if isinstance(it, list):
                walk(it, level + 1)
            else:
                out.append((reader.get_destination_page_number(it) + 1, level, it.title))

    walk(reader.outline, 0)
    return out


def load_pdf(path: Path, document_id: str, source: str) -> list[DocumentPage]:
    """Extract each physical page with its PDF page number, printed page and outline metadata.

    Pages with no extractable text are kept with empty text and `metadata["empty"] = True`.
    """
    reader = PdfReader(path)
    outline = _outline_ranges(reader)
    chapters = [(p, t) for p, lvl, t in outline if lvl == 0]
    sections = [(p, t) for p, lvl, t in outline if lvl == 1 and re.match(r"\d+\.\d+ ", t)]

    pages = []
    for i, pdf_page in enumerate(reader.pages, start=1):
        lines = (pdf_page.extract_text() or "").splitlines()
        lines = [ln for ln in lines if ln.strip() != _BOILERPLATE]
        printed_page = None
        # The running footer is one of the last two non-empty lines.
        for j in range(len(lines) - 1, max(len(lines) - 3, -1), -1):
            m = _FOOTER.match(lines[j])
            if m:
                printed_page = int(m.group(1) or m.group(2))
                del lines[j]
                break
        text = normalize_text("\n".join(lines))

        chapter = next((t for p, t in reversed(chapters) if p <= i), None)
        # Sections overlapping this page: the one active at its top plus any starting on it.
        active = [t for p, t in sections if p < i][-1:]
        starting = [t for p, t in sections if p == i]
        page_sections = [s for s in active + starting
                         if chapter and s.split(".")[0] == _chapter_number(chapter)]
        pages.append(DocumentPage(
            document_id=document_id,
            source=source,
            page=i,
            text=text,
            metadata={
                "printed_page": printed_page,
                "chapter_title": chapter,
                "chapter": int(_chapter_number(chapter)) if _chapter_number(chapter) else None,
                "sections": page_sections,
                "empty": not text,
            },
        ))
    return pages


def _chapter_number(title: str | None) -> str | None:
    m = re.match(r"Chapter (\d+)", title or "")
    return m.group(1) if m else None


def normalize_text(text: str) -> str:
    """NFKC-normalize, fix the mis-mapped bullet glyph, trim line ends, collapse blank runs.

    Leading spaces are kept because Python code indentation is meaningful.
    """
    text = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("�", "•")  # pypdf maps OpenStax bullets to U+FFFD
    text = text.replace(" ", " ").replace("\t", "    ")
    text = "\n".join(ln.rstrip() for ln in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip()
