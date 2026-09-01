# ChatGPT MCP deployment notes

This fork is designed to keep the MCP application contract independent from where the server is hosted. The same progressive profile should work on a private machine (for example a Raspberry Pi on a LAN/VPN) and on a VPS behind EasyPanel or another reverse proxy.

## MCP application contract

- Use Streamable HTTP for remote clients.
- Keep the MCP endpoint at `/mcp` unless the deployment explicitly overrides it.
- Keep `/healthz` separate from the MCP endpoint for health checks.
- Do not make tool registration depend on a public hostname, LAN address, VPN address, or reverse-proxy implementation.
- Keep authentication enabled even when network access is restricted.
- After changing tool names, schemas, titles, or annotations, refresh/rescan the MCP app in ChatGPT so its tool snapshot is rebuilt.

The progressive profile exposes a small stable surface and performs capability discovery internally. Tool annotations describe behavior to MCP clients; they are hints only and do not replace the existing authorization and guarded-write checks.

## Private LAN / VPN / Raspberry Pi

A private RFC1918/VPN address is intentionally not assumed to be reachable by ChatGPT's hosted runtime. Keep the MCP service private and expose it to ChatGPT through a supported secure MCP tunnel or equivalent controlled ingress rather than opening the raw application port to the Internet.

Recommended shape:

```text
ChatGPT
  -> secure MCP tunnel / controlled ingress
  -> private HTTPS/HTTP endpoint
  -> MCP service on RPi/LAN
  -> Jira / Confluence
```

A VPN remains useful for administrator access and other local clients, but the MCP application itself should not require a specific VPN vendor or subnet.

## VPS / EasyPanel / reverse proxy

On a VPS, terminate TLS at EasyPanel or the reverse proxy and route the public HTTPS MCP URL to the service's `/mcp` endpoint.

Recommended shape:

```text
ChatGPT
  -> https://mcp.example.com/mcp
  -> EasyPanel / reverse proxy
  -> MCP container
  -> Jira / Confluence
```

The proxy should preserve `Authorization`, MCP session/protocol headers, HTTP methods used by Streamable HTTP, and streaming behavior. Do not publish an unauthenticated MCP endpoint merely because TLS is present.

## Deployment checklist

1. Run with `TRANSPORT=streamable-http` (or the equivalent CLI option).
2. Confirm `/healthz` responds without exposing credentials.
3. Confirm the MCP endpoint is reachable through the intended private tunnel or HTTPS reverse proxy.
4. Confirm authentication still applies at `/mcp`.
5. Refresh/scan tools in ChatGPT after deployment.
6. Start a new chat, select the MCP app for the message, and test a read-only capability before testing guarded writes.
