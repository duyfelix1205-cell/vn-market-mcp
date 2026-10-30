"""Dependency-free ASGI bearer authentication for the remote MCP entry point."""
from __future__ import annotations

import secrets


class BearerGate:
    def __init__(self, app, token: str):
        if len(token) < 32 or token != token.strip() or any(c.isspace() for c in token):
            raise ValueError("MCP_API_TOKEN must be a whitespace-free secret of at least 32 characters")
        self.app = app
        self.token = token.encode("utf-8")

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)
        if scope["type"] != "http":
            await send({"type": "websocket.close", "code": 1008})
            return
        path = scope.get("path", "")
        if path == "/healthz" and scope.get("method") in {"GET", "HEAD"}:
            return await self.reply(scope, send, 200, b'{"status":"ok"}')
        if path != "/mcp":
            return await self.reply(scope, send, 404, b'{"error":"not_found"}')
        values = [v for k, v in scope.get("headers", []) if k.lower() == b"authorization"]
        parts = values[0].split(b" ", 1) if len(values) == 1 else []
        valid = (len(parts) == 2 and parts[0].lower() == b"bearer"
                 and secrets.compare_digest(parts[1], self.token))
        if not valid:
            return await self.reply(scope, send, 401, b'{"error":"unauthorized"}',
                                    [(b"www-authenticate", b'Bearer realm="vn-market-mcp"')])
        return await self.app(scope, receive, send)

    @staticmethod
    async def reply(scope, send, status, body, extra=()):
        headers = [(b"content-type", b"application/json"), (b"cache-control", b"no-store"),
                   (b"content-length", str(len(body)).encode()), *extra]
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": b"" if scope.get("method") == "HEAD" else body})
