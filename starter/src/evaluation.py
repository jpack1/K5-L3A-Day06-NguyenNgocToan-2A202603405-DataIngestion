"""Automatic evidence checks and per-query traces. Manual coherence/grounding labels are separate."""
from collections import defaultdict
from typing import Any


def collapse(s: str) -> str:
    """Whitespace-insensitive form used for evidence matching (same rule as validate_benchmark.py)."""
    return " ".join(s.split())


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    """A hit = chunk on a gold/alt page of the gold source that contains the whole quote."""
    golds = [(question["gold_page"], question["evidence_quote"])] + [
        (g["page"], g["quote"]) for g in question.get("alt_evidence", [])]
    flt = question.get("filter") or {}
    ranked = []
    for rank, h in enumerate(hits, start=1):
        on_gold_page = h["document_id"] == question["gold_source_id"] and any(h["page"] == p for p, _ in golds)
        is_hit = h["document_id"] == question["gold_source_id"] and any(
            h["page"] == p and collapse(q) in collapse(h["text"]) for p, q in golds)
        ranked.append({"rank": rank, "chunk_id": h["chunk_id"], "page": h["page"],
                       "printed_page": h["printed_page"], "chapter": h["chapter"], "sections": h["sections"],
                       "score": round(float(h["score"]), 4), "on_gold_page": on_gold_page,
                       "evidence_hit": is_hit,
                       "matches_filter": all(h.get(k) == v for k, v in flt.items()) if flt else None,
                       "text": h["text"]})
    return {
        "id": question["id"], "split": question["split"], "type": question["type"],
        "question": question["question"], "filter": question.get("filter"),
        "gold_page": question["gold_page"], "alt_pages": [g["page"] for g in question.get("alt_evidence", [])],
        "evidence_quote": question["evidence_quote"],
        "hit_at_1": bool(ranked and ranked[0]["evidence_hit"]),
        "hit_at_3": any(r["evidence_hit"] for r in ranked[:3]),
        "page_hit_at_3": any(r["on_gold_page"] for r in ranked[:3]),
        # Gold page retrieved but quote not inside one chunk: evidence split across chunks.
        "split_evidence": any(r["on_gold_page"] for r in ranked[:3]) and not any(r["evidence_hit"] for r in ranked[:3]),
        "filter_compliant": all(r["matches_filter"] for r in ranked) if question.get("filter") else None,
        "top_k": ranked,
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts (numerator/denominator) per strategy and split."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for t in traces:
        groups[(t["strategy"], t["split"])].append(t)
    out = {}
    for (strategy, split), ts in sorted(groups.items()):
        n = len(ts)
        filt = [t for t in ts if t["filter"]]
        out[f"{strategy}/{split}"] = {
            "n": n,
            "hit_at_1": sum(t["hit_at_1"] for t in ts),
            "hit_at_3": sum(t["hit_at_3"] for t in ts),
            "page_hit_at_3": sum(t["page_hit_at_3"] for t in ts),
            "split_evidence": sum(t["split_evidence"] for t in ts),
            "filter_questions": len(filt),
            "filter_hit_at_3": sum(t["hit_at_3"] for t in filt),
            # Compliance of the top-3 with the question's filter (meaningful for A/B too: they ignore it).
            "filter_compliant": sum(t["filter_compliant"] for t in filt) if filt else "N/A",
        }
    return out
