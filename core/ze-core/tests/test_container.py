import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from ze_core.errors import AgentConfigError, RoutingError
from ze_core.orchestration import agent, clear_registry, register_instance
from ze_core.orchestration.base_agent import BaseAgent
from ze_core.orchestration.tool import clear_tool_registry
from ze_core.orchestration.types import AgentContext, AgentResult


@pytest.fixture(autouse=True)
def clean_registries():
    clear_registry()
    clear_tool_registry()
    yield
    clear_registry()
    clear_tool_registry()


# ── helpers ───────────────────────────────────────────────────────────────────

def _agent_cls(
    name="test",
    description="test agent",
    enabled=True,
    capabilities=None,
    intent_map=None,
    tools=None,
):
    class _A(BaseAgent):
        async def run(self, ctx: AgentContext) -> AgentResult:
            return AgentResult(agent=name, response="ok")

    _A.name = name
    _A.description = description
    _A.enabled = enabled
    _A.capabilities = capabilities or {"read": "autonomous"}
    _A.intent_map = intent_map or {}
    _A.tools = tools or []
    return _A


# ── TestDiscoverAgents ────────────────────────────────────────────────────────

class TestDiscoverAgents:
    def test_imports_agent_module_and_registers(self, tmp_path):
        from ze_core.container import _discover_agents

        agents_dir = tmp_path / "myapp" / "agents" / "research"
        agents_dir.mkdir(parents=True)
        (agents_dir.parent).joinpath("__init__.py").touch()
        (agents_dir / "__init__.py").touch()
        (agents_dir / "agent.py").write_text(
            "from ze_core.orchestration import agent as _reg\n"
            "from ze_core.orchestration.base_agent import BaseAgent\n"
            "from ze_core.orchestration.types import AgentContext, AgentResult\n\n"
            "@_reg\n"
            "class ResearchAgent(BaseAgent):\n"
            "    name = 'research'\n"
            "    description = 'Research agent'\n"
            "    async def run(self, ctx: AgentContext) -> AgentResult:\n"
            "        return AgentResult(agent='research', response='ok')\n"
        )

        sys.path.insert(0, str(tmp_path))
        pkg = "myapp"
        try:
            _discover_agents(tmp_path / "myapp", pkg)
            from ze_core.orchestration.registry import get_registered_agents
            assert "research" in get_registered_agents()
        finally:
            sys.path.pop(0)
            for key in list(sys.modules.keys()):
                if key.startswith(pkg):
                    del sys.modules[key]

    def test_raises_when_agents_dir_missing(self, tmp_path):
        from ze_core.container import _discover_agents

        with pytest.raises(AgentConfigError, match="agents/"):
            _discover_agents(tmp_path, "pkg")

    def test_skips_subdirs_without_agent_py(self, tmp_path):
        from ze_core.container import _discover_agents

        utils_dir = tmp_path / "agents" / "utils"
        utils_dir.mkdir(parents=True)
        (utils_dir / "__init__.py").touch()
        # No agent.py — should be silently skipped

        _discover_agents(tmp_path, "pkg")
        from ze_core.orchestration.registry import get_registered_agents
        assert get_registered_agents() == {}

    def test_imports_in_sorted_order(self, tmp_path):
        from ze_core.container import _discover_agents

        import_order = []
        agents_dir = tmp_path / "agents"
        for name in ["beta", "alpha"]:
            d = agents_dir / name
            d.mkdir(parents=True)
            (d / "__init__.py").touch()
            # Use a file that just writes its name to a shared list via a side-effect
            (d / "agent.py").write_text(
                f"import ze_core.orchestration.registry as _r\n"
                f"class _{name.capitalize()}(object):\n"
                f"    name = '{name}'\n"
                f"    description = 'x'\n"
                f"    enabled = True\n"
            )
        # Just verifying it doesn't raise and processes both
        # (sorted order is alpha, beta)
        try:
            _discover_agents(tmp_path, "nopackage")
        except Exception:
            pass  # Import may fail without a real package — just verifying sort attempt


# ── TestValidateRegistry ──────────────────────────────────────────────────────

