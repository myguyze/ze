from __future__ import annotations

from typing import Any

from ze_logging import get_logger
from ze_seed.context import SeedContext
from ze_seed.domain import SeedDomain

log = get_logger(__name__)


class DevDataSeeder:
    def __init__(self, domains: list[SeedDomain]) -> None:
        self._domains = domains

    async def apply(self, ctx: SeedContext, *, force: bool = True) -> dict[str, int]:
        if force:
            await self._clear_all(ctx)

        results: dict[str, int] = {}
        for domain in sorted(self._domains, key=lambda d: d.seed_order, reverse=True):
            try:
                count = await domain.apply(ctx)
                results[domain.name] = count
                log.info("seed_domain_applied", domain=domain.name, rows=count)
            except Exception as exc:
                log.error("seed_domain_failed", domain=domain.name, error=str(exc))
                raise

        log.info("seed_complete", domains=results)
        return results

    async def _clear_all(self, ctx: SeedContext) -> None:
        for domain in sorted(self._domains, key=lambda d: d.seed_order):
            try:
                await domain.clear(ctx)
                log.debug("seed_domain_cleared", domain=domain.name)
            except Exception as exc:
                log.error(
                    "seed_domain_clear_failed", domain=domain.name, error=str(exc)
                )
                raise


def collect_seed_domains(plugins: list[Any]) -> list[SeedDomain]:
    from ze_seed.domains.automation import automation_seed_domains
    from ze_seed.domains.engine import engine_seed_domains
    from ze_seed.domains.memory import memory_seed_domains

    plugin_domains = [d for plugin in plugins for d in plugin.seed_domains()]
    return (
        memory_seed_domains()
        + automation_seed_domains()
        + engine_seed_domains()
        + plugin_domains
    )
