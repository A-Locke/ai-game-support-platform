"""Local, zero-cost embeddings via fastembed (ONNX Runtime, not full PyTorch) -- see
docs/adr/0006, D2. The model is baked into the Docker image at build time (D4), so this only
ever loads from the local cache at runtime, no Hugging Face Hub dependency in production."""

from __future__ import annotations

from functools import lru_cache

from fastembed import TextEmbedding

from app.config import settings


@lru_cache
def _model() -> TextEmbedding:
    return TextEmbedding(model_name=settings.embedding_model)


def embed_one(text: str) -> list[float]:
    [vector] = list(_model().embed([text]))
    return vector.tolist()


def embed_many(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return [v.tolist() for v in _model().embed(texts)]
