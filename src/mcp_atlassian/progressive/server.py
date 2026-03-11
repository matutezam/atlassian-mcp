"""Progressive MCP server for Atlassian."""

from typing import Annotated, Any

from fastmcp import Context
from mcp.types import Tool as MCPTool
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_atlassian.progressive.catalog import (
    build_domain_catalog,
    discover_capabilities,
    execute_read_capability,
    execute_write_capability,
    get_capability_schema,
)
from mcp_atlassian.servers.confluence import confluence_mcp
from mcp_atlassian.servers.context import MainAppContext
from mcp_atlassian.servers.jira import jira_mcp
from mcp_atlassian.servers.main import (
    AtlassianMCP,
    _sanitize_schema_for_compatibility,
    health_check,
    logger,
    main_lifespan,
)

JIRA_EXTERNAL_TOOLS = {
    "jira_discover",
    "jira_capability_schema",
    "jira_execute_read",
    "jira_execute_write_guarded",
}
CONFLUENCE_EXTERNAL_TOOLS = {
    "confluence_discover",
    "confluence_capability_schema",
    "confluence_execute_read",
    "confluence_execute_write_guarded",
}


class ProgressiveAtlassianMCP(AtlassianMCP):
    """Progressive server exposing only curated discovery and execution tools."""

    async def _list_tools_mcp(self) -> list[MCPTool]:
        req_context = self._mcp_server.request_context
        if req_context is None or req_context.lifespan_context is None:
            return []

        lifespan_ctx_dict = req_context.lifespan_context
        app_lifespan_state: MainAppContext | None = (
            lifespan_ctx_dict.get("app_lifespan_context")
            if isinstance(lifespan_ctx_dict, dict)
            else None
        )
        allowed_names = set()
        if app_lifespan_state and app_lifespan_state.full_jira_config is not None:
            allowed_names |= JIRA_EXTERNAL_TOOLS
        if app_lifespan_state and app_lifespan_state.full_confluence_config is not None:
            allowed_names |= CONFLUENCE_EXTERNAL_TOOLS

        all_tools = await self.get_tools()
        filtered_tools: list[MCPTool] = []
        for registered_name, tool_obj in all_tools.items():
            if registered_name not in allowed_names:
                continue
            mcp_tool = tool_obj.to_mcp_tool(name=registered_name)
            _sanitize_schema_for_compatibility(mcp_tool)
            filtered_tools.append(mcp_tool)

        logger.debug("Progressive tool exposure filtered to: %s", allowed_names)
        return filtered_tools


progressive_mcp = ProgressiveAtlassianMCP(
    name="Atlassian Progressive MCP",
    instructions=(
        "Expose only progressive discovery/schema/execute tools for Jira and "
        "Confluence."
    ),
    lifespan=main_lifespan,
)


async def _get_app_context(ctx: Context) -> MainAppContext | None:
    lifespan_ctx = ctx.lifespan_context
    if isinstance(lifespan_ctx, dict):
        return lifespan_ctx.get("app_lifespan_context")
    return None


@progressive_mcp.tool(
    name="jira_discover",
    description="Discover a short list of relevant Jira capabilities based on intent and risk.",
)
async def jira_discover(
    ctx: Context,
    intent: Annotated[
        str | None, Field(default=None, description="What user wants to do in Jira.")
    ] = None,
    risk: Annotated[
        str | None, Field(default=None, description="Use read or write.")
    ] = None,
) -> dict[str, Any]:
    app_ctx = await _get_app_context(ctx)
    catalog = await build_domain_catalog("jira", jira_mcp, app_ctx)
    return discover_capabilities(catalog, intent, risk)


@progressive_mcp.tool(
    name="jira_capability_schema",
    description="Return full input schema and usage examples for one Jira capability.",
)
async def jira_capability_schema(
    ctx: Context,
    capability_id: Annotated[
        str, Field(description="Capability identifier from jira_discover.")
    ],
) -> dict[str, Any]:
    app_ctx = await _get_app_context(ctx)
    catalog = await build_domain_catalog("jira", jira_mcp, app_ctx)
    return get_capability_schema(catalog, capability_id)


