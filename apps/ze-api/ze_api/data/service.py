from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from itertools import groupby

from ze_agents.plugin import DataDomain
from ze_api.data.assembler import ExportAssembler, ImportAssembler
from ze_api.data.types import ImportResult
from ze_api.logging import get_logger

log = get_logger(__name__)

_TOKEN_TTL_MINUTES = 10


class SchemaMismatchError(Exception):
    def __init__(self, archive: list[str], current: list[str]) -> None:
        self.archive = archive
        self.current = current
        super().__init__(
            f"Archive schema revisions {sorted(archive)} do not match "
            f"current revisions {sorted(current)}. "
            "Ensure you are importing an archive created by the same Ze version."
        )


class InstanceNotEmptyError(Exception):
    pass


class DataPortabilityService:
    """Orchestrates data export, import, and hard-deletion across all registered domains."""

    def __init__(self, pool, domains: list[DataDomain]) -> None:
        self._pool = pool
        self._domains = domains
        self._export_assembler = ExportAssembler()
        self._import_assembler = ImportAssembler()
        self._pending_tokens: dict[str, datetime] = {}

    # ── Schema revisions ─────────────────────────────────────────────────────

    async def get_schema_revisions(self) -> list[str]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT version_num FROM alembic_version")
            return sorted(r["version_num"] for r in rows)

    # ── Export ────────────────────────────────────────────────────────────────

    async def export(self) -> bytes:
        results = await asyncio.gather(
            *[d.export(self._pool) for d in self._domains],
            return_exceptions=True,
        )
        domain_data: dict[str, list] = {}
        for domain, result in zip(self._domains, results):
            if isinstance(result, Exception):
                log.error("export_domain_failed", domain=domain.name, error=str(result))
                domain_data[domain.name] = []
            else:
                domain_data[domain.name] = result

        exported_at = datetime.now(timezone.utc)
        schema_revisions = await self.get_schema_revisions()
        log.info("export_assembled", domains=list(domain_data.keys()), revisions=schema_revisions)
        return self._export_assembler.build(domain_data, exported_at, schema_revisions)

    # ── Import ────────────────────────────────────────────────────────────────

    async def is_empty(self) -> bool:
        importable = [d for d in self._domains if d.importer is not None]
        results = await asyncio.gather(
            *[d.export(self._pool) for d in importable],
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, list) and result:
                return False
        return True

    async def import_archive(self, archive_bytes: bytes) -> ImportResult:
        manifest, domain_data = self._import_assembler.parse(archive_bytes)

        current_revisions = await self.get_schema_revisions()
        archive_revisions = sorted(manifest.get("schema_revisions", []))
        if archive_revisions != current_revisions:
            raise SchemaMismatchError(archive=archive_revisions, current=current_revisions)

        if not await self.is_empty():
            raise InstanceNotEmptyError(
                "Instance is not empty. Delete all data before importing."
            )

        importable = [d for d in self._domains if d.importer is not None]
        # Import parents before children: descending delete_order.
        ordered = sorted(importable, key=lambda d: d.delete_order, reverse=True)

        domains_imported: list[str] = []
        rows_imported: dict[str, int] = {}

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for domain in ordered:
                    rows = domain_data.get(domain.name, [])
                    if not rows:
                        continue
                    count = await domain.importer(conn, rows)
                    domains_imported.append(domain.name)
                    rows_imported[domain.name] = count
                    log.info("import_domain_done", domain=domain.name, rows=count)

        log.info("import_complete", domains=domains_imported)
        return ImportResult(domains_imported=domains_imported, rows_imported=rows_imported)

    # ── Delete ────────────────────────────────────────────────────────────────

    def create_delete_intent(self) -> tuple[str, datetime]:
        token = str(uuid.uuid4())
        expiry = datetime.now(timezone.utc) + timedelta(minutes=_TOKEN_TTL_MINUTES)
        self._pending_tokens[token] = expiry
        return token, expiry

    def consume_delete_intent(self, token: str) -> bool:
        expiry = self._pending_tokens.pop(token, None)
        if expiry is None:
            return False
        if datetime.now(timezone.utc) > expiry:
            return False
        return True

    async def delete(self) -> None:
        ordered = sorted(self._domains, key=lambda d: d.delete_order)
        for order_key, group in groupby(ordered, key=lambda d: d.delete_order):
            batch = list(group)
            await asyncio.gather(*[d.delete(self._pool) for d in batch])
            log.info("delete_batch_done", order=order_key, domains=[d.name for d in batch])
        log.info("data_deletion_complete")
