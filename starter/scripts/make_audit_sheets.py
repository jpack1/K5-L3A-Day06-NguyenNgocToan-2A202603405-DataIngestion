"""Build manual-labeling sheets in results/manual/ from the corpus and results/test/traces.jsonl.

Run from starter/ after `python -m src.run --split test`:  python scripts/make_audit_sheets.py
Score columns are left empty for the human grader.
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.prepare_data import CHAPTER_RANGES, PDF, SOURCE_ID  # noqa: E402
from src.chunking import _HEADING  # noqa: E402
from src.evaluation import collapse  # noqa: E402
from src.ingestion import load_pdf  # noqa: E402
from src.run import STRATEGIES, load_pages  # noqa: E402

OUT = ROOT / "results" / "manual"


def write(name, rows):
    if (OUT / name).exists() and "--force" not in sys.argv:
        raise SystemExit(f"{OUT / name} exists (may hold manual labels); pass --force to overwrite")
    with open(OUT / name, "w", encoding="utf-8-sig", newline="") as f:  # BOM so Excel opens UTF-8
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{name}: {len(rows)} rows")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pages = sorted(load_pages(), key=lambda p: p.page)

    # Coherence: 10 positions fixed before scoring = middle character of every 6th sorted page.
    rows = []
    for i, p in enumerate(pages[::6][:10], start=1):
        offset = len(p.text) // 2
        for name in ("A", "B"):  # C uses B's chunks, so its coherence equals B's
            # First chunk ending after the offset (covers it, or follows it if offset is a boundary newline).
            chunk = next(c for c in STRATEGIES[name][1](p) if offset < c.metadata["char_end"])
            rows.append({"position": f"pos{i:02d}", "page": p.page, "char_offset": offset,
                         "text_at_position": p.text[max(0, offset - 40):offset + 40].replace("\n", " "),
                         "strategy": name, "chunk_id": chunk.chunk_id, "chunk_chars": len(chunk.text),
                         "chunk_text": chunk.text, "score_0_2": "", "reason": "", "grader": ""})
    write("coherence.csv", rows)

    traces = [json.loads(l) for l in open(ROOT / "results" / "test" / "traces.jsonl", encoding="utf-8")]
    # Independent re-extraction straight from the PDF (not from pages.jsonl) for the auto checks.
    pdf_pages = {p.page: p for p in load_pdf(PDF, SOURCE_ID, "")}
    meta, grounding = [], []
    for t in traces:
        for r in t["top_k"]:
            pdf = pdf_pages[r["page"]]
            heads = [ln for ln in r["text"].splitlines() if _HEADING.match(ln)]
            meta.append({"strategy": t["strategy"], "id": t["id"], "filter": json.dumps(t["filter"]),
                         "rank": r["rank"], "chunk_id": r["chunk_id"], "page": r["page"],
                         "printed_page": r["printed_page"], "chapter": r["chapter"],
                         "sections": "; ".join(r["sections"] or []), "text_start": r["text"][:120].replace("\n", " "),
                         "auto_page_ok": collapse(r["text"]) in collapse(pdf.text),
                         # Book pages in chapters 5/9/10 are PDF page - 10; chapter openers have no footer.
                         "auto_printed_ok": r["printed_page"] == r["page"] - 10 or (
                             r["printed_page"] is None and r["page"] in (125, 221, 237)),
                         "auto_chapter_ok": CHAPTER_RANGES[r["chapter"]][0] <= r["page"] <= CHAPTER_RANGES[r["chapter"]][1],
                         # A section heading inside the chunk must be one of the page's listed sections, and a
                         # chunk wholly inside the chapter outline (before "Introduction") belongs to no section.
                         "auto_sections_ok": all(h in (r["sections"] or []) for h in heads) and not (
                             "\nIntroduction\n" in pdf.text
                             and collapse(r["text"]) in collapse(pdf.text[:pdf.text.index("\nIntroduction\n")])),
                         "matches_filter": "" if r["matches_filter"] is None else r["matches_filter"],
                         "metadata_ok": "", "note": "", "grader": ""})
        grounding.append({"strategy": t["strategy"], "id": t["id"], "question": t["question"],
                          "filter_applied": json.dumps(t["filter_applied"]),
                          "auto_hit_at_3": t["hit_at_3"],
                          "top3": "\n\n".join(f"[{r['rank']}] p{r['page']} ch{r['chapter']}: {r['text']}"
                                              for r in t["top_k"]),
                          "score_0_2": "", "reason": "", "grader": ""})
    write("test_metadata.csv", meta)
    write("test_grounding.csv", grounding)


if __name__ == "__main__":
    main()
