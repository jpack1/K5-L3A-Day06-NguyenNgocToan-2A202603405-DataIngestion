"""Check benchmark/questions.jsonl against data/pages.jsonl before any retrieval run.

Run from starter/:  python scripts/validate_benchmark.py
"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def collapse(s: str) -> str:
    # Evidence matching ignores whitespace/line wraps; the same rule is used in evaluation.
    return " ".join(s.split())


def main() -> None:
    pages = {}
    for line in open(ROOT / "data" / "pages.jsonl", encoding="utf-8"):
        p = json.loads(line)
        pages[(p["document_id"], p["page"])] = p
    qs = [json.loads(l) for l in open(ROOT / "benchmark" / "questions.jsonl", encoding="utf-8") if l.strip()]

    errors = []
    ids = Counter(q["id"] for q in qs)
    errors += [f"duplicate id {i}" for i, n in ids.items() if n > 1]
    for q in qs:
        golds = [{"page": q["gold_page"], "quote": q["evidence_quote"]}] + q.get("alt_evidence", [])
        for g in golds:
            page = pages.get((q["gold_source_id"], g["page"]))
            if page is None:
                errors.append(f"{q['id']}: page {g['page']} not in corpus")
            elif collapse(g["quote"]) not in collapse(page["text"]):
                errors.append(f"{q['id']}: evidence not found on page {g['page']}")
            elif q.get("filter") and any(page.get(k) != v for k, v in q["filter"].items()):
                errors.append(f"{q['id']}: gold page {g['page']} violates its own filter {q['filter']}")
        if q.get("filter"):
            for k, v in q["filter"].items():
                if v not in {p.get(k) for p in pages.values()}:
                    errors.append(f"{q['id']}: filter value {k}={v} does not exist in corpus")
        if q["split"] not in ("dev", "test"):
            errors.append(f"{q['id']}: bad split {q['split']}")

    split = Counter(q["split"] for q in qs)
    filt = Counter(q["split"] for q in qs if q.get("filter"))
    if split["dev"] < 15 or split["test"] < 5:
        errors.append(f"need >=15 dev / >=5 test, got {dict(split)}")
    if sum(filt.values()) < 3 or filt["test"] < 1:
        errors.append(f"need >=3 filter questions with >=1 in test, got {dict(filt)}")

    print(f"questions: {len(qs)}  split: {dict(split)}  filter: {dict(filt)}  "
          f"types: {dict(Counter(q['type'] for q in qs))}")
    if errors:
        raise SystemExit("INVALID:\n" + "\n".join(errors))
    print("Benchmark OK")


if __name__ == "__main__":
    main()
