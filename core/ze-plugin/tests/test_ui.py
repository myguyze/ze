from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ze_agents.errors import AgentConfigError
from ze_plugin.ui import (
    UiContribution,
    collect_ui_contributions,
    filter_ui_manifest_by_openapi,
)


def _nav(
    *,
    id: str = "ze_news.overview",
    path: str = "finance",
    priority: int = 100,
) -> UiContribution:
    return UiContribution(
        id=id,
        plugin="ze_news",
        kind="nav",
        label="Finance",
        icon="newspaper",
        path=path,
        page_operation_id="getFinancePage",
        priority=priority,
    )


def _settings(*, id: str = "ze_news.settings") -> UiContribution:
    return UiContribution(
        id=id,
        plugin="ze_news",
        kind="settings_section",
        label="News",
        icon="newspaper",
        settings_operation_id="getNewsSettings",
    )


def _plugin(*contributions: UiContribution):
    plugin = MagicMock()
    plugin.ui_contributions.return_value = list(contributions)
    return plugin


def test_empty_plugins_returns_empty_manifest():
    manifest = collect_ui_contributions([_plugin(), _plugin()])
    assert manifest.nav == ()
    assert manifest.settings_sections == ()


def test_collects_nav_and_settings():
    manifest = collect_ui_contributions([_plugin(_nav(), _settings())])
    assert len(manifest.nav) == 1
    assert manifest.nav[0].path == "finance"
    assert len(manifest.settings_sections) == 1


def test_duplicate_id_raises():
    with pytest.raises(AgentConfigError, match="ze_news.overview"):
        collect_ui_contributions([_plugin(_nav(), _nav(id="ze_news.overview"))])


def test_duplicate_nav_path_raises():
    with pytest.raises(AgentConfigError, match="finance"):
        collect_ui_contributions(
            [
                _plugin(_nav(id="a", path="finance")),
                _plugin(_nav(id="b", path="finance")),
            ]
        )


def test_core_reserved_nav_path_raises():
    with pytest.raises(AgentConfigError, match="goals"):
        collect_ui_contributions([_plugin(_nav(path="goals"))])


def test_nav_without_path_raises():
    contribution = UiContribution(
        id="ze_bad.nav",
        plugin="ze_bad",
        kind="nav",
        label="Bad",
        icon="circle",
        path=None,
    )
    with pytest.raises(AgentConfigError, match="requires path"):
        collect_ui_contributions([_plugin(contribution)])


def test_orders_by_priority_then_label():
    manifest = collect_ui_contributions(
        [
            _plugin(
                _nav(id="b", path="beta", priority=20),
                _nav(id="a", path="alpha", priority=10),
            )
        ]
    )
    assert [item.path for item in manifest.nav] == ["alpha", "beta"]


def test_filter_ui_manifest_keeps_valid_entries():
    manifest = collect_ui_contributions([_plugin(_nav(), _settings())])
    operation_ids = frozenset({"getFinancePage", "getNewsSettings"})

    filtered = filter_ui_manifest_by_openapi(manifest, operation_ids)

    assert len(filtered.nav) == 1
    assert len(filtered.settings_sections) == 1


def test_filter_ui_manifest_drops_unknown_nav_operation_id():
    manifest = collect_ui_contributions([_plugin(_nav())])
    filtered = filter_ui_manifest_by_openapi(manifest, frozenset())

    assert filtered.nav == ()


def test_filter_ui_manifest_drops_unknown_settings_operation_id():
    manifest = collect_ui_contributions([_plugin(_settings())])
    filtered = filter_ui_manifest_by_openapi(manifest, frozenset())

    assert filtered.settings_sections == ()


def test_filter_ui_manifest_drops_nav_without_page_operation_id():
    contribution = UiContribution(
        id="ze_bad.nav",
        plugin="ze_bad",
        kind="nav",
        label="Bad",
        icon="circle",
        path="bad",
    )
    manifest = collect_ui_contributions([_plugin(contribution)])
    filtered = filter_ui_manifest_by_openapi(manifest, frozenset({"getAnything"}))

    assert filtered.nav == ()
