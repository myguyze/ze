from __future__ import annotations

from types import SimpleNamespace

from ze_api.api import app as app_module
from ze_api.settings import get_settings


class FakeContainer:
    plugins: list = []

    def __getattr__(self, name: str):
        return object()

    async def close(self) -> None:
        return None


async def test_lifespan_runs_auto_migrate_when_enabled(monkeypatch):
    calls: list[str] = []

    async def fake_build_container(settings):
        calls.append("build_container")
        return FakeContainer()

    def fake_upgrade(database_url: str) -> None:
        calls.append(f"upgrade:{database_url}")

    def fake_assert_schema_ready(database_url: str) -> None:
        calls.append(f"assert_schema_ready:{database_url}")

    get_settings.cache_clear()
    monkeypatch.setenv("AUTO_MIGRATE", "true")
    monkeypatch.setenv("DATABASE_URL_SYNC", "postgresql+psycopg2://test:test@localhost/test")
    monkeypatch.setattr(app_module, "build_container", fake_build_container)
    monkeypatch.setattr(app_module.ze_migrate, "upgrade", fake_upgrade)
    monkeypatch.setattr(app_module.ze_migrate, "assert_schema_ready", fake_assert_schema_ready)

    app = SimpleNamespace(state=SimpleNamespace())
    async with app_module.lifespan(app):
        pass

    assert calls == [
        "upgrade:postgresql+psycopg2://test:test@localhost/test",
        "assert_schema_ready:postgresql+psycopg2://test:test@localhost/test",
        "build_container",
    ]
    get_settings.cache_clear()


async def test_lifespan_checks_schema_when_auto_migrate_disabled(monkeypatch):
    calls: list[str] = []

    async def fake_build_container(settings):
        calls.append("build_container")
        return FakeContainer()

    def fake_assert_schema_ready(database_url: str) -> None:
        calls.append(f"assert_schema_ready:{database_url}")

    get_settings.cache_clear()
    monkeypatch.delenv("AUTO_MIGRATE", raising=False)
    monkeypatch.setenv("DATABASE_URL_SYNC", "postgresql+psycopg2://test:test@localhost/test")
    monkeypatch.setattr(app_module, "build_container", fake_build_container)
    monkeypatch.setattr(app_module.ze_migrate, "assert_schema_ready", fake_assert_schema_ready)

    app = SimpleNamespace(state=SimpleNamespace())
    async with app_module.lifespan(app):
        pass

    assert calls == [
        "assert_schema_ready:postgresql+psycopg2://test:test@localhost/test",
        "build_container",
    ]
    get_settings.cache_clear()
