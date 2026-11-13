"""Download the corpus, select content pages and write data/manifest.json + data/pages.jsonl.

Run from starter/:  python scripts/prepare_data.py
"""
import hashlib
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.ingestion import load_pdf  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data"
URL = "https://assets.openstax.org/oscms-prodcms/media/documents/Introduction_to_Python_Programming-WEB.pdf"
PDF = DATA / "raw" / "Introduction_to_Python_Programming-WEB.pdf"
SHA256 = "e1298e4fcfe541a8fc3bb786c5756d3d2be8e6ffc07997f1bc1e0ac270be383d"
SOURCE_ID = "openstax-intro-python"
# Chapters 5 Loops, 9 Lists, 10 Dictionaries: inclusive PDF page ranges from the PDF outline.
CHAPTER_RANGES = {5: (125, 146), 9: (221, 236), 10: (237, 258)}
MIN_CHARS = 300  # below this a page is only a link/stub, not useful content


def main() -> None:
    if not PDF.exists():
        PDF.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(URL, PDF)
    digest = hashlib.sha256(PDF.read_bytes()).hexdigest()
    if digest != SHA256:
        raise SystemExit(f"PDF checksum mismatch: {digest} (the OpenStax file changed; re-verify pages)")

    pages = load_pdf(PDF, SOURCE_ID, f"data/raw/{PDF.name}")
    selected, excluded = [], []
    for p in pages:
        chapter = p.metadata["chapter"]
        lo, hi = CHAPTER_RANGES.get(chapter, (0, -1))
        if not lo <= p.page <= hi:
            continue
        if p.metadata["empty"] or len(p.text) < MIN_CHARS:
            excluded.append({"page": p.page, "chars": len(p.text),
                             "reason": "no useful content (multimedia link only)"})
            continue
        selected.append(p)

    with open(DATA / "pages.jsonl", "w", encoding="utf-8") as f:
        for p in selected:
            f.write(json.dumps({"document_id": p.document_id, "source": p.source, "page": p.page,
                                **p.metadata, "chars": len(p.text), "text": p.text},
                               ensure_ascii=False) + "\n")

    manifest = {
        "corpus": "Introduction to Python Programming (OpenStax), chapters 5, 9, 10",
        "counting_rule": (f"Count PDF physical pages of chapters 5, 9, 10 (ranges from the PDF outline) "
                          f"with >= {MIN_CHARS} normalized characters; exclude stub pages. "
                          "Cover, contents, preface, other chapters, answer key and index are not used."),
        "sources": [{
            "source_id": SOURCE_ID,
            "title": "Introduction to Python Programming",
            "publisher": "OpenStax, Rice University",
            "source_path_or_url": URL,
            "local_path": f"data/raw/{PDF.name}",
            "book_page": "https://openstax.org/details/books/introduction-python-programming",
            "license_or_permission": "CC BY-NC-SA 4.0 (https://creativecommons.org/licenses/by-nc-sa/4.0/); "
                                     "non-commercial educational use with attribution",
            "accessed_at": str(date.today()),
            "snapshot": {"sha256": digest, "pdf_physical_pages": len(pages)},
            "chapters_used": {str(c): {"title": next(p.metadata["chapter_title"] for p in pages
                                                     if p.metadata["chapter"] == c),
                                       "pdf_pages": list(r)} for c, r in CHAPTER_RANGES.items()},
            "physical_pages_in_ranges": sum(hi - lo + 1 for lo, hi in CHAPTER_RANGES.values()),
            "counted_pages": [{"page": p.page, "printed_page": p.metadata["printed_page"],
                               "chapter": p.metadata["chapter"], "sections": p.metadata["sections"],
                               "chars": len(p.text)} for p in selected],
            "counted_page_total": len(selected),
            "excluded_pages": excluded,
            "total_chars": sum(len(p.text) for p in selected),
        }],
        "metadata_fields": {
            "document_id": "str, fixed source id",
            "source": "str, local PDF path",
            "page": "int, PDF physical page (1-based)",
            "printed_page": "int, page number printed in the book footer",
            "chapter": "int, from PDF outline level 0; filter field",
            "chapter_title": "str, from PDF outline",
            "sections": "list[str], outline sections overlapping the page",
        },
        "known_issues": [
            "pypdf maps bullet glyphs to U+FFFD; normalized to '•'.",
            "Code indentation from PDF extraction may be approximate.",
            "Figures/videos are not extracted (text only); no OCR needed.",
        ],
    }
    (DATA / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"counted pages: {len(selected)}  excluded: {len(excluded)}  "
          f"chars: {manifest['sources'][0]['total_chars']}")
    assert len(selected) >= 30, "corpus must have at least 30 content pages"


if __name__ == "__main__":
    main()
