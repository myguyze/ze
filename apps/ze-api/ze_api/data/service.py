from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from itertools import groupby

from ze_agents.plugin import DataDomain
from ze_api.data.assembler import ExportAssembler
from ze_api.logging import get_logger

log = get_logger(__name__)

_TOKEN_TTL_MINUTES = 10


class DataPortabilityService:
    """Orchestrates data export and hard-deletion across all registered domains."""

    def __init__(self, pool, domains: list[DataDomain]) -> None:
        self._pool = pool
        self._domains = domains
        self._assembler = ExportAssembler()
        self._pending_tokens: dict[str, datetime] = {}

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
        log.info("export_assembled", domains=list(domain_data.keys()))
        return self._assembler.build(domain_data, exported_at)

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
