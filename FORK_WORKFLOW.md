# Fork Workflow and Upstream Sync

This repository is maintained as a fork of `sooperset/mcp-atlassian` with an additional progressive MCP profile for Jira and Confluence.

## Current Policy

- `main` should stay deployable.
- `MCP_PROFILE=direct|progressive` must be preserved.
- Progressive mode exposes a small wrapper surface: discovery, schema, read execution, and guarded write execution.
- `READ_ONLY_MODE=true` must continue blocking writes at server level.
- Do not commit real Atlassian URLs, emails, API tokens, PATs, OAuth tokens, raw headers, or production logs.

## Upstream Reconciliation

Upstream currently does **not** ship `src/mcp_atlassian/progressive/` or `tests/unit/progressive/`. A direct merge can delete the local progressive implementation. Treat upstream as a source of selected patches, not as a branch to merge blindly.

Preferred flow:

```bash
git checkout main
git pull --ff-only origin main
git fetch upstream
git checkout -b codex/short-description
# inspect upstream commits
# cherry-pick or manually adapt only the relevant patches
```

Bring forward selectively:

- dependency and lockfile fixes,
- auth and token handling fixes,
- transport / FastMCP compatibility fixes,
- schema compatibility fixes,
- Jira/Confluence API client fixes,
- sanitized documentation updates.

Preserve intentionally:

- `src/mcp_atlassian/progressive/`,
- `tests/unit/progressive/`,
- `src/mcp_atlassian/servers/__init__.py` profile selection,
- `MCP_PROFILE=direct|progressive`,
- local static API-key middleware behavior used by the deployed HTTP wrapper.

## Validation

Run local validation with `uv` when available:

```bash
uv sync --frozen --all-extras --dev
uv run pytest tests/unit/progressive tests/unit/test_profile_selection.py tests/unit/test_main_transport_selection.py -q
```

Remote smoke tests after deployment should avoid real writes unless explicitly approved:

- `jira_discover` returns progressive capabilities.
- `jira_capability_schema` returns schema for a known capability such as `jira.create_issue`.
- `jira_execute_read jira.get_all_projects` returns either visible projects or an auth/permission error that matches the configured account.
- `jira_execute_write_guarded` with `approved=false` blocks writes.

If the Atlassian account has expired or no visible projects, discovery and schema checks still validate the progressive wrapper; real read/write behavior needs a refreshed account.
