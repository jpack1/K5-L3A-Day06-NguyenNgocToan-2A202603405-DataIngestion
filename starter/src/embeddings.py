"""OpenAI embedding adapter. Errors propagate: there is no mock fallback."""
from typing import Protocol

from openai import OpenAI


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...


class MyEmbedder:
    """OpenAI embeddings; documents and queries are embedded the same way (the model has no prefixes)."""

    BATCH = 100

    def __init__(self, model_name: str) -> None:
        if not model_name:
            raise ValueError("EMBEDDING_MODEL is empty in .env")
        self.model_name = model_name
        self.client = OpenAI()  # reads OPENAI_API_KEY; raises if missing
        self.total_tokens = 0
        self.dimensions = len(self.embed_query("dimension probe"))

    def _embed(self, texts: list[str]) -> list[list[float]]:
        resp = self.client.embeddings.create(model=self.model_name, input=texts)
        self.total_tokens += resp.usage.total_tokens
        return [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.BATCH):
            out += self._embed(texts[i:i + self.BATCH])
        return out

    def embed_query(self, question: str) -> list[float]:
        return self._embed([question])[0]
