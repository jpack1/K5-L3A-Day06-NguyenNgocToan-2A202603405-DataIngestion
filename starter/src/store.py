"""Store and search vectors using PostgreSQL + pgvector (exact cosine search, no ANN index)."""
import hashlib
from typing import Any

import psycopg

from .models import Chunk

# Only these columns may be used in filters; values are always bound as parameters.
FILTER_COLUMNS = {"document_id", "page", "chapter"}
_COLS = ("chunk_id, document_id, source, page, printed_page, chapter, chapter_title, sections, "
         "char_start, char_end, text")


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _vec(v: list[float]) -> str:
    return "[" + ",".join(map(str, v)) + "]"


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.url = database_url
        self.dimensions = dimensions

    def _connect(self):
        return psycopg.connect(self.url, connect_timeout=5)

    def create_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS chunks (
                    strategy      text    NOT NULL,
                    chunk_id      text    NOT NULL,
                    document_id   text    NOT NULL,
                    source        text    NOT NULL,
                    page          int     NOT NULL,
                    printed_page  int,
                    chapter       int,
                    chapter_title text,
                    sections      text[],
                    char_start    int,
                    char_end      int,
                    text          text    NOT NULL,
                    text_hash     text    NOT NULL,
                    model         text    NOT NULL,
                    embedding     vector({self.dimensions}) NOT NULL,
                    PRIMARY KEY (strategy, chunk_id)
                )""")
            row = conn.execute(
                "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
                "WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'").fetchone()
            if row[0] != f"vector({self.dimensions})":
                raise RuntimeError(f"existing table has {row[0]}, model needs vector({self.dimensions}); "
                                   "drop the chunks table to switch models")

    def existing_hashes(self, strategy: str, model: str) -> dict[str, str]:
        """chunk_id -> text_hash already stored for this strategy and model (used to skip re-embedding)."""
        with self._connect() as conn:
            rows = conn.execute("SELECT chunk_id, text_hash FROM chunks WHERE strategy = %s AND model = %s",
                                (strategy, model)).fetchall()
        return dict(rows)

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]], model: str,
               keep_ids: set[str]) -> int:
        """Insert/update `chunks`, then delete rows of the same documents whose id is not in `keep_ids`.

        `keep_ids` is the full current chunk set, so obsolete chunks from a changed document are removed.
        Returns the number of deleted rows.
        """
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors differ in length")
        if any(len(v) != self.dimensions for v in vectors):
            raise ValueError("vector dimension mismatch")
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.executemany(f"""
                    INSERT INTO chunks (strategy, {_COLS}, text_hash, model, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
                    ON CONFLICT (strategy, chunk_id) DO UPDATE SET
                        text = EXCLUDED.text, text_hash = EXCLUDED.text_hash, model = EXCLUDED.model,
                        embedding = EXCLUDED.embedding, page = EXCLUDED.page,
                        printed_page = EXCLUDED.printed_page, chapter = EXCLUDED.chapter,
                        chapter_title = EXCLUDED.chapter_title, sections = EXCLUDED.sections,
                        char_start = EXCLUDED.char_start, char_end = EXCLUDED.char_end""",
                    [(strategy, c.chunk_id, c.document_id, c.source, c.page, c.metadata.get("printed_page"),
                      c.metadata.get("chapter"), c.metadata.get("chapter_title"), c.metadata.get("sections"),
                      c.metadata.get("char_start"), c.metadata.get("char_end"), c.text, text_hash(c.text),
                      model, _vec(v)) for c, v in zip(chunks, vectors)])
                docs = sorted({cid.split(":p")[0] for cid in keep_ids})
                cur.execute("DELETE FROM chunks WHERE strategy = %s AND document_id = ANY(%s) "
                            "AND NOT (chunk_id = ANY(%s))", (strategy, docs, list(keep_ids)))
                return cur.rowcount

    def count(self, strategy: str) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT count(*) FROM chunks WHERE strategy = %s", (strategy,)).fetchone()[0]

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Filter in SQL, rank by cosine distance; score = cosine similarity."""
        where, params = ["strategy = %s"], [strategy]
        for key, value in (filters or {}).items():
            if key not in FILTER_COLUMNS:
                raise ValueError(f"filter on {key!r} not allowed")
            where.append(f"{key} = %s")
            params.append(value)
        q = _vec(query_vector)
        with self._connect() as conn:
            cur = conn.execute(
                f"SELECT {_COLS}, 1 - (embedding <=> %s::vector) AS score FROM chunks "
                f"WHERE {' AND '.join(where)} ORDER BY embedding <=> %s::vector LIMIT %s",
                [q, *params, q, top_k])
            names = [d.name for d in cur.description]
            return [dict(zip(names, row)) for row in cur.fetchall()]
