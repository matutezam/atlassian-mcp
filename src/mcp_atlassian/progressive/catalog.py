"""Capability catalog and execution helpers for the progressive profile."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from fastmcp import Context, FastMCP
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

from mcp_atlassian.servers.context import MainAppContext
from mcp_atlassian.utils.tools import should_include_tool
from mcp_atlassian.utils.toolsets import get_toolset_tag, should_include_tool_by_toolset

CapabilityMode = Literal["read", "write_guarded"]
SafetyClass = Literal["safe", "guarded", "dangerous"]
Domain = Literal["jira", "confluence"]
ProgressiveRisk = Literal["read", "write"]

DISCOVER_LIMIT = 8
WRITE_VERB_REGEX = re.compile(
    r"(create|update|edit|delete|remove|transition|move|comment|attach|publish|write)",
    re.IGNORECASE,
)
EXPLICIT_DANGER_REGEX = re.compile(
    r"(delete|remove|destroy|purge|cleanup|archive)",
    re.IGNORECASE,
)
TOKEN_SYNONYMS: dict[str, list[str]] = {
    "issue": ["issues", "ticket", "tickets", "task", "tasks", "incidencia", "incidencias", "tarea", "tareas"],
    "issues": ["issue", "ticket", "tickets", "task", "tasks"],
    "ticket": ["issue", "issues", "task", "tasks"],
    "tarea": ["task", "tasks", "issue", "issues"],
    "tareas": ["task", "tasks", "issue", "issues"],
    "proyecto": ["project", "projects"],
    "proyectos": ["project", "projects"],
    "comment": ["comments", "comentario", "comentarios"],
    "comentario": ["comment", "comments"],
    "comentarios": ["comment", "comments"],
    "transition": ["transitions", "status", "estado", "workflow"],
    "estado": ["status", "transition", "workflow"],
    "estados": ["status", "transition", "workflow"],
    "search": ["buscar", "busqueda", "search", "find", "jql", "cql"],
    "buscar": ["search", "find", "jql", "cql"],
    "wiki": ["page", "pages", "confluence", "documentacion", "documentacion", "docs"],
    "documentacion": ["page", "pages", "docs", "wiki", "documentation"],
    "page": ["pages", "wiki", "docs", "documentacion", "documentation"],
    "pages": ["page", "wiki", "docs", "documentacion", "documentation"],
    "espacio": ["space", "spaces"],
    "espacios": ["space", "spaces"],
}

JIRA_CATEGORY_ORDER = [
    "issues",
    "projects",
    "comments",
    "transitions",
    "fields",
    "agile",
    "worklog",
    "attachments",
    "users",
    "watchers",
    "forms",
    "metrics",
    "development",
]
CONFLUENCE_CATEGORY_ORDER = [
    "pages",
    "comments",
    "spaces",
    "attachments",
    "labels",
    "users",
    "analytics",
]


@dataclass(frozen=True)
class CapabilitySpec:
    id: str
    tool_name: str
    mode: CapabilityMode
    category: str
    summary: str
    description: str
    safety_class: SafetyClass
    keywords: tuple[str, ...]
    example: dict[str, Any]
    aliases: tuple[str, ...]
    args_schema: dict[str, Any]


@dataclass(frozen=True)
class DomainCatalog:
    domain: Domain
    capabilities: tuple[CapabilitySpec, ...]
    aliases: dict[str, str]


@dataclass(frozen=True)
class ToolOverride:
    category: str | None = None
    summary: str | None = None
    keywords: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    example: dict[str, Any] | None = None
    safety_class: SafetyClass | None = None


JIRA_OVERRIDES: dict[str, ToolOverride] = {
    "get_all_projects": ToolOverride(
        category="projects",
        summary="List available Jira projects.",
        keywords=("projects", "project list", "workspace", "portfolio"),
        aliases=("jira.list_projects",),
        example={},
    ),
    "search": ToolOverride(
        category="issues",
        summary="Search Jira issues using JQL.",
        keywords=("search", "jql", "issues", "backlog", "pending"),
        aliases=("jira.search_issues",),
        example={"jql": "project = PROJ ORDER BY updated DESC", "limit": 10},
    ),
    "get_issue": ToolOverride(
        category="issues",
        summary="Get detailed information for one Jira issue.",
        keywords=("issue", "ticket", "status", "details"),
        example={"issue_key": "PROJ-123"},
    ),
    "get_transitions": ToolOverride(
        category="transitions",
        summary="List available transitions for an issue.",
        keywords=("transition", "workflow", "status", "move"),
        aliases=("jira.list_transitions",),
        example={"issue_key": "PROJ-123"},
    ),
    "create_issue": ToolOverride(
        category="issues",
        summary="Create a new Jira issue.",
        keywords=("create", "issue", "task", "bug", "story"),
        example={
            "project_key": "PROJ",
            "summary": "Nueva tarea",
            "issue_type": "Task",
        },
    ),
    "update_issue": ToolOverride(
        category="issues",
        summary="Update fields on an existing Jira issue.",
        keywords=("update", "edit", "issue", "fields"),
        example={"issue_key": "PROJ-123", "fields": "{\"summary\":\"Actualizar resumen\"}"},
    ),
    "transition_issue": ToolOverride(
        category="transitions",
        summary="Move a Jira issue to another workflow status.",
        keywords=("transition", "status", "workflow", "done"),
        example={"issue_key": "PROJ-123", "transition_id": "31"},
    ),
    "add_comment": ToolOverride(
        category="comments",
        summary="Add a comment to a Jira issue.",
        keywords=("comment", "comentario", "notes", "reply"),
        example={"issue_key": "PROJ-123", "comment": "Trabajo completado."},
    ),
}

CONFLUENCE_OVERRIDES: dict[str, ToolOverride] = {
    "search": ToolOverride(
        category="pages",
        summary="Search Confluence content using text or CQL.",
        keywords=("search", "cql", "wiki", "docs", "documentation"),
        example={"query": "project roadmap", "limit": 10},
    ),
    "get_page": ToolOverride(
        category="pages",
        summary="Get a Confluence page by id or title.",
        keywords=("page", "wiki", "content", "documentation"),
        example={"title": "Project Planning", "space_key": "ENG"},
    ),
    "get_page_children": ToolOverride(
        category="pages",
        summary="List child pages for a Confluence page.",
        keywords=("children", "tree", "hierarchy", "pages"),
        example={"parent_id": "123456"},
    ),
    "get_space_page_tree": ToolOverride(
        category="spaces",
        summary="Inspect the page hierarchy for a Confluence space.",
        keywords=("space", "tree", "hierarchy", "pages"),
        example={"space_key": "ENG", "limit": 100},
    ),
    "create_page": ToolOverride(
        category="pages",
        summary="Create a new Confluence page.",
        keywords=("create", "page", "wiki", "documentation"),
        example={
            "space_key": "ENG",
            "title": "Nueva pagina",
            "content": "# Project Plan",
        },
    ),
    "update_page": ToolOverride(
        category="pages",
        summary="Update an existing Confluence page.",
        keywords=("update", "edit", "page", "wiki"),
        example={
            "page_id": "123456",
            "title": "Project Planning",
            "content": "# Actualizado",
        },
    ),
    "add_comment": ToolOverride(
        category="comments",
        summary="Add a comment to a Confluence page.",
        keywords=("comment", "comentario", "review"),
        example={"page_id": "123456", "comment": "Revisado."},
    ),
}

DOMAIN_OVERRIDES: dict[Domain, dict[str, ToolOverride]] = {
    "jira": JIRA_OVERRIDES,
    "confluence": CONFLUENCE_OVERRIDES,
}


async def build_domain_catalog(
    domain: Domain,
    server: FastMCP[MainAppContext],
    app_ctx: MainAppContext | None,
) -> DomainCatalog:
    if not _service_available(domain, app_ctx):
        return DomainCatalog(domain=domain, capabilities=(), aliases={})

    tools = await server.list_tools(run_middleware=False)
    overrides = DOMAIN_OVERRIDES[domain]
    capabilities: list[CapabilitySpec] = []
    aliases: dict[str, str] = {}

    for tool in tools:
        if domain not in tool.tags:
            continue
        if not _is_tool_enabled(tool.name, tool.tags, app_ctx):
            continue
        mode = _get_mode(tool.name, tool.tags)
        if mode == "write_guarded" and app_ctx and app_ctx.read_only:
            continue

        override = overrides.get(tool.name, ToolOverride())
        capability = CapabilitySpec(
            id=f"{domain}.{tool.name}",
            tool_name=tool.name,
            mode=mode,
            category=override.category or _infer_category(domain, tool.tags),
            summary=override.summary or _tool_summary(tool),
            description=tool.description or _tool_summary(tool),
            safety_class=override.safety_class or _infer_safety_class(mode, tool.name),
            keywords=_collect_keywords(domain, tool.name, tool.tags, override),
            example=override.example or _generate_example(tool.parameters),
            aliases=override.aliases,
            args_schema=_normalize_args_schema(tool.parameters),
        )
        capabilities.append(capability)
        for alias in capability.aliases:
            aliases[alias] = capability.id

    capabilities.sort(key=lambda item: item.id)
    return DomainCatalog(
        domain=domain,
        capabilities=tuple(capabilities),
        aliases=aliases,
    )


def infer_risk(intent: str, raw_risk: str | None) -> ProgressiveRisk:
    normalized = (raw_risk or "").strip().lower()
    if normalized in {"read", "write"}:
        return normalized  # type: ignore[return-value]
    return "write" if WRITE_VERB_REGEX.search(intent) else "read"


def discover_capabilities(
    catalog: DomainCatalog,
    intent_input: str | None,
    raw_risk: str | None,
) -> dict[str, Any]:
    intent = _normalize_text(intent_input or "")
    risk = infer_risk(intent, raw_risk)
    candidates = [
        capability
        for capability in catalog.capabilities
        if risk == "write" or capability.mode == "read"
    ]

    scored = [
        (capability, _score_capability(catalog.domain, capability, intent, risk))
        for capability in candidates
    ]
    scored.sort(key=lambda item: (-item[1], item[0].id))
    strong_matches = [capability for capability, score in scored if score > 0]
    ordered = (
        _fill_with_fallback(catalog.domain, strong_matches, candidates)
        if strong_matches
        else _fallback_capabilities(catalog.domain, candidates)
    )

    return {
        "ok": True,
        "intent": intent,
        "risk": risk,
        "capabilities": [
            {
                "id": capability.id,
                "mode": capability.mode,
                "summary": capability.summary,
                "category": capability.category,
                "safetyClass": capability.safety_class,
            }
            for capability in ordered[:DISCOVER_LIMIT]
        ],
        "totalMatches": len(strong_matches) or len(candidates),
        "nextStep": (
            f"Call {catalog.domain}_capability_schema then "
            f"{catalog.domain}_execute_read or {catalog.domain}_execute_write_guarded."
        ),
    }


def get_capability_schema(
    catalog: DomainCatalog,
    capability_id: str,
) -> dict[str, Any]:
    capability = resolve_capability(catalog, capability_id)
    if capability is None:
        return {
            "ok": False,
            "error": "unknown_capability",
            "capabilityId": capability_id,
            "available": [item.id for item in catalog.capabilities],
        }

    return {
        "ok": True,
        "capabilityId": capability.id,
        "mode": capability.mode,
        "category": capability.category,
        "safetyClass": capability.safety_class,
        "description": capability.description,
        "argsSchema": capability.args_schema,
        "example": capability.example,
        "aliases": list(capability.aliases),
    }


async def execute_read_capability(
    ctx: Context,
    catalog: DomainCatalog,
    server: FastMCP[MainAppContext],
    capability_id: str,
    raw_args: str | dict[str, Any] | None,
) -> dict[str, Any]:
    parsed_args = parse_capability_args(capability_id, raw_args)
    if not parsed_args["ok"]:
        return parsed_args

    capability = resolve_capability(catalog, capability_id)
    if capability is None or capability.mode != "read":
        return {
            "ok": False,
            "capabilityId": capability_id,
            "error": "unsupported_read_capability",
            "allowed": [item.id for item in catalog.capabilities if item.mode == "read"],
        }

    return await _run_capability(ctx, server, capability, parsed_args["args"])


async def execute_write_capability(
    ctx: Context,
    catalog: DomainCatalog,
    server: FastMCP[MainAppContext],
    capability_id: str,
    raw_args: str | dict[str, Any] | None,
    approved: bool,
) -> dict[str, Any]:
    parsed_args = parse_capability_args(capability_id, raw_args)
    if not parsed_args["ok"]:
        return parsed_args

    capability = resolve_capability(catalog, capability_id)
    if capability is None or capability.mode != "write_guarded":
        return {
            "ok": False,
            "capabilityId": capability_id,
            "error": "unsupported_write_capability",
            "allowed": [
                item.id for item in catalog.capabilities if item.mode == "write_guarded"
            ],
        }

    if not approved:
        return {
            "ok": False,
            "capabilityId": capability.id,
            "blocked": True,
            "reason": "write_requires_approved_true",
        }

    return await _run_capability(ctx, server, capability, parsed_args["args"])


def parse_capability_args(
    capability_id: str,
    raw_args: str | dict[str, Any] | None,
) -> dict[str, Any]:
    if raw_args is None:
        return {"ok": True, "args": {}}

    if isinstance(raw_args, dict):
        return {"ok": True, "args": raw_args}

    trimmed = raw_args.strip()
    if not trimmed:
        return {"ok": True, "args": {}}

    try:
        parsed = json.loads(trimmed)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "capabilityId": capability_id,
            "error": "invalid_args_json",
        }

    if not isinstance(parsed, dict):
        return {
            "ok": False,
            "capabilityId": capability_id,
            "error": "args_must_be_json_object",
        }

    return {"ok": True, "args": parsed}


def resolve_capability(
    catalog: DomainCatalog,
    capability_id: str,
) -> CapabilitySpec | None:
    normalized = capability_id.strip()
    canonical = catalog.aliases.get(normalized, normalized)
    return next((item for item in catalog.capabilities if item.id == canonical), None)


async def _run_capability(
    ctx: Context,
    server: FastMCP[MainAppContext],
    capability: CapabilitySpec,
    args: dict[str, Any],
) -> dict[str, Any]:
    del ctx
    try:
        result = await server.call_tool(capability.tool_name, args, run_middleware=False)
        if isinstance(result, ToolResult):
            data = _tool_result_to_data(result)
        else:
            data = result
        return {"ok": True, "capabilityId": capability.id, "data": data}
    except Exception as exc:
        return {
            "ok": False,
            "capabilityId": capability.id,
            "error": str(exc),
        }


def _tool_result_to_data(result: ToolResult) -> Any:
    if result.structured_content is not None:
        return result.structured_content

    if (
        len(result.content) == 1
        and isinstance(result.content[0], TextContent)
        and result.content[0].text
    ):
        text = result.content[0].text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    content_blocks: list[dict[str, Any]] = []
    for block in result.content:
        model_dump = getattr(block, "model_dump", None)
        if callable(model_dump):
            content_blocks.append(model_dump(mode="json", exclude_none=True))
        else:
            content_blocks.append({"type": getattr(block, "type", "unknown")})
    return content_blocks


def _service_available(domain: Domain, app_ctx: MainAppContext | None) -> bool:
    if app_ctx is None:
        return False
    if domain == "jira":
        return app_ctx.full_jira_config is not None
    return app_ctx.full_confluence_config is not None


def _is_tool_enabled(
    tool_name: str,
    tool_tags: set[str],
    app_ctx: MainAppContext | None,
) -> bool:
    enabled_tools = app_ctx.enabled_tools if app_ctx else None
    enabled_toolsets = app_ctx.enabled_toolsets if app_ctx else None
    return should_include_tool(tool_name, enabled_tools) and should_include_tool_by_toolset(
        tool_tags, enabled_toolsets
    )


def _get_mode(tool_name: str, tool_tags: set[str]) -> CapabilityMode:
    if "write" in tool_tags:
        return "write_guarded"
    if "read" in tool_tags:
        return "read"
    return "write_guarded" if WRITE_VERB_REGEX.search(tool_name) else "read"


def _infer_category(domain: Domain, tool_tags: set[str]) -> str:
    toolset = get_toolset_tag(tool_tags)
    if toolset:
        prefix = f"{domain}_"
        if toolset.startswith(prefix):
            return toolset[len(prefix) :]
        return toolset
    return "general"


def _tool_summary(tool: Any) -> str:
    if tool.annotations and getattr(tool.annotations, "title", None):
        return str(tool.annotations.title)
    description = tool.description or tool.name.replace("_", " ")
    first_line = description.strip().splitlines()[0]
    return first_line.rstrip(".")


def _infer_safety_class(mode: CapabilityMode, tool_name: str) -> SafetyClass:
    if mode == "read":
        return "safe"
    if EXPLICIT_DANGER_REGEX.search(tool_name):
        return "dangerous"
    return "guarded"


def _collect_keywords(
    domain: Domain,
    tool_name: str,
    tool_tags: set[str],
    override: ToolOverride,
) -> tuple[str, ...]:
    keywords = set(override.keywords)
    keywords.add(domain)
    keywords.add(tool_name.replace("_", " "))
    keywords.update(tool_name.split("_"))
    category = override.category or _infer_category(domain, tool_tags)
    keywords.add(category)
    toolset = get_toolset_tag(tool_tags)
    if toolset:
        keywords.add(toolset)
    for alias in override.aliases:
        keywords.add(alias)
        keywords.update(alias.split("."))
    return tuple(sorted(keywords))


def _normalize_args_schema(schema: dict[str, Any] | None) -> dict[str, Any]:
    if not schema:
        return {"type": "object", "properties": {}, "additionalProperties": False}

    normalized = dict(schema)
    normalized.setdefault("type", "object")
    normalized.setdefault("properties", {})
    normalized.setdefault("additionalProperties", False)
    return normalized


def _generate_example(schema: dict[str, Any] | None) -> dict[str, Any]:
    schema = _normalize_args_schema(schema)
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    example: dict[str, Any] = {}

    for name in required[:4]:
        value_schema = properties.get(name, {})
        example[name] = _example_value(name, value_schema)

    return example


def _example_value(name: str, schema: dict[str, Any]) -> Any:
    schema_type = schema.get("type")
    if schema_type == "integer":
        return schema.get("minimum", 1)
    if schema_type == "number":
        return schema.get("minimum", 1)
    if schema_type == "boolean":
        return True
    if schema_type == "array":
        return []
    if schema_type == "object":
        return {}

    lowered = name.lower()
    if lowered.endswith("_key") or lowered == "issue_key":
        return "PROJ-123"
    if lowered.endswith("_id") or lowered == "page_id":
        return "123456"
    if "query" in lowered:
        return "Project planning"
    if "jql" in lowered:
        return "project = PROJ ORDER BY updated DESC"
    if "cql" in lowered:
        return "space = ENG AND type = page"
    if "space" in lowered:
        return "ENG"
    if "project" in lowered:
        return "PROJ"
    if "title" in lowered:
        return "Project Planning"
    if "comment" in lowered:
        return "Actualizado."
    if "content" in lowered:
        return "# Project Plan"
    return name


def _score_capability(
    domain: Domain,
    capability: CapabilitySpec,
    intent: str,
    risk: ProgressiveRisk,
) -> int:
    tokens = _tokenize(intent)
    searchable = [
        capability.id,
        capability.tool_name,
        capability.category,
        capability.summary,
        capability.description,
        *capability.keywords,
        *capability.aliases,
    ]
    normalized_values = [_normalize_text(value) for value in searchable]

    score = 0
    for token in tokens:
        if token in capability.tool_name:
            score += 8
        if token in capability.id:
            score += 7
        if token in capability.category:
            score += 5
        if any(token in value for value in normalized_values):
            score += 2

    if not tokens and capability.mode == "read":
        score += 1

    if capability.mode == "read" and risk == "read":
        score += 1
    if capability.mode == "write_guarded" and risk == "write":
        score += 1
    if capability.safety_class == "dangerous" and not EXPLICIT_DANGER_REGEX.search(intent):
        score -= 3
    if domain in tokens:
        score += 2

    return score


def _tokenize(intent: str) -> list[str]:
    raw_tokens = _normalize_text(intent).split()
    expanded: set[str] = set()
    for token in raw_tokens:
        expanded.add(token)
        for synonym in TOKEN_SYNONYMS.get(token, []):
            expanded.add(_normalize_text(synonym))
    return sorted(expanded)


def _normalize_text(value: str) -> str:
    return (
        value.lower()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
    )


def _fallback_capabilities(
    domain: Domain,
    capabilities: Sequence[CapabilitySpec],
) -> list[CapabilitySpec]:
    by_category: dict[str, list[CapabilitySpec]] = {}
    for capability in capabilities:
        by_category.setdefault(capability.category, []).append(capability)

    ordered: list[CapabilitySpec] = []
    category_order = JIRA_CATEGORY_ORDER if domain == "jira" else CONFLUENCE_CATEGORY_ORDER
    for category in category_order:
        category_items = sorted(by_category.get(category, []), key=lambda item: item.id)
        if category_items:
            ordered.append(category_items[0])

    seen = {item.id for item in ordered}
    remaining = sorted(
        (item for item in capabilities if item.id not in seen),
        key=lambda item: item.id,
    )
    return [*ordered, *remaining][:DISCOVER_LIMIT]


def _fill_with_fallback(
    domain: Domain,
    primary: Sequence[CapabilitySpec],
    candidates: Sequence[CapabilitySpec],
) -> list[CapabilitySpec]:
    seen = {item.id for item in primary}
    fallback = [
        item
        for item in _fallback_capabilities(domain, candidates)
        if item.id not in seen
    ]
    return [*primary, *fallback][: max(DISCOVER_LIMIT, len(primary))]
