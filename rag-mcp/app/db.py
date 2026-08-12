"""Direct Postgres access via asyncpg -- the first service in this project to talk to Postgres
directly rather than through Chatwoot's API, since this schema has nothing to do with Chatwoot's
own Rails-managed tables. See docs/adr/0006, D1."""

from __future__ import annotations

import asyncpg
from pgvector import Vector
from pgvector.asyncpg import register_vector

from app.config import settings

_pool: asyncpg.Pool | None = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    # register_vector's schema kwarg is where the `vector` TYPE itself lives (Chatwoot's own
    # `CREATE EXTENSION vector` installed it into the default/public schema) -- not to be
    # confused with settings.schema_name, which is where *our* documents table lives.
    await register_vector(conn)


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=settings.postgres_host,
            port=settings.postgres_port,
            user=settings.postgres_username,
            password=settings.postgres_password,
            database=settings.postgres_database,
            init=_init_connection,
            min_size=1,
            max_size=5,
        )
    return _pool


async def ensure_schema(pool: asyncpg.Pool) -> None:
    schema = settings.schema_name
    async with pool.acquire() as conn:
        await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        await conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {schema}.documents (
                id SERIAL PRIMARY KEY,
                source_path TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding vector({settings.embedding_dim}) NOT NULL,
                indexed_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )


async def upsert_document(pool: asyncpg.Pool, source_path: str, title: str, content: str, embedding: list[float]) -> None:
    schema = settings.schema_name
    async with pool.acquire() as conn:
        await conn.execute(
            f"""
            INSERT INTO {schema}.documents (source_path, title, content, embedding)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (source_path) DO UPDATE
                SET title = $2, content = $3, embedding = $4, indexed_at = now()
            """,
            source_path,
            title,
            content,
            Vector(embedding),
        )


async def search(pool: asyncpg.Pool, query_embedding: list[float], top_k: int) -> list[dict]:
    schema = settings.schema_name
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT source_path, title, content, 1 - (embedding <=> $1) AS score
            FROM {schema}.documents
            ORDER BY embedding <=> $1
            LIMIT $2
            """,
            Vector(query_embedding),
            top_k,
        )
    return [dict(r) for r in rows]


async def count_documents(pool: asyncpg.Pool) -> int:
    schema = settings.schema_name
    async with pool.acquire() as conn:
        return await conn.fetchval(f"SELECT count(*) FROM {schema}.documents")


async def list_documents(pool: asyncpg.Pool) -> list[dict]:
    """All documents, newest-first -- used by the ingestion UI (docs/adr/0007)."""
    schema = settings.schema_name
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT source_path, title, content, indexed_at FROM {schema}.documents ORDER BY indexed_at DESC"
        )
    return [dict(r) for r in rows]


async def delete_document(pool: asyncpg.Pool, source_path: str) -> bool:
    """Returns True if a document was actually deleted."""
    schema = settings.schema_name
    async with pool.acquire() as conn:
        result = await conn.execute(f"DELETE FROM {schema}.documents WHERE source_path = $1", source_path)
    return result != "DELETE 0"
