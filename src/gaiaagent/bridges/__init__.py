"""Bridges module — Protocol adapters for MCP, A2A, ACP.
协议桥接模块 — MCP、A2A、ACP 协议适配器
"""

from gaiaagent.bridges.base import BridgeRegistry, MCPBridge, ProtocolBridge
from gaiaagent.bridges.a2a import A2ABridge
from gaiaagent.bridges.acp import ACPBridge

__all__ = [
    "BridgeRegistry",
    "MCPBridge",
    "A2ABridge",
    "ACPBridge",
    "ProtocolBridge",
]
