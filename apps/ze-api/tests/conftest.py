import importlib

import pytest

import ze_personal.contacts.tools  # noqa: F401 — registers get_contact_channels, set_contact_channel
import ze_browser.tool  # noqa: F401 — registers browser_extract
import ze_components.tools  # noqa: F401 — registers all render tools

# Ensure CalendarPlugin agent modules are imported so @agent decorators fire.
from ze_calendar.plugin import CalendarPlugin as _CalendarPlugin
for _path in _CalendarPlugin().agent_module_paths():
    importlib.import_module(_path)


def _registry_has_real_agents() -> bool:
    from ze_core.orchestration.registry import get_registered_agents

    agents = get_registered_agents()
    if "research" not in agents:
        return False
    if "calendar" not in agents:
        return False
    return not any(cls.__name__.startswith("GateConfig_") for cls in agents.values())


@pytest.fixture(autouse=True)
def _ensure_real_agent_registry():
    """Keep ze-core registry on real @agent classes, not capability test stubs."""
    from ze_api.bootstrap import reload_agent_modules

    if not _registry_has_real_agents():
        reload_agent_modules()
    yield
    if not _registry_has_real_agents():
        reload_agent_modules()
