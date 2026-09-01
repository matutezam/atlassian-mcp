from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from mcp_atlassian.progressive import server as progressive_server_module
from mcp_atlassian.progressive.server import (
    _extract_lifespan_context,
    _get_app_context,
    progressive_mcp,
)
from mcp_atlassian.servers.context import MainAppContext


def test_extract_lifespan_context_prefers_direct_context():
    app_ctx = MainAppContext(full_jira_config=object())
    ctx = SimpleNamespace(
        lifespan_context={"app_lifespan_context": app_ctx},
        request_context=SimpleNamespace(
            lifespan_context={"app_lifespan_context": None}
        ),
    )

    lifespan_ctx = _extract_lifespan_context(ctx)  # type: ignore[arg-type]

    assert lifespan_ctx == {"app_lifespan_context": app_ctx}


def test_extract_lifespan_context_supports_request_context():
    app_ctx = MainAppContext(full_jira_config=object())
    ctx = SimpleNamespace(
        request_context=SimpleNamespace(
            lifespan_context={"app_lifespan_context": app_ctx}
        )
    )

    lifespan_ctx = _extract_lifespan_context(ctx)  # type: ignore[arg-type]

    assert lifespan_ctx == {"app_lifespan_context": app_ctx}


@pytest.mark.anyio
async def test_get_app_context_supports_request_context():
    app_ctx = MainAppContext(full_confluence_config=object())
    ctx = SimpleNamespace(
        request_context=SimpleNamespace(
            lifespan_context={"app_lifespan_context": app_ctx}
        )
    )

    result = await _get_app_context(ctx)  # type: ignore[arg-type]

    assert result is app_ctx


@pytest.mark.anyio
async def test_progressive_list_tools_uses_fastmcp_list_tools(monkeypatch):
    app_ctx = MainAppContext(full_jira_config=object())
    fake_tool = SimpleNamespace(
        name="jira_discover",
        to_mcp_tool=lambda *, name: SimpleNamespace(name=name),
    )
    list_tools = AsyncMock(return_value=[fake_tool])
    monkeypatch.setattr(progressive_mcp, "list_tools", list_tools)
    monkeypatch.setattr(
        progressive_mcp,
        "_mcp_server",
        SimpleNamespace(
            request_context=SimpleNamespace(
                lifespan_context={"app_lifespan_context": app_ctx}
            )
        ),
    )
    monkeypatch.setattr(
        progressive_server_module,
        "_sanitize_schema_for_compatibility",
        lambda tool: None,
    )

    tools = await progressive_mcp._list_tools_mcp()

    list_tools.assert_awaited_once_with(run_middleware=False)
    assert [tool.name for tool in tools] == ["jira_discover"]


@pytest.mark.anyio
async def test_progressive_list_tools_falls_back_to_deployment_config(monkeypatch):
    jira_tool = SimpleNamespace(
        name="jira_discover",
        to_mcp_tool=lambda *, name: SimpleNamespace(name=name),
    )
    confluence_tool = SimpleNamespace(
        name="confluence_discover",
        to_mcp_tool=lambda *, name: SimpleNamespace(name=name),
    )
    list_tools = AsyncMock(return_value=[jira_tool, confluence_tool])

    monkeypatch.setattr(progressive_mcp, "list_tools", list_tools)
    monkeypatch.setattr(progressive_mcp, "_tool_filter_context", lambda: None)
    monkeypatch.setattr(
        progressive_server_module,
        "get_available_services",
        lambda: {"jira": True, "confluence": False},
    )
    monkeypatch.setattr(
        progressive_server_module,
        "_sanitize_schema_for_compatibility",
        lambda tool: None,
    )

    tools = await progressive_mcp._list_tools_mcp()

    list_tools.assert_awaited_once_with(run_middleware=False)
    assert [tool.name for tool in tools] == ["jira_discover"]
