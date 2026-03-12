from types import SimpleNamespace

import pytest

from mcp_atlassian.progressive.server import _extract_lifespan_context, _get_app_context
from mcp_atlassian.servers.context import MainAppContext


def test_extract_lifespan_context_prefers_direct_context():
    app_ctx = MainAppContext(full_jira_config=object())
    ctx = SimpleNamespace(
        lifespan_context={"app_lifespan_context": app_ctx},
        request_context=SimpleNamespace(lifespan_context={"app_lifespan_context": None}),
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
