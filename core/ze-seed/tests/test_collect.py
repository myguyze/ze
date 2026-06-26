from __future__ import annotations

from ze_seed.service import collect_seed_domains
from ze_seed.domains.memory import memory_seed_domains
from ze_seed.domains.automation import automation_seed_domains
from ze_seed.domains.engine import engine_seed_domains


class _PluginStub:
    def seed_domains(self):
        return []


def test_collect_seed_domains_includes_core_domains():
    domains = collect_seed_domains([_PluginStub()])
    names = {d.name for d in domains}
    assert "memory.dev" in names
    assert "automation.dev" in names
    assert "engine.dev" in names


def test_core_domain_names_unique():
    domains = memory_seed_domains() + automation_seed_domains() + engine_seed_domains()
    names = [d.name for d in domains]
    assert len(names) == len(set(names))
