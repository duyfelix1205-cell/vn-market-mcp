"""Auth tests run without a database; SDK smoke tests need project dependencies."""
import asyncio
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location(
    "remote_auth_under_test", Path(__file__).resolve().parents[1] / "mcp_server" / "http_auth.py")
AUTH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUTH)
BearerGate = AUTH.BearerGate
TOKEN = "a" * 48


async def invoke(path="/mcp", headers=(), method="POST"):
    sent, forwarded = [], []

    async def downstream(scope, receive, send):
        forwarded.append(scope["type"])
        if scope["type"] == "http":
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    gate = BearerGate(downstream, TOKEN)
    await gate({"type": "http", "path": path, "method": method, "headers": list(headers)}, receive, send)
    return sent, forwarded


class AuthTests(unittest.TestCase):
    def test_rejects_missing_or_weak_secret(self):
        for token in ("", "short", " " + TOKEN, TOKEN + " ", "a" * 32 + "\nb"):
            with self.assertRaises(ValueError):
                BearerGate(None, token)

    def test_missing_wrong_and_duplicate_credentials(self):
        cases = [(), [(b"authorization", b"Bearer wrong")],
                 [(b"authorization", TOKEN.encode())],
                 [(b"authorization", b"Basic " + TOKEN.encode())],
                 [(b"authorization", b"Bearer " + TOKEN.encode())] * 2]
        for headers in cases:
            with self.subTest(headers=headers):
                sent, forwarded = asyncio.run(invoke(headers=headers))
                self.assertEqual(sent[0]["status"], 401)
                self.assertFalse(forwarded)
                self.assertNotIn(TOKEN.encode(), sent[1]["body"])

    def test_bearer_is_case_insensitive(self):
        sent, forwarded = asyncio.run(invoke(headers=[(b"Authorization", b"bEaReR " + TOKEN.encode())]))
        self.assertEqual(sent[0]["status"], 204)
        self.assertEqual(forwarded, ["http"])

    def test_health_is_generic_and_head_has_no_body(self):
        sent, forwarded = asyncio.run(invoke("/healthz", method="GET"))
        self.assertEqual(sent[0]["status"], 200)
        self.assertEqual(sent[1]["body"], b'{"status":"ok"}')
        self.assertFalse(forwarded)
        sent, _ = asyncio.run(invoke("/healthz", method="HEAD"))
        self.assertEqual(sent[1]["body"], b"")

    def test_unpublished_paths_are_not_forwarded(self):
        for path in ("/", "/mcp/", "/admin", "/healthz/private"):
            sent, forwarded = asyncio.run(invoke(path))
            self.assertEqual(sent[0]["status"], 404)
            self.assertFalse(forwarded)

    def test_lifespan_is_forwarded(self):
        called = []
        async def app(scope, receive, send):
            called.append(scope["type"])
        asyncio.run(BearerGate(app, TOKEN)({"type": "lifespan"}, None, None))
        self.assertEqual(called, ["lifespan"])


class SDKSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if importlib.util.find_spec("mcp") is None or importlib.util.find_spec("psycopg") is None:
            raise unittest.SkipTest("Install project dependencies for SDK smoke tests")

    def test_sdk_initialize_and_only_read_tools(self):
        import os
        from unittest.mock import patch
        from starlette.testclient import TestClient
        from mcp_server.http_server import create_app
        env = {"MCP_API_TOKEN": TOKEN, "MCP_PUBLIC_URL": "https://stocks.example.com/mcp",
               "MCP_RO_DATABASE_URL": "postgresql://mcp_ro:unused@localhost/unused"}
        with patch.dict(os.environ, env):
            with TestClient(create_app(), base_url="https://stocks.example.com") as client:
                headers = {"Authorization": "Bearer " + TOKEN,
                           "Accept": "application/json, text/event-stream"}
                result = client.post("/mcp", headers=headers, json={
                    "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                        "protocolVersion": "2025-03-26", "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1"}}})
                self.assertEqual(result.status_code, 200)
                self.assertIn("result", result.json())
                tools = client.post("/mcp", headers=headers,
                                    json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
                self.assertEqual(tools.status_code, 200)
                advertised = tools.json()["result"]["tools"]
                self.assertEqual({t["name"] for t in advertised},
                                 {"get_snapshot", "query_history", "screen_tickers"})
                self.assertTrue(all(t["annotations"]["readOnlyHint"] for t in advertised))
                self.assertEqual(client.post("/mcp", json={}).status_code, 401)
                bad_origin = dict(headers, Origin="https://untrusted.example")
                self.assertEqual(client.post("/mcp", headers=bad_origin, json={}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
