import pytest

from ze_core.errors import AgentConfigError, UnknownToolError
from ze_core.orchestration.tool import (
    ToolAccess,
    ToolSpec,
    clear_tool_registry,
    get_tool,
    registered_tools,
    tool,
)


@pytest.fixture(autouse=True)
def clean_tools():
    clear_tool_registry()
    yield
    clear_tool_registry()


class TestToolDecorator:
    def test_registers_async_function(self):
        @tool(access=ToolAccess.READ, description="A search tool")
        async def web_search(query: str) -> str:
            return "result"

        assert "web_search" in registered_tools()
        spec = get_tool("web_search")
        assert spec.description == "A search tool"
        assert spec.access == ToolAccess.READ

    def test_accepts_string_access(self):
        @tool(access="write", description="write tool")
        async def my_write(text: str) -> str:
            return text

        assert get_tool("my_write").access == ToolAccess.WRITE

    def test_raises_for_sync_function(self):
        with pytest.raises(TypeError, match="async"):

            @tool(access=ToolAccess.READ, description="sync")
            def sync_tool(q: str) -> str:
                return "result"

    def test_raises_on_duplicate_name(self):
        @tool(access=ToolAccess.READ, description="first")
        async def dup_tool(q: str) -> str: ...

        with pytest.raises(AgentConfigError, match="Duplicate"):

            @tool(access=ToolAccess.READ, description="second")
            async def dup_tool(q: str) -> str: ...  # noqa: F811

    async def test_returns_original_function(self):
        @tool(access=ToolAccess.READ, description="passthrough")
        async def passthrough(q: str) -> str:
            return q

        result = await passthrough("hello")
        assert result == "hello"


class TestGetTool:
    def test_raises_unknown_tool_error(self):
        with pytest.raises(UnknownToolError, match="nonexistent"):
            get_tool("nonexistent")

    def test_returns_correct_spec(self):
        @tool(access=ToolAccess.WRITE, description="desc")
        async def special_tool(x: int) -> str: ...

        spec = get_tool("special_tool")
        assert isinstance(spec, ToolSpec)
        assert spec.name == "special_tool"


class TestRegisteredTools:
    def test_empty_after_clear(self):
        assert registered_tools() == {}

    def test_contains_registered_tools(self):
        @tool(access=ToolAccess.READ, description="t1")
        async def tool_a(q: str) -> str: ...

        @tool(access=ToolAccess.READ, description="t2")
        async def tool_b(q: str) -> str: ...

        tools = registered_tools()
        assert "tool_a" in tools
        assert "tool_b" in tools

    def test_returns_copy(self):
        result = registered_tools()
        result["injected"] = None  # type: ignore
        assert "injected" not in registered_tools()


class TestToolSpecLlmSchema:
    def test_includes_primitive_params(self):
        @tool(access=ToolAccess.READ, description="schema test")
        async def schema_tool(query: str, count: int, active: bool, ratio: float) -> str: ...

        schema = get_tool("schema_tool").llm_schema()
        props = schema["parameters"]["properties"]
        assert props["query"] == {"type": "string"}
        assert props["count"] == {"type": "integer"}
        assert props["active"] == {"type": "boolean"}
        assert props["ratio"] == {"type": "number"}

    def test_excludes_non_primitive_params(self):
        class _InternalClient:
            pass

        @tool(access=ToolAccess.READ, description="exclude test")
        async def mixed_tool(query: str, client: _InternalClient) -> str: ...

        schema = get_tool("mixed_tool").llm_schema()
        props = schema["parameters"]["properties"]
        assert "query" in props
        assert "client" not in props

    def test_required_list_excludes_optional_params(self):
        @tool(access=ToolAccess.READ, description="optional test")
        async def optional_tool(query: str, limit: int = 10) -> str: ...

        schema = get_tool("optional_tool").llm_schema()
        assert "query" in schema["parameters"]["required"]
        assert "limit" not in schema["parameters"]["required"]

    def test_schema_name_and_description(self):
        @tool(access=ToolAccess.WRITE, description="send an email")
        async def send_email(to: str, body: str) -> str: ...

        schema = get_tool("send_email").llm_schema()
        assert schema["name"] == "send_email"
        assert schema["description"] == "send an email"

    def test_schema_parameters_type_is_object(self):
        @tool(access=ToolAccess.READ, description="t")
        async def obj_tool(q: str) -> str: ...

        schema = get_tool("obj_tool").llm_schema()
        assert schema["parameters"]["type"] == "object"
