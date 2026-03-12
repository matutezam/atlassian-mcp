from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

from mcp_atlassian.progressive.catalog import (
    CapabilitySpec,
    DomainCatalog,
    build_domain_catalog,
    discover_capabilities,
    execute_read_capability,
    execute_write_capability,
    parse_capability_args,
)
from mcp_atlassian.servers.context import MainAppContext


@dataclass
class FakeTool:
    name: str
    tags: set[str]
    description: str
    parameters: dict
    annotations: object | None = None


@dataclass
class FakeRegisteredTool:
    name: str
    result: object

    async def run(self, arguments):
        del arguments
        return self.result


class FakeServer:
    def __init__(self, tools):
        self._tools = tools

    async def list_tools(self, run_middleware: bool = False):
        del run_middleware
        return self._tools

    async def get_tools(self):
        return {tool.name: tool for tool in self._tools}


class GetToolsOnlyServer:
    def __init__(self, tools):
        self._tools = tools

    async def get_tools(self):
        return {tool.name: tool for tool in self._tools}


@pytest.mark.anyio
async def test_build_domain_catalog_adds_aliases_and_filters_readonly():
    server = FakeServer(
        [
            FakeTool(
                name="search",
                tags={"jira", "read", "toolset:jira_issues"},
                description="Search Jira issues using JQL.",
                parameters={
                    "type": "object",
                    "properties": {"jql": {"type": "string"}},
                    "required": ["jql"],
                },
            ),
            FakeTool(
                name="create_issue",
                tags={"jira", "write", "toolset:jira_issues"},
                description="Create issue.",
                parameters={
                    "type": "object",
                    "properties": {"project_key": {"type": "string"}},
                    "required": ["project_key"],
                },
            ),
        ]
    )

    writable_ctx = MainAppContext(full_jira_config=object(), read_only=False)
    writable_catalog = await build_domain_catalog("jira", server, writable_ctx)
    assert {item.id for item in writable_catalog.capabilities} == {
        "jira.create_issue",
        "jira.search",
    }
    assert writable_catalog.aliases["jira.search_issues"] == "jira.search"

    readonly_ctx = MainAppContext(full_jira_config=object(), read_only=True)
    readonly_catalog = await build_domain_catalog("jira", server, readonly_ctx)
    assert {item.id for item in readonly_catalog.capabilities} == {"jira.search"}


@pytest.mark.anyio
async def test_build_domain_catalog_supports_get_tools_only_servers():
    server = GetToolsOnlyServer(
        [
            FakeTool(
                name="search",
                tags={"jira", "read", "toolset:jira_issues"},
                description="Search Jira issues using JQL.",
                parameters={
                    "type": "object",
                    "properties": {"jql": {"type": "string"}},
                    "required": ["jql"],
                },
            )
        ]
    )

    catalog = await build_domain_catalog(
        "jira", server, MainAppContext(full_jira_config=object(), read_only=False)
    )

    assert [item.id for item in catalog.capabilities] == ["jira.search"]


def test_parse_capability_args_rejects_invalid_payloads():
    invalid_json = parse_capability_args("jira.search", "not-json")
    assert invalid_json == {
        "ok": False,
        "capabilityId": "jira.search",
        "error": "invalid_args_json",
    }

    invalid_type = parse_capability_args("jira.search", "[]")
    assert invalid_type == {
        "ok": False,
        "capabilityId": "jira.search",
        "error": "args_must_be_json_object",
    }


@pytest.mark.anyio
async def test_execute_write_capability_requires_approval():
    catalog = DomainCatalog(
        domain="jira",
        capabilities=(
            CapabilitySpec(
                id="jira.create_issue",
                tool_name="create_issue",
                mode="write_guarded",
                category="issues",
                summary="Create issue",
                description="Create issue",
                safety_class="guarded",
                keywords=("issue",),
                example={"project_key": "PROJ"},
                aliases=(),
                args_schema={"type": "object", "properties": {}},
            ),
        ),
        aliases={},
    )

    result = await execute_write_capability(
        ctx=None,  # type: ignore[arg-type]
        catalog=catalog,
        server=FakeServer([]),  # type: ignore[arg-type]
        capability_id="jira.create_issue",
        raw_args="{}",
        approved=False,
    )

    assert result == {
        "ok": False,
        "capabilityId": "jira.create_issue",
        "blocked": True,
        "reason": "write_requires_approved_true",
    }


@pytest.mark.anyio
async def test_execute_read_capability_supports_get_tools_only_runtime():
    catalog = DomainCatalog(
        domain="jira",
        capabilities=(
            CapabilitySpec(
                id="jira.search",
                tool_name="search",
                mode="read",
                category="issues",
                summary="Search issue",
                description="Search issue",
                safety_class="safe",
                keywords=("search",),
                example={"jql": "project = PROJ"},
                aliases=(),
                args_schema={"type": "object", "properties": {}},
            ),
        ),
        aliases={},
    )
    server = GetToolsOnlyServer(
        [
            FakeRegisteredTool(
                name="search",
                result=ToolResult(content=[TextContent(type="text", text='{"issues": []}')]),
            )
        ]
    )

    result = await execute_read_capability(
        ctx=None,  # type: ignore[arg-type]
        catalog=catalog,
        server=server,  # type: ignore[arg-type]
        capability_id="jira.search",
        raw_args="{}",
    )

    assert result == {
        "ok": True,
        "capabilityId": "jira.search",
        "data": {"issues": []},
    }


def test_discover_capabilities_prefers_relevant_issue_search():
    catalog = DomainCatalog(
        domain="jira",
        capabilities=(
            CapabilitySpec(
                id="jira.search",
                tool_name="search",
                mode="read",
                category="issues",
                summary="Search Jira issues using JQL.",
                description="Search Jira issues using JQL.",
                safety_class="safe",
                keywords=("search", "issues", "jql", "project"),
                example={"jql": "project = PROJ"},
                aliases=("jira.search_issues",),
                args_schema={"type": "object", "properties": {}},
            ),
            CapabilitySpec(
                id="jira.get_all_projects",
                tool_name="get_all_projects",
                mode="read",
                category="projects",
                summary="List projects.",
                description="List projects.",
                safety_class="safe",
                keywords=("projects",),
                example={},
                aliases=("jira.list_projects",),
                args_schema={"type": "object", "properties": {}},
            ),
        ),
        aliases={"jira.search_issues": "jira.search", "jira.list_projects": "jira.get_all_projects"},
    )

    result = discover_capabilities(catalog, "buscar issues con jql", "read")
    assert result["capabilities"][0]["id"] == "jira.search"
