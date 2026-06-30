"""Bridges module — Protocol adapters for MCP, A2A, ACP.
协议桥接模块 — MCP、A2A、ACP 协议适配器
"""

from gaiaagent.bridges.a2a import A2ABridge
from gaiaagent.bridges.acp import ACPBridge
from gaiaagent.bridges.base import BridgeRegistry, MCPBridge, ProtocolBridge
from gaiaagent.bridges.discord import DISCORD_PROTOCOL, DiscordBridge
from gaiaagent.bridges.discord_sender import DiscordSender
from gaiaagent.bridges.slack import SLACK_PROTOCOL, SlackBridge
from gaiaagent.bridges.slack_sender import SlackSender
from gaiaagent.bridges.telegram import TELEGRAM_PROTOCOL, TelegramBridge
from gaiaagent.bridges.telegram_sender import TelegramSender

__all__ = [
    "BridgeRegistry",
    "MCPBridge",
    "A2ABridge",
    "ACPBridge",
    "DiscordBridge",
    "DiscordSender",
    "DISCORD_PROTOCOL",
    "SlackBridge",
    "SlackSender",
    "SLACK_PROTOCOL",
    "TelegramBridge",
    "TelegramSender",
    "TELEGRAM_PROTOCOL",
    "ProtocolBridge",
]
