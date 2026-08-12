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
        await conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {schema}.document_links (
                source_path TEXT NOT NULL REFERENCES {schema}.documents(source_path) ON DELETE CASCADE,
                target_path TEXT NOT NULL REFERENCES {schema}.documents(source_path) ON DELETE CASCADE,
                relation_type TEXT NOT NULL DEFAULT 'link',
                PRIMARY KEY (source_path, target_path)
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
    """Returns True if a document was actually deleted. document_links rows referencing this
    document (either direction) go with it via ON DELETE CASCADE."""
    schema = settings.schema_name
    async with pool.acquire() as conn:
        result = await conn.execute(f"DELETE FROM {schema}.documents WHERE source_path = $1", source_path)
    return result != "DELETE 0"


async def replace_links(pool: asyncpg.Pool, source_path: str, target_titles: list[str]) -> list[str]:
    """Resolves target_titles (case-insensitive) against existing document titles and replaces
    source_path's outgoing links with whatever resolved. A title that doesn't match any existing
    document is silently skipped, not an error -- same "unlinked mention" behavior Obsidian itself
    has (docs/adr/0008, D10). Returns the source_paths that were actually linked."""
    schema = settings.schema_name
    if not target_titles:
        target_titles = []
    async with pool.acquire() as conn:
        async with conn.transaction():
            resolved = await conn.fetch(
                f"""
                SELECT source_path FROM {schema}.documents
                WHERE lower(title) = ANY($1::text[]) AND source_path != $2
                """,
                [t.lower() for t in target_titles],
                source_path,
            )
            target_paths = [r["source_path"] for r in resolved]
            await conn.execute(f"DELETE FROM {schema}.document_links WHERE source_path = $1", source_path)
            if target_paths:
                await conn.executemany(
                    f"""
                    INSERT INTO {schema}.document_links (source_path, target_path)
                    VALUES ($1, $2) ON CONFLICT DO NOTHING
                    """,
                    [(source_path, target_path) for target_path in target_paths],
                )
    return target_paths


async def get_links(pool: asyncpg.Pool, source_path: str) -> list[dict]:
    """Documents source_path links to (outgoing)."""
    schema = settings.schema_name
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT d.source_path, d.title, l.relation_type
            FROM {schema}.document_links l
            JOIN {schema}.documents d ON d.source_path = l.target_path
            WHERE l.source_path = $1
            ORDER BY d.title
            """,
            source_path,
        )
    return [dict(r) for r in rows]


async def get_backlinks(pool: asyncpg.Pool, source_path: str) -> list[dict]:
    """Documents that link to source_path (incoming)."""
    schema = settings.schema_name
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT d.source_path, d.title, l.relation_type
            FROM {schema}.document_links l
            JOIN {schema}.documents d ON d.source_path = l.source_path
            WHERE l.target_path = $1
            ORDER BY d.title
            """,
            source_path,
        )
    return [dict(r) for r in rows]


async def get_all_links(pool: asyncpg.Pool) -> list[dict]:
    """Every edge, with both endpoints' titles -- backs the graph view and the vault export."""
    schema = settings.schema_name
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT l.source_path, l.target_path, l.relation_type,
                   ds.title AS source_title, dt.title AS target_title
            FROM {schema}.document_links l
            JOIN {schema}.documents ds ON ds.source_path = l.source_path
            JOIN {schema}.documents dt ON dt.source_path = l.target_path
            """
        )
    return [dict(r) for r in rows]
