# Local Repository Instructions

This file is a template for `AGENTS.local.md`.

- Copy it to `AGENTS.local.md`.
- Keep `AGENTS.local.md` out of git.
- Put only environment-specific or operator-specific guidance there.

## Local Targets

- Jira URL: `https://your-atlassian-host.atlassian.net`
- Confluence URL: `https://your-atlassian-host.atlassian.net/wiki`
- Deployment profile: `progressive`
- Preferred transport: `streamable-http`
- Local MCP endpoint: `http://your-local-host:8000/mcp`

## Local Auth Model

- Runtime auth mode: service credentials or OAuth, depending on deployment.
- If using a remote HTTP wrapper, document the local header contract here.
- Keep real usernames, tokens, headers, and secrets out of public files.

## Local Validation Workflow

1. Run:
   - `uv sync --frozen --all-extras --dev`
   - `pre-commit run --all-files`
   - `uv run pytest -xvs`
2. If validating only the progressive surface:
   - `uv run pytest tests/unit/progressive/test_catalog.py -xvs`
   - `uv run pytest tests/unit/test_profile_selection.py -xvs`
   - `uv run pytest tests/unit/test_main_transport_selection.py -xvs`
3. If deploying a remote HTTP service:
   - verify `/mcp` responds with the expected transport
   - verify auth headers are enforced as intended
   - verify `READ_ONLY_MODE` behavior matches the target environment
4. Only then push and redeploy.

## Local Notes

- Keep real site names, project keys, space keys, internal URLs, and deployment shortcuts here, not in public docs.
- Do not paste secrets unless absolutely necessary. Prefer environment variables or a password manager.
