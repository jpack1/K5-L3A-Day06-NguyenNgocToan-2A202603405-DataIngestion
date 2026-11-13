"""Day 06 pipeline: load corpus -> chunk (A, B) -> embed -> pgvector -> retrieve A/B/C -> traces + metrics.

Run from starter/:
    python -m src.run --split dev     # tune / choose the configuration on dev only
    python -m src.run --split test    # once, after the choice is fixed
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from .chunking import by_paragraph, fixed_size
from .embeddings import MyEmbedder
from .evaluation import summarize, evaluate_query
from .models import DocumentPage
from .store import PgVectorStore, text_hash

ROOT = Path(__file__).resolve().parents[1]
PRICE_PER_M_TOKENS = 0.02  # USD, OpenAI text-embedding-3-small list price; check if the model changes

STRATEGIES = {
    # name: (stored chunk set, chunker, uses filter)
    "A": ("A", lambda p: fixed_size(p, size=500, overlap=50), False),
    "B": ("B", lambda p: by_paragraph(p, max_size=500), False),
    "C": ("B", None, True),  # same chunks/vectors as B; only adds the metadata filter
}
CONFIG = {
    "A": {"chunking": "fixed_size", "chunk_size": 500, "overlap": 50, "filter": "none"},
    "B": {"chunking": "by_paragraph (heading-aware, packed)", "chunk_size": 500, "overlap": 0, "filter": "none"},
    "C": {"chunking": "same as B", "chunk_size": 500, "overlap": 0,
          "filter": "chapter = question.filter.chapter when given, else none"},
}


def load_pages() -> list[DocumentPage]:
    pages = []
    for line in open(ROOT / "data" / "pages.jsonl", encoding="utf-8"):
        d = json.loads(line)
        meta = {k: d[k] for k in ("printed_page", "chapter", "chapter_title", "sections")}
        pages.append(DocumentPage(d["document_id"], d["source"], d["page"], d["text"], meta))
    if len(pages) < 30:
        raise SystemExit(f"corpus has {len(pages)} content pages, need >= 30 (run scripts/prepare_data.py)")
    return pages


def ingest(store: PgVectorStore, embedder: MyEmbedder, name: str, chunker, pages) -> dict:
    t0 = time.perf_counter()
    chunks = [c for p in pages for c in chunker(p)]
    have = store.existing_hashes(name, embedder.model_name)
    todo = [c for c in chunks if have.get(c.chunk_id) != text_hash(c.text)]
    tokens_before = embedder.total_tokens
    vectors = embedder.embed_documents([c.text for c in todo]) if todo else []
    deleted = store.upsert(name, todo, vectors, embedder.model_name, keep_ids={c.chunk_id for c in chunks})
    lengths = [len(c.text) for c in chunks]
    stored = store.count(name)
    if stored != len(chunks):
        raise RuntimeError(f"{name}: {stored} rows stored but {len(chunks)} chunks built (duplicates?)")
    tokens = embedder.total_tokens - tokens_before
    return {
        "chunks": len(chunks), "stored_rows": stored, "embedded_now": len(todo),
        "reused_unchanged": len(chunks) - len(todo), "deleted_obsolete": deleted,
        "chars_total": sum(lengths), "len_min": min(lengths), "len_median": statistics.median(lengths),
        "len_mean": round(statistics.mean(lengths), 1), "len_max": max(lengths),
        "len_p10_p90": [statistics.quantiles(lengths, n=10)[0], statistics.quantiles(lengths, n=10)[-1]],
        "embedding_tokens_now": tokens, "cost_usd_now": round(tokens / 1e6 * PRICE_PER_M_TOKENS, 6),
        "ingest_seconds": round(time.perf_counter() - t0, 2),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "validate_benchmark.py")], check=True)
    pages = load_pages()
    questions = [json.loads(l) for l in open(ROOT / "benchmark" / "questions.jsonl", encoding="utf-8") if l.strip()]
    questions = [q for q in questions if args.split == "all" or q["split"] == args.split]

    embedder = MyEmbedder(os.environ.get("EMBEDDING_MODEL", ""))
    store = PgVectorStore(os.environ["DATABASE_URL"], embedder.dimensions)
    store.create_schema()

    ingest_stats = {}
    for name, (stored_as, chunker, _) in STRATEGIES.items():
        if chunker:
            ingest_stats[name] = ingest(store, embedder, stored_as, chunker, pages)
            print(f"[ingest] {name}: {ingest_stats[name]}")

    traces, query_tokens_before = [], embedder.total_tokens
    for q in questions:
        qvec = embedder.embed_query(q["question"])  # one query vector shared by A/B/C
        for name, (stored_as, _, use_filter) in STRATEGIES.items():
            filters = q.get("filter") if use_filter else None
            t = evaluate_query(q, store.search(stored_as, qvec, top_k=3, filters=filters))
            t.update(strategy=name, filter_applied=filters)
            traces.append(t)
    query_tokens = embedder.total_tokens - query_tokens_before

    out = ROOT / "results" / args.split
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "traces.jsonl", "w", encoding="utf-8") as f:
        for t in traces:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    summary = {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "split": args.split,
        "embedding": {"provider": "OpenAI", "model": embedder.model_name, "dimensions": embedder.dimensions,
                      "query_document_handling": "same model, no prefix, raw chunk text"},
        "vector_store": "PostgreSQL 16 + pgvector 0.8.7, table chunks, exact cosine (<=>), no ANN index",
        "configs": CONFIG,
        "ingest": ingest_stats,
        "query_tokens": query_tokens,
        "total_cost_usd_this_run": round(embedder.total_tokens / 1e6 * PRICE_PER_M_TOKENS, 6),
        "metrics": summarize(traces),
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    for k, m in summary["metrics"].items():
        print(f"[{k}] Hit@1 {m['hit_at_1']}/{m['n']}  Hit@3 {m['hit_at_3']}/{m['n']}  "
              f"page@3 {m['page_hit_at_3']}/{m['n']}  split_evidence {m['split_evidence']}  "
              f"filter Hit@3 {m['filter_hit_at_3']}/{m['filter_questions']}  "
              f"filter compliant {m['filter_compliant']}/{m['filter_questions']}")
    print(f"saved {out / 'traces.jsonl'} and {out / 'summary.json'}")


if __name__ == "__main__":
    main()
