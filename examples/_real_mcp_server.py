"""A real MCP server used by the cross-process interop demo.

This is a genuine MCP server built on the OFFICIAL Anthropic ``mcp`` SDK
(FastMCP, stdio transport). The e2e_mcp_a2a_interop demo spawns it as a
grandchild process and reaches it via the official ClientSession, so the
arithmetic in the demo is computed inside a real MCP server -- not by AURC.

Run standalone (stdio):
    python examples/_real_mcp_server.py
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("calc")


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


if __name__ == "__main__":
    mcp.run(transport="stdio")
