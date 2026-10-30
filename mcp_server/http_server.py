"""Read-only Streamable HTTP MCP server; leaves server.py (stdio) unchanged."""
from __future__ import annotations

import asyncio
import os
from urllib.parse import urlsplit

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from mcp_server.http_auth import BearerGate


def create_app():
    token = os.environ.get("MCP_API_TOKEN", "")
    # Validate the token before importing any application tools.
    BearerGate(None, token)
    url = urlsplit(os.environ.get("MCP_PUBLIC_URL", ""))
    if (url.scheme != "https" or not url.hostname or url.path != "/mcp"
            or url.username or url.password or url.query or url.fragment
            or "*" in url.netloc):
        raise ValueError("MCP_PUBLIC_URL must be https://your-host/mcp with no credentials, query or fragment")
    if not os.environ.get("MCP_RO_DATABASE_URL"):
        raise ValueError("MCP_RO_DATABASE_URL is required; use the mcp_ro database role")

    from mcp_server.tools.history import query_history_tool
    from mcp_server.tools.screen import screen_tickers_tool
    from mcp_server.tools.snapshot import get_snapshot_tool

    mcp = FastMCP(
        "vn-market-remote",
        instructions="Read-only Vietnamese market research from the local database. Data may be stale; "
                     "check dates and warnings. These tools do not refresh data or place trades.",
        stateless_http=True, json_response=True, streamable_http_path="/mcp",
        max_request_body_size=1048576,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[url.netloc, "localhost:8000", "127.0.0.1:8000"],
            allowed_origins=[f"https://{url.netloc}"],
        ),
    )
    annotations = ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                  idempotentHint=True, openWorldHint=False)

    @mcp.tool(annotations=annotations)
    async def get_snapshot(ticker: str | None = None, run_id: str | None = None) -> dict:
        """Read a saved snapshot. Provide exactly one of ticker or run_id; does not refresh data."""
        return await asyncio.to_thread(get_snapshot_tool,
                                       ticker=ticker.upper() if ticker else None, run_id=run_id)

    @mcp.tool(annotations=annotations)
    async def query_history(ticker: str, series: str, start_date: str, end_date: str) -> dict:
        """Read prices, fundamentals or foreign_flow for an inclusive date range (max 366 days).

        Dates are YYYY-MM-DD; larger histories require separate bounded calls.
        Returns data directly, never a path on the server.
        """
        from datetime import date
        start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
        if not 0 <= (end - start).days <= 365:
            raise ValueError("Date range must be ordered and no longer than 366 inclusive days")
        return await asyncio.to_thread(query_history_tool, ticker.upper(), series, start_date, end_date)

    @mcp.tool(annotations=annotations)
    async def screen_tickers(
        tickers: list[str] | None = None,
        candle_pattern: str | None = None,
        rsi_below: float | None = None,
        rsi_above: float | None = None,
        above_ma20: bool | None = None,
        above_ma50: bool | None = None,
        min_volume_ratio: float | None = None,
    ) -> dict:
        """Screen stored daily bars by RSI, moving averages, volume and bullish candles.

        Omit tickers to scan VN30. At most 100 explicit tickers. Results may be provisional.
        """
        if tickers is not None and not 1 <= len(tickers) <= 100:
            raise ValueError("Provide 1-100 tickers or omit tickers to scan VN30")
        return await asyncio.to_thread(
            screen_tickers_tool, tickers, candle_pattern=candle_pattern,
            rsi_below=rsi_below, rsi_above=rsi_above, above_ma20=above_ma20,
            above_ma50=above_ma50, min_volume_ratio=min_volume_ratio,
        )

    return BearerGate(mcp.streamable_http_app(), token)


def main():
    import uvicorn
    uvicorn.run(create_app(), host="127.0.0.1", port=8000,
                proxy_headers=False, access_log=False, limit_concurrency=32)


if __name__ == "__main__":
    main()