@progressive_mcp.tool(
    name="jira_execute_read",
    description="Execute approved read-only Jira capabilities.",
)
async def jira_execute_read(
    ctx: Context,
    capability_id: Annotated[str, Field(description="Read capability id.")],
    args: Annotated[
        str | None,
        Field(
            default=None,
            description="Arguments JSON string for the capability. Use {} for no-args capabilities.",
        ),
    ] = None,
) -> dict[str, Any]:
    app_ctx = await _get_app_context(ctx)
    catalog = await build_domain_catalog("jira", jira_mcp, app_ctx)
    return await execute_read_capability(ctx, catalog, jira_mcp, capability_id, args)


@progressive_mcp.tool(
    name="jira_execute_write_guarded",
    description="Execute Jira write capability only when approved=true. Otherwise returns blocked response.",
)
async def jira_execute_write_guarded(
    ctx: Context,
    capability_id: Annotated[str, Field(description="Write capability id.")],
    args: Annotated[
        str | None,
        Field(
            default=None,
            description="Arguments JSON string for the capability. Use {} for no-args capabilities.",
        ),
    ] = None,
    approved: Annotated[
        bool, Field(default=False, description="Set true only after explicit human approval.")
    ] = False,
) -> dict[str, Any]:
    app_ctx = await _get_app_context(ctx)
    catalog = await build_domain_catalog("jira", jira_mcp, app_ctx)
    return await execute_write_capability(
        ctx, catalog, jira_mcp, capability_id, args, approved
    )


@progressive_mcp.tool(
    name="confluence_discover",
    description="Discover a short list of relevant Confluence capabilities based on intent and risk.",
)
async def confluence_discover(
    ctx: Context,
    intent: Annotated[
        str | None, Field(default=None, description="What user wants to do in Confluence.")
    ] = None,
    risk: Annotated[
        str | None, Field(default=None, description="Use read or write.")
    ] = None,
) -> dict[str, Any]:
    app_ctx = await _get_app_context(ctx)
    catalog = await build_domain_catalog("confluence", confluence_mcp, app_ctx)
    return discover_capabilities(catalog, intent, risk)


@progressive_mcp.tool(
    name="confluence_capability_schema",
    description="Return full input schema and usage examples for one Confluence capability.",
)
async def confluence_capability_schema(
    ctx: Context,
    capability_id: Annotated[
        str, Field(description="Capability identifier from confluence_discover.")
    ],
) -> dict[str, Any]:
    app_ctx = await _get_app_context(ctx)
    catalog = await build_domain_catalog("confluence", confluence_mcp, app_ctx)
    return get_capability_schema(catalog, capability_id)


@progressive_mcp.tool(
    name="confluence_execute_read",
    description="Execute approved read-only Confluence capabilities.",
)
async def confluence_execute_read(
    ctx: Context,
    capability_id: Annotated[str, Field(description="Read capability id.")],
    args: Annotated[
        str | None,
        Field(
            default=None,
            description="Arguments JSON string for the capability. Use {} for no-args capabilities.",
        ),
    ] = None,
) -> dict[str, Any]:
    app_ctx = await _get_app_context(ctx)
    catalog = await build_domain_catalog("confluence", confluence_mcp, app_ctx)
    return await execute_read_capability(
        ctx, catalog, confluence_mcp, capability_id, args
    )


@progressive_mcp.tool(
    name="confluence_execute_write_guarded",
    description="Execute Confluence write capability only when approved=true. Otherwise returns blocked response.",
)
async def confluence_execute_write_guarded(
    ctx: Context,
    capability_id: Annotated[str, Field(description="Write capability id.")],
    args: Annotated[
        str | None,
        Field(
            default=None,
            description="Arguments JSON string for the capability. Use {} for no-args capabilities.",
        ),
    ] = None,
    approved: Annotated[
        bool, Field(default=False, description="Set true only after explicit human approval.")
    ] = False,
) -> dict[str, Any]:
    app_ctx = await _get_app_context(ctx)
    catalog = await build_domain_catalog("confluence", confluence_mcp, app_ctx)
    return await execute_write_capability(
        ctx, catalog, confluence_mcp, capability_id, args, approved
    )


@progressive_mcp.custom_route("/healthz", methods=["GET"], include_in_schema=False)
async def _health_check_route(request: Request) -> JSONResponse:
    return await health_check(request)