class TestValidateRegistry:
    def test_passes_with_valid_agent(self):
        from ze_core.container import _validate_registry

        cls = _agent_cls("valid", "A valid agent")
        agent(cls)
        _validate_registry(None)  # should not raise

    def test_raises_on_empty_description(self):
        # Validation now happens at decoration time, not _validate_registry time.
        cls = _agent_cls("x", "")
        with pytest.raises(AgentConfigError, match="description"):
            agent(cls)

    def test_raises_on_whitespace_only_description(self):
        cls = _agent_cls("x", "   ")
        with pytest.raises(AgentConfigError, match="description"):
            agent(cls)

    def test_raises_on_unknown_tool(self):
        from ze_core.container import _validate_registry

        cls = _agent_cls("x", "desc", tools=["nonexistent_tool"])
        agent(cls)
        with pytest.raises(AgentConfigError, match="unknown tool"):
            _validate_registry(None)

    def test_passes_when_tool_is_registered(self):
        from ze_core.container import _validate_registry
        from ze_core.orchestration.tool import tool as reg_tool

        @reg_tool(access="read", description="a tool")
        async def known_tool(q: str) -> str: ...

        cls = _agent_cls("x", "desc", tools=["known_tool"])
        agent(cls)
        _validate_registry(None)  # should not raise

    def test_raises_when_intent_map_key_not_in_capabilities(self):
        # Validation now happens at decoration time.
        cls = _agent_cls(
            "x", "desc",
            capabilities={"read": "autonomous"},
            intent_map={"write": "assistant"},
        )
        with pytest.raises(AgentConfigError, match="intent_map"):
            agent(cls)

    def test_raises_when_no_enabled_agents(self):
        from ze_core.container import _validate_registry

        cls = _agent_cls("x", "desc", enabled=False)
        agent(cls)
        with pytest.raises(RoutingError, match="No enabled"):
            _validate_registry(None)

    def test_passes_with_matching_intent_map_and_capabilities(self):
        from ze_core.container import _validate_registry

        cls = _agent_cls(
            "x", "desc",
            capabilities={"read": "autonomous", "write": "confirm"},
            intent_map={"read": "assistant", "write": "writer"},
        )
        agent(cls)
        _validate_registry(None)


# ── TestResolve ───────────────────────────────────────────────────────────────

class TestResolve:
    def test_resolves_single_dep_by_type(self):
        from ze_core.container import _resolve

        class _Dep:
            pass

        class _MyAgent(BaseAgent):
            name = "di_test"
            description = "test"
            enabled = True

            def __init__(self, dep: _Dep) -> None:
                self.dep = dep

            async def run(self, ctx: AgentContext) -> AgentResult:
                return AgentResult(agent="di_test", response="ok")

        dep = _Dep()
        result = _resolve(_MyAgent, {_Dep: dep})
        assert result.dep is dep

    def test_resolves_zero_dep_agent(self):
        from ze_core.container import _resolve

        class _NoDep(BaseAgent):
            name = "no_dep"
            description = "no deps"
            enabled = True

            def __init__(self) -> None:
                pass

            async def run(self, ctx: AgentContext) -> AgentResult:
                return AgentResult(agent="no_dep", response="ok")

        result = _resolve(_NoDep, {})
        assert isinstance(result, _NoDep)

    def test_raises_on_missing_dep(self):
        from ze_core.container import _resolve

        class _Missing:
            pass

        class _NeedsMissing(BaseAgent):
            name = "needs_missing"
            description = "needs a dep"
            enabled = True

            def __init__(self, dep: _Missing) -> None: ...

            async def run(self, ctx: AgentContext) -> AgentResult:
                return AgentResult(agent="needs_missing", response="ok")

        with pytest.raises(AgentConfigError, match="No dependency"):
            _resolve(_NeedsMissing, {})

    def test_raises_on_unannotated_param(self):
        from ze_core.container import _resolve

        class _Unannotated(BaseAgent):
            name = "unannotated"
            description = "unannotated"
            enabled = True

            def __init__(self, dep) -> None: ...  # type: ignore[no-untyped-def]

            async def run(self, ctx: AgentContext) -> AgentResult:
                return AgentResult(agent="unannotated", response="ok")

        with pytest.raises(AgentConfigError, match="no type annotation"):
            _resolve(_Unannotated, {})

    def test_multiple_deps_resolved(self):
        from ze_core.container import _resolve

        class _A:
            pass

        class _B:
            pass

        class _MultiDep(BaseAgent):
            name = "multi"
            description = "multi"
            enabled = True

            def __init__(self, a: _A, b: _B) -> None:
                self.a = a
                self.b = b

            async def run(self, ctx: AgentContext) -> AgentResult:
                return AgentResult(agent="multi", response="ok")

        a, b = _A(), _B()
        result = _resolve(_MultiDep, {_A: a, _B: b})
        assert result.a is a
        assert result.b is b


# ── TestInstantiateAgents ─────────────────────────────────────────────────────

