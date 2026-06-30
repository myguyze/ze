from __future__ import annotations

from typing import Any


def embedding_vector(embedder: Any, text: str) -> str:
    vec = embedder.encode(text)
    vals = vec.tolist() if hasattr(vec, "tolist") else list(vec)
    return "[" + ",".join(str(v) for v in vals) + "]"


async def delete_by_ids(conn: Any, table: str, ids: list) -> None:
    if not ids:
        return
    await conn.execute(f"DELETE FROM {table} WHERE id = ANY($1::uuid[])", ids)


async def delete_by_column_ids(conn: Any, table: str, column: str, ids: list) -> None:
    if not ids:
        return
    await conn.execute(f"DELETE FROM {table} WHERE {column} = ANY($1::uuid[])", ids)
