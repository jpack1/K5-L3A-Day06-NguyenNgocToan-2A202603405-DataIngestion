"""Offline self-check (no API, no DB). Run from starter/:  python -m tests.test_pipeline"""
import json
from pathlib import Path

from src.chunking import by_paragraph, fixed_size
from src.evaluation import evaluate_query
from src.run import load_pages

ROOT = Path(__file__).resolve().parents[1]


def test_chunkers_cover_pages_within_size():
    for p in load_pages():
        a, b = fixed_size(p, 500, 50), by_paragraph(p, 500)
        for chunks in (a, b):
            assert all(len(c.text) <= 500 and c.page == p.page for c in chunks)
            assert chunks[0].metadata["char_start"] == 0 and chunks[-1].metadata["char_end"] == len(p.text)
        # B partitions the page: no overlap, and only the boundary newline between chunks.
        for x, y in zip(b, b[1:]):
            gap = p.text[x.metadata["char_end"]:y.metadata["char_start"]]
            assert x.metadata["char_end"] <= y.metadata["char_start"] and not gap.strip()
        # A windows overlap by exactly 50 chars.
        for x, y in zip(a, a[1:]):
            assert x.metadata["char_end"] - y.metadata["char_start"] == 50


def test_heading_starts_new_paragraph_chunk():
    p = next(p for p in load_pages() if p.page == 128)  # "5.2 For loop" starts mid-page
    assert any(c.text.startswith("5.2 For loop") for c in by_paragraph(p, 500))


def test_evaluate_query_hit_rules():
    q = json.loads(open(ROOT / "benchmark" / "questions.jsonl", encoding="utf-8").readline())  # q01, gold p125, alt p143
    hit = {"chunk_id": "x", "document_id": q["gold_source_id"], "page": 143, "printed_page": 133, "chapter": 5,
           "sections": [], "score": 0.9, "text": "junk " + q["alt_evidence"][0]["quote"].replace(" ", "\n ")}
    wrong_page = {**hit, "page": 126}
    partial = {**hit, "text": q["alt_evidence"][0]["quote"][:40]}
    t = evaluate_query(q, [wrong_page, partial, hit])
    assert not t["hit_at_1"] and t["hit_at_3"] and not t["split_evidence"]
    t = evaluate_query(q, [partial])
    assert not t["hit_at_3"] and t["split_evidence"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