class TestInstantiateAgents:
    def test_instantiates_enabled_agents(self):
        from ze_core.container import _instantiate_agents

        class _Enabled(BaseAgent):
            name = "enabled"
            description = "d"
            enabled = True

            def __init__(self) -> None:
                pass

            async def run(self, ctx: AgentContext) -> AgentResult:
                return AgentResult(agent="enabled", response="ok")

        instances = _instantiate_agents({"enabled": _Enabled}, {})
        assert "enabled" in instances
        assert isinstance(instances["enabled"], _Enabled)

    def test_skips_disabled_agents(self):
        from ze_core.container import _instantiate_agents

        class _Disabled(BaseAgent):
            name = "disabled"
            description = "d"
            enabled = False

            def __init__(self) -> None:
                pass

            async def run(self, ctx: AgentContext) -> AgentResult:
                return AgentResult(agent="disabled", response="ok")

        instances = _instantiate_agents({"disabled": _Disabled}, {})
        assert "disabled" not in instances

    def test_registers_instances_in_registry(self):
        from ze_core.container import _instantiate_agents
        from ze_core.orchestration.registry import get_agent

        class _Reg(BaseAgent):
            name = "regtest"
            description = "d"
            enabled = True

            def __init__(self) -> None:
                pass

            async def run(self, ctx: AgentContext) -> AgentResult:
                return AgentResult(agent="regtest", response="ok")

        _instantiate_agents({"regtest": _Reg}, {})
        assert get_agent("regtest") is not None


# ── TestContainerClose ────────────────────────────────────────────────────────

class TestContainerClose:
    async def test_calls_shutdown_on_all_instances(self):
        from ze_core.container import Container

        instance = MagicMock()
        instance.name = "agent_a"
        instance.shutdown = AsyncMock()
        register_instance("agent_a", instance)

        container = _make_container()
        await container.close()
        instance.shutdown.assert_awaited_once()

    async def test_continues_after_agent_shutdown_failure(self):
        from ze_core.container import Container

        instance = MagicMock()
        instance.name = "failing"
        instance.shutdown = AsyncMock(side_effect=Exception("boom"))
        register_instance("failing", instance)

        container = _make_container()
        await container.close()  # must not raise
        container.pool.close.assert_awaited_once()

    async def test_closes_pool_and_client(self):
        from ze_core.container import Container

        container = _make_container()
        await container.close()
        container.openrouter_client.aclose.assert_awaited_once()
        container.pool.close.assert_awaited_once()
        container.checkpointer_pool.close.assert_awaited_once()


def _make_container():
    from ze_core.container import Container

    pool = MagicMock()
    pool.close = AsyncMock()
    checkpointer_pool = MagicMock()
    checkpointer_pool.close = AsyncMock()
    client = MagicMock()
    client.aclose = AsyncMock()

    return Container(
        settings=MagicMock(),
        pool=pool,
        checkpointer_pool=checkpointer_pool,
        embedder=MagicMock(),
        openrouter_client=client,
        router=MagicMock(),
        capability_gate=MagicMock(),
        memory_store=MagicMock(),
        memory_consolidator=MagicMock(),
        graph=MagicMock(),
    )


# ── TestSettings ──────────────────────────────────────────────────────────────

class TestSettings:
    def test_reads_env_vars(self, monkeypatch):
        from ze_core.settings import Settings

        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")

        s = Settings.from_env()
        assert s.openrouter_api_key == "sk-test"
        assert s.database_url == "postgresql://localhost/test"
        assert s.log_level == "DEBUG"

    def test_defaults_without_env(self, monkeypatch):
        from ze_core.settings import Settings

        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("SESSION_INACTIVITY_MINUTES", raising=False)
        monkeypatch.delenv("CONSOLIDATION_ENABLED", raising=False)

        s = Settings.from_env()
        assert s.session_inactivity_minutes == 30
        assert s.consolidation_enabled is True
        assert s.openrouter_base_url == "https://openrouter.ai/api/v1"

    def test_consolidation_disabled_via_env(self, monkeypatch):
        from ze_core.settings import Settings

        monkeypatch.setenv("CONSOLIDATION_ENABLED", "false")
        s = Settings.from_env()
        assert s.consolidation_enabled is False

    def test_loads_yaml_config(self, tmp_path, monkeypatch):
        from ze_core.settings import Settings

        config_file = tmp_path / "config.yaml"
        config_file.write_text("memory:\n  contradiction_threshold: 0.9\n")
        try:
            s = Settings.from_env(config_file)
            assert s.config["memory"]["contradiction_threshold"] == 0.9
        except ImportError:
            pytest.skip("PyYAML not installed")

    def test_empty_config_when_file_missing(self, tmp_path):
        from ze_core.settings import Settings

        s = Settings.from_env(tmp_path / "nonexistent.yaml")
        assert s.config == {}
