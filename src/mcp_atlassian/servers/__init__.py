"""MCP Atlassian Servers Package."""

from .main import main_mcp


def get_server_for_profile(profile: str):
    if str(profile).strip().lower() == "progressive":
        from mcp_atlassian.progressive import progressive_mcp

        return progressive_mcp
    return main_mcp


def __getattr__(name: str):
    if name == "progressive_mcp":
        from mcp_atlassian.progressive import progressive_mcp

        return progressive_mcp
    raise AttributeError(name)


__all__ = ["get_server_for_profile", "main_mcp", "progressive_mcp"]
