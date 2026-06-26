from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ze_agents.errors import AgentConfigError
from ze_logging import get_logger

log = get_logger(__name__)

__all__ = [
    "CORE_RESERVED_NAV_PATHS",
    "UiContribution",
    "UiManifest",
    "collect_ui_contributions",
    "filter_ui_manifest_by_openapi",
]

CORE_RESERVED_NAV_PATHS = frozenset(
    {"goals", "costs", "settings"}
)


@dataclass(frozen=True)
class UiContribution:
    """Declarative shell contribution from a plugin."""

    id: str
    plugin: str
    kind: Literal["nav", "settings_section"]
    label: str
    icon: str
    path: str | None = None
    page_operation_id: str | None = None
    settings_operation_id: str | None = None
    priority: int = 100
    show_in_mobile_nav: bool = True


@dataclass(frozen=True)
class UiManifest:
    nav: tuple[UiContribution, ...]
    settings_sections: tuple[UiContribution, ...]


def collect_ui_contributions(plugins: list) -> UiManifest:
    """Merge plugin UI contributions; raise AgentConfigError on conflicts."""
    seen_ids: set[str] = set()
    seen_nav_paths: set[str] = set()
    nav: list[UiContribution] = []
    settings_sections: list[UiContribution] = []

    for plugin in plugins:
        plugin_name = type(plugin).__name__
        for contribution in plugin.ui_contributions():
            if contribution.id in seen_ids:
                raise AgentConfigError(
                    f"Duplicate UI contribution id {contribution.id!r} "
                    f"contributed by {plugin_name}"
                )
            seen_ids.add(contribution.id)

            if contribution.kind == "nav":
                if contribution.path is None:
                    raise AgentConfigError(
                        f"Nav contribution {contribution.id!r} from {plugin_name} "
                        "requires path"
                    )
                if contribution.path in CORE_RESERVED_NAV_PATHS:
                    raise AgentConfigError(
                        f"Nav path {contribution.path!r} from {contribution.id!r} "
                        f"conflicts with a core-owned route"
                    )
                if contribution.path in seen_nav_paths:
                    raise AgentConfigError(
                        f"Duplicate nav path {contribution.path!r} "
                        f"contributed by {plugin_name}"
                    )
                seen_nav_paths.add(contribution.path)
                nav.append(contribution)
            elif contribution.kind == "settings_section":
                settings_sections.append(contribution)

    def _sort_key(contribution: UiContribution) -> tuple[int, str, str]:
        return (contribution.priority, contribution.label, contribution.id)

    return UiManifest(
        nav=tuple(sorted(nav, key=_sort_key)),
        settings_sections=tuple(sorted(settings_sections, key=_sort_key)),
    )


def filter_ui_manifest_by_openapi(
    manifest: UiManifest,
    operation_ids: frozenset[str],
) -> UiManifest:
    """Drop manifest entries whose operation IDs are missing from OpenAPI."""

    def _valid_nav(item: UiContribution) -> bool:
        op = item.page_operation_id
        if op is None:
            log.warning(
                "ui_manifest_nav_missing_operation_id",
                contribution_id=item.id,
                plugin=item.plugin,
            )
            return False
        if op not in operation_ids:
            log.warning(
                "ui_manifest_unknown_operation_id",
                contribution_id=item.id,
                plugin=item.plugin,
                operation_id=op,
                kind="nav",
            )
            return False
        return True

    def _valid_settings(item: UiContribution) -> bool:
        op = item.settings_operation_id
        if op is None:
            log.warning(
                "ui_manifest_settings_missing_operation_id",
                contribution_id=item.id,
                plugin=item.plugin,
            )
            return False
        if op not in operation_ids:
            log.warning(
                "ui_manifest_unknown_operation_id",
                contribution_id=item.id,
                plugin=item.plugin,
                operation_id=op,
                kind="settings_section",
            )
            return False
        return True

    return UiManifest(
        nav=tuple(item for item in manifest.nav if _valid_nav(item)),
        settings_sections=tuple(
            item for item in manifest.settings_sections if _valid_settings(item)
        ),
    )