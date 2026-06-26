from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ze_agents.errors import AgentConfigError

__all__ = [
    "CORE_RESERVED_NAV_PATHS",
    "UiContribution",
    "UiManifest",
    "collect_ui_contributions",
]

CORE_RESERVED_NAV_PATHS = frozenset(
    {"goals", "reminders", "costs", "settings"}
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