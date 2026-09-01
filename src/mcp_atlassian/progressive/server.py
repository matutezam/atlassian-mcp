"""Progressive MCP server for Atlassian."""

from typing import Annotated, Any

from fastmcp import Context
from mcp.types import Tool as MCPTool
from mcp.types import ToolAnnotations
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
from mcp_atlassian.utils.environment import get_available_services

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
        """Return a stable progressive tool surface for MCP client scans.

        ChatGPT and other remote MCP clients may enumerate tools outside the request
        shape used for normal tool execution. Do not collapse the catalog to an
        empty list merely because request-scoped lifespan state is unavailable.
        Prefer the normal request-aware service detection when possible, then fall
        back to deployment configuration (environment/OAuth/external-auth flags).
        """
        filter_ctx = self._tool_filter_context()
        allowed_names: set[str] = set()

        if filter_ctx is not None:
            app_lifespan_state: MainAppContext | None = filter_ctx["app_lifespan_state"]

            # Progressive capability catalogs are currently built from the
            # application context. Header-only multi-tenant availability must not
            # advertise progressive tools until that request-scoped availability is
            # propagated into catalog construction as well.
            jira_available = bool(
                app_lifespan_state and app_lifespan_state.full_jira_config is not None
            )
            confluence_available = bool(
                app_lifespan_state
                and app_lifespan_state.full_confluence_config is not None
            )
        else:
            configured_services = get_available_services()
            jira_available = bool(configured_services.get("jira", False))
            confluence_available = bool(configured_services.get("confluence", False))

        if jira_available:
            allowed_names |= JIRA_EXTERNAL_TOOLS
        if confluence_available:
            allowed_names |= CONFLUENCE_EXTERNAL_TOOLS

        all_tools = await self.list_tools(run_middleware=False)
        filtered_tools: list[MCPTool] = []
        for tool_obj in all_tools:
            if tool_obj.name not in allowed_names:
                continue
            mcp_tool = tool_obj.to_mcp_tool(name=tool_obj.name)
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


def _extract_lifespan_context(ctx: Context) -> dict[str, Any] | None:
    """Support both direct and request-scoped FastMCP context layouts."""
    lifespan_ctx = getattr(ctx, "lifespan_context", None)
    if isinstance(lifespan_ctx, dict):
        return lifespan_ctx

    request_context = getattr(ctx, "request_context", None)
    request_lifespan_ctx = getattr(request_context, "lifespan_context", None)
    if isinstance(request_lifespan_ctx, dict):
        return request_lifespan_ctx

    return None


async def _get_app_context(ctx: Context) -> MainAppContext | None:
    lifespan_ctx = _extract_lifespan_context(ctx)
    if isinstance(lifespan_ctx, dict):
        return lifespan_ctx.get("app_lifespan_context")
    return None


@progressive_mcp.tool(
    name="jira_discover",
    title="Discover Jira capabilities",
    description="Discover a short list of relevant Jira capabilities based on intent and risk.",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
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
    title="Get Jira capability schema",
    description="Return full input schema and usage examples for one Jira capability.",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
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
    title="Read from Jira",
    description="Execute approved read-only Jira capabilities.",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
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
    title="Write to Jira (guarded)",
    description="Execute Jira write capability only when approved=true. Otherwise returns blocked response.",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=True,
    ),
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
        bool,
        Field(
            default=False, description="Set true only after explicit human approval."
        ),
    ] = False,
) -> dict[str, Any]:
    app_ctx = await _get_app_context(ctx)
    catalog = await build_domain_catalog("jira", jira_mcp, app_ctx)
    return await execute_write_capability(
        ctx, catalog, jira_mcp, capability_id, args, approved
    )


@progressive_mcp.tool(
    name="confluence_discover",
    title="Discover Confluence capabilities",
    description="Discover a short list of relevant Confluence capabilities based on intent and risk.",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
)
async def confluence_discover(
    ctx: Context,
    intent: Annotated[
        str | None,
        Field(default=None, description="What user wants to do in Confluence."),
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
    title="Get Confluence capability schema",
    description="Return full input schema and usage examples for one Confluence capability.",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
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
    title="Read from Confluence",
    description="Execute approved read-only Confluence capabilities.",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
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
    title="Write to Confluence (guarded)",
    description="Execute Confluence write capability only when approved=true. Otherwise returns blocked response.",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=True,
    ),
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
        bool,
        Field(
            default=False, description="Set true only after explicit human approval."
        ),
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
