from app import embeddings
from app.config import settings


def test_embed_one_returns_a_vector_of_the_configured_dimension():
    vector = embeddings.embed_one("app crashes exporting a large report")

    assert isinstance(vector, list)
    assert len(vector) == settings.embedding_dim
    assert all(isinstance(x, float) for x in vector)


def test_embed_many_returns_one_vector_per_input():
    vectors = embeddings.embed_many(["first document", "second document", "third document"])

    assert len(vectors) == 3
    assert all(len(v) == settings.embedding_dim for v in vectors)


def test_embed_many_empty_input_returns_empty_list():
    assert embeddings.embed_many([]) == []


def test_similar_text_embeds_closer_than_dissimilar_text():
    # Real semantic check, not just shape -- confirms the model is doing something meaningful,
    # the same property verified live against real Postgres in PROJECT_JOURNAL.md, Milestone 8.
    import math

    def cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        return dot / (norm_a * norm_b)

    base = embeddings.embed_one("The app crashes when exporting a report with many rows")
    similar = embeddings.embed_one("Exporting a large report causes the application to crash")
    unrelated = embeddings.embed_one("How do I enable two-factor authentication")

    assert cosine(base, similar) > cosine(base, unrelated)
