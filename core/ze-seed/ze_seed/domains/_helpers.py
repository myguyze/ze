from __future__ import annotations

from typing import Any


def embedding_list(embedder: Any, text: str) -> list[float]:
    vec = embedder.encode(text)
    if hasattr(vec, "tolist"):
        return vec.tolist()
    return list(vec)


async def delete_by_ids(conn: Any, table: str, ids: list) -> None:
    if not ids:
        return
    await conn.execute(f"DELETE FROM {table} WHERE id = ANY($1::uuid[])", ids)


async def delete_by_column_ids(conn: Any, table: str, column: str, ids: list) -> None:
    if not ids:
        return
    await conn.execute(f"DELETE FROM {table} WHERE {column} = ANY($1::uuid[])", ids)
