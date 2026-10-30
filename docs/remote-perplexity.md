# Remote MCP for Perplexity (Linux VPS)

This is a read-only first version, not a complete migration of the Hermes agent.
The existing `python -m mcp_server.server` stdio entry point is unchanged.
The new `python -m mcp_server.http_server` serves Streamable HTTP at `/mcp`.

## Scope and prerequisites

- A Linux VPS with Docker Engine and Compose, plus a hostname you control.
- An operational database and pipeline, installed using README section 5.
  Run migrations, create roles, seed and backfill data, and start workers/scheduler first.
- A vnstock API key for the pipeline. The remote MCP container needs only the
  `mcp_ro` database URL, not a vnstock key, admin credentials or write credentials.
- A DNS A record pointing the hostname to the VPS. Remove a stale AAAA record
  unless IPv6 actually reaches this server. Allow inbound TCP 80/443 for HTTPS.
  Restrict SSH to trusted sources. Never publish the database or port 8000 publicly.
- This Compose stack uses Linux host networking, like the existing pipeline stack.
  It is not a Docker Desktop on Windows deployment recipe.

## Configure and start

From the repository root on the VPS:

```bash
cp infrastructure/remote/.env.example infrastructure/remote/.env
chmod 600 infrastructure/remote/.env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Edit `infrastructure/remote/.env` privately. Set MCP_DOMAIN to your hostname,
MCP_API_TOKEN to the generated secret, and MCP_RO_DATABASE_URL to the real
read-only role URL. URL-encode special characters in database passwords.
Keep PostgreSQL bound to 127.0.0.1 as in the existing database Compose file.
Do not commit secrets or paste them into a chat. Do not use example passwords.

```bash
docker compose --env-file infrastructure/remote/.env \
  -f infrastructure/remote/docker-compose.yml up -d --build
docker compose --env-file infrastructure/remote/.env \
  -f infrastructure/remote/docker-compose.yml ps
```

Caddy provisions HTTPS for the configured hostname. DNS, inbound 80/443 and
certificate issuance must work; inspect Caddy logs if HTTPS is unavailable.
It proxies to the loopback-only app. Only the generic `/healthz` is public;
it checks process liveness, not database readiness or data freshness.
The app requires `Authorization: Bearer <MCP_API_TOKEN>` for `/mcp`.
No custom request header is required. Restart mcp after changing the token.

## Verify before connecting

```bash
python -m unittest discover -s tests -p test_remote_http.py -v
curl -i https://YOUR_HOST/healthz
curl -i -X POST https://YOUR_HOST/mcp
```

The public health check should return 200; unauthenticated MCP should return 401.
The SDK smoke test runs only when project dependencies are installed; it
initializes MCP and lists tools without connecting to Postgres. Run the full
project tests as well. Use an MCP client/inspector with a privately configured
Authorization bearer header to initialize, list tools, and query a seeded ticker.
Also verify missing/wrong tokens fail, unexpected origins fail, and 8000/55432
are unreachable from another machine. A passing health check alone is not proof
of a working database, a working Perplexity connection or fresh market data.

## Add the Perplexity connector

Open Plugins (or Customize > Connectors), then Add custom > Add MCP connector > Remote.
Use the real `https://YOUR_HOST/mcp` URL, Streamable HTTP transport and API Key
authentication. Configure the credential so the request uses the standard
Authorization bearer header shown above. The help documentation confirms API Key
support but does not specify whether its UI expects a raw token or a complete
Bearer value; verify the resulting connection rather than assuming either.
Never solve a 401 by disabling authentication or publishing a token in a URL.
If API-key header formatting is incompatible, stop and adapt authentication.

Enable the connector and ask: "Using Vietnam Stock Market, screen the stored VN30
stocks with RSI below 30; show the trade dates and provisional-data warnings."

Official setup documentation:
https://www.perplexity.ai/help-center/en/articles/13915507-adding-custom-remote-connectors

## Available tools and limitations

- get_snapshot: reads an existing snapshot, not a fresh analysis job.
- query_history: returns rows directly for prices/fundamentals/foreign_flow;
  dates are required, limited to 366 inclusive days per call.
- screen_tickers: screens stored bars; defaults to VN30, max 100 explicit tickers.

All tools use existing read-only database functions and advertise readOnlyHint.
The container supplies no write database URL and sets default_transaction_read_only
and a 15-second statement timeout. Request bodies are limited to 1 MiB.
The app limits concurrent connections, but has no dedicated rate-limiting service;
use upstream rate limiting before broader/public sharing. Treat this as a
single-owner connector, not a multi-tenant identity or portfolio system.

Write tools, job submission, personal positions/watchlists, Hermes subagents,
Telegram alerts and filesystem exports are deliberately not exposed. A remote
client cannot read a local file path returned by export_price_bars, so that tool
is omitted; query_history provides bounded inline data instead.
The scheduler/worker must keep the database current. Check trade dates and
warnings; a reachable service can still return stale or missing data.
The scoring model is not a validated investment recommendation system.

## Status and rollback

Preparing these files does not provision hosting or prove an end-to-end connection.
Authentication unit tests can run without project dependencies. SDK, Docker build,
Postgres queries, TLS and Perplexity must be verified in the deployment environment.

```bash
docker compose --env-file infrastructure/remote/.env \
  -f infrastructure/remote/docker-compose.yml down
```

This stops only the separate remote stack; do not use `down -v` on the database
stack. Existing stdio and pipeline files are unchanged.
