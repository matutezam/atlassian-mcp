# Repository Instructions

This file is the public baseline for the repository.

If `AGENTS.local.md` exists locally, read it as well and treat it as environment-specific guidance that augments this file. `AGENTS.local.md` must stay local and must not be committed.

## Repository map

| Path | Purpose |
| --- | --- |
| `src/mcp_atlassian/` | Library source (Python ≥ 3.10) |
| `  ├─ jira/` | Jira client + mixins for issues, search, transitions, SLA, metrics, and related APIs |
| `  ├─ confluence/` | Confluence client + mixins for pages, search, analytics, comments, and related APIs |
| `  ├─ models/` | Pydantic v2 data models (`ApiModel` base) |
| `  ├─ servers/` | FastMCP server instances and transport entrypoints |
| `  ├─ progressive/` | Progressive capability catalog and guarded execution surface |
| `  ├─ preprocessing/` | Content conversion (ADF and Storage to Markdown) |
| `  └─ utils/` | Shared utilities (auth, logging, SSL, decorators) |
| `tests/` | Pytest suite: unit, integration, and real-API validation |
| `scripts/` | OAuth setup and testing scripts |

## Architecture

- `JiraFetcher` and `ConfluenceFetcher` compose service mixins and expose typed client behavior.
- `servers/main.py` selects the runtime transport and profile, then wires dependencies through the application context.
- `MCP_PROFILE=direct|progressive` controls whether the server exposes the full tool surface or the curated discovery surface.
- Progressive mode exposes only `*_discover`, `*_capability_schema`, `*_execute_read`, and `*_execute_write_guarded`.
- Config is environment-driven via `from_env()` factories on `JiraConfig` and `ConfluenceConfig`.
- `READ_ONLY_MODE=true` blocks write tools at server level even when the caller requests a guarded write.

## Dev workflow

```bash
uv sync --frozen --all-extras --dev
pre-commit install
pre-commit run --all-files
uv run pytest -xvs
uv run pytest tests/unit/ -xvs
uv run pytest tests/integration/
uv run pytest --cov=src/mcp_atlassian --cov-report=term-missing
```

Tests, lint, and typing should be clean before pushing.

## Publication Safety

- Do not commit or publish personal data, credentials, tokens, private keys, session cookies, or raw auth headers.
- Do not publish real infrastructure identifiers such as internal hostnames, LAN IPs, SSH shortcuts, personal email addresses, or deployment-specific service names.
- Do not commit raw API dumps, screenshots, logs, or notes from a live environment unless they have been reviewed and sanitized first.
- Keep examples, manifests, tests, and documentation generic. Use placeholders such as `PROJ-123`, `PROJ`, `ENG`, `example-user`, and `your-atlassian-host`.
- Before pushing, review staged changes and recent history for sensitive material, not just the current working tree.

## Local Overrides

- Put deployment-specific assumptions, private hostnames, real workspace names, operator workflow, and local shortcuts in `AGENTS.local.md`.
- Use `AGENTS.local.example.md` as the tracked template for that local file.
- Do not copy real values from `AGENTS.local.md` into committed docs, tests, examples, or code.

## Rules

1. Use `uv`, not `pip`.
2. Do not work on `main`; create a feature or fix branch.
3. Add type hints for new code.
4. New features need tests, and bug fixes need regression tests.
5. Use conventional commit types such as `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, and `ci`.
6. Prefer editing existing files over creating parallel alternatives.

## Code conventions

- Python ≥ 3.10
- 88 character line length
- Absolute imports sorted by Ruff
- `snake_case` for functions and `PascalCase` for classes
- Google-style docstrings for public APIs
- Specific exceptions instead of broad catches

## Gotchas

- Cloud and Server/Data Center diverge on endpoints, field names, and auth behavior. Check `is_cloud` before assuming parity.
- OAuth 2.0, PAT, and basic auth do not apply equally across every deployment model.
- `IGNORE_HEADER_AUTH=true` changes how remote HTTP wrappers validate callers; keep that behavior documented locally, not with real values in public docs.
- See `.env.example` for configuration options covering auth, proxying, SSL, filtering, and runtime behavior.

## Quick reference

```bash
uv run mcp-atlassian
uv run mcp-atlassian --oauth-setup
uv run mcp-atlassian -v
git checkout -b feature/description
git checkout -b fix/issue-description
git commit --trailer "Reported-by:<name>"
git commit --trailer "Github-Issue:#<number>"
```
