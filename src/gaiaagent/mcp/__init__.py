"""AURC MCP server package — expose AURC @skill agents as MCP tools.
AURC MCP server 包 —— 把 AURC @skill agent 暴露为 MCP 工具

Run as a stdio server the `claude` CLI connects to via `--mcp-config`::

    python -m gaiaagent.mcp --agent myproj:ResearchAgent
"""

from .server import AURCMCPStdioServer, main

__all__ = ["AURCMCPStdioServer", "main"]
