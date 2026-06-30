# Bridge Integration Guide

> 🌐 [中文版](../../zh/guides/bridges.md)
> **[← Back to README](../../../README.md)** | [Architecture](../architecture.md) | [Bridge Developer Guide](../architecture/bridge-guide.md) | [Protocol Spec](../../../PROTOCOL.md)
>
> Connect AURC agents to MCP servers, A2A agents, and custom protocols

---

## Table of Contents

1. [Overview](#overview)
2. [MCP Bridge](#mcp-bridge)
3. [A2A Bridge](#a2a-bridge)
4. [ACP Bridge](#acp-bridge)
5. [Messaging Channel Bridges](#messaging-channel-bridges-slack--telegram)
6. [Building Custom Bridges](#building-custom-bridges)
7. [Cross-Protocol Routing](#cross-protocol-routing)
8. [Bridge Testing and Debugging](#bridge-testing-and-debugging)

---

## Overview

Bridges are AURC's interoperability mechanism. Each bridge translates between AURC's canonical `AURCMessage` format and an external protocol.

```
                        ┌──────────────────┐
                        │  AURC Message Bus │
                        │  (AURCMessage)    │
                        └────────┬─────────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
              ┌─────▼─────┐ ┌───▼───┐ ┌─────▼─────┐
              │MCPBridge  │ │A2A    │ │Custom     │
              │           │ │Bridge │ │Bridge     │
              └─────┬─────┘ └───┬───┘ └─────┬─────┘
                    │           │            │
              ┌─────▼─────┐ ┌───▼───┐ ┌─────▼─────┐
              │MCP Server │ │A2A    │ │Your       │
              │(JSON-RPC) │ │Agent  │ │Protocol   │
              └───────────┘ └───────┘ └───────────┘
```

### Bridge Lifecycle

1. **Register** bridge with `BridgeRegistry`
2. **Register** forwarder with `MessageRouter`
3. **Translate** incoming external messages to `AURCMessage`
4. **Route** through the message bus
5. **Translate** outgoing AURC messages back to external format

---

## MCP Bridge

The MCP Bridge translates between MCP's JSON-RPC 2.0 protocol and AURC messages.

### Creating an MCP Bridge

```python
from gaiaagent.bridges.base import MCPBridge, BridgeRegistry

# Create and register
mcp_bridge = MCPBridge()
registry = BridgeRegistry()
registry.register(mcp_bridge)

print(mcp_bridge.source_protocol)  # "mcp/2025-06-18"
```

### Translating MCP → AURC

MCP `tools/call` becomes an AURC `request`:

```python
mcp_message = {
    "jsonrpc": "2.0",
    "id": "req-1",
    "method": "tools/call",
    "params": {
        "name": "web-search",
        "arguments": {"query": "AI agent protocols", "limit": 10}
    }
}

aurc_msg = await mcp_bridge.translate_to_aurc(mcp_message)

print(aurc_msg.type)                  # MessageDirection.REQUEST
print(aurc_msg.body.method)           # "invoke"
print(aurc_msg.body.skill)            # "web-search"
print(aurc_msg.body.params["query"])  # "AI agent protocols"
print(aurc_msg.protocol_context.origin_protocol)  # "mcp/2025-06-18"
print(aurc_msg.protocol_context.bridge_chain)     # ["mcp→aurc"]
```

### Supported MCP Methods

| MCP Method | AURC Type | AURC Body Method |
|---|---|---|
| `tools/call` | `request` | `"invoke"` |
| `tools/list` | `request` | `"list_capabilities"` |
| `resources/read` | `request` | `"load_context"` |
| `initialize` | `notification` | event: `"mcp_server_initialized"` |
| (other) | `request` | (method name as-is) |

### Translating AURC → MCP

```python
from gaiaagent.core.message import AURCMessage, MessageBody
from gaiaagent.core.types import MessageDirection

# Create an AURC request
aurc_msg = AURCMessage(
    source="aurc:gaia/orchestrator:v1.0",
    target="mcp:web-search/server",
    type=MessageDirection.REQUEST,
    body=MessageBody(
        method="invoke",
        skill="web-search",
        params={"query": "AURC protocol", "limit": 5},
    ),
)

mcp_msg = await mcp_bridge.translate_from_aurc(aurc_msg)
# Result:
# {
#     "jsonrpc": "2.0",
#     "id": "...",
#     "method": "tools/call",
#     "params": {"name": "web-search", "arguments": {"query": "AURC protocol", "limit": 5}}
# }
```

### MCP Capability Mapping

Convert MCP tool declarations to AURC skills:

```python
mcp_tools = [
    {
        "name": "web-search",
        "description": "Search the web for information",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"}
            },
            "required": ["query"]
        }
    }
]

aurc_skills = await mcp_bridge.map_capabilities(mcp_tools)
# Returns:
# [{
#     "skill_id": "mcp:web-search",
#     "name": "web-search",
#     "description": "Search the web for information",
#     "input_schema": {...},
#     "tags": ["mcp-bridge"]
# }]
```

---

## A2A Bridge

The A2A Bridge translates between Google's Agent-to-Agent protocol and AURC.

### Creating an A2A Bridge

```python
from gaiaagent.bridges.a2a import A2ABridge

a2a_bridge = A2ABridge()
registry.register(a2a_bridge)

print(a2a_bridge.source_protocol)  # "a2a/1.0"
```

### Translating A2A → AURC

A2A `tasks/send` becomes an AURC `delegation`:

```python
a2a_message = {
    "jsonrpc": "2.0",
    "id": "task-req-1",
    "method": "tasks/send",
    "params": {
        "id": "task-001",
        "sessionId": "session-abc",
        "messages": [
            {
                "role": "user",
                "parts": [{"type": "text", "text": "Research quantum computing advances in 2026"}]
            }
        ]
    }
}

aurc_msg = await a2a_bridge.translate_to_aurc(a2a_message)

print(aurc_msg.type)              # MessageDirection.DELEGATION
print(aurc_msg.body.method)       # "invoke"
print(aurc_msg.body.skill)        # "research" (inferred from content)
print(aurc_msg.body.params["task_id"])      # "task-001"
print(aurc_msg.body.params["session_id"])   # "session-abc"
```

### Supported A2A Methods

| A2A Method | AURC Type | Description |
|---|---|---|
| `tasks/send` | `delegation` | New task delegation |
| `tasks/sendSubscribe` | `delegation` | Delegation with streaming |
| `tasks/get` | `request` | Task status query |
| `tasks/cancel` | `notification` | Task cancellation |
| `tasks/pushNotification/set` | `notification` | Push notification config |

### Translating AURC → A2A

```python
# AURC delegation → A2A tasks/send
aurc_delegation = AURCMessage(
    source="aurc:gaia/orchestrator:v1.0",
    target="a2a:external/expert-agent",
    type=MessageDirection.DELEGATION,
    body=MessageBody(
        method="invoke",
        skill="research",
        params={
            "task_id": "task-002",
            "session_id": "session-xyz",
            "content": "Analyze recent AI safety papers",
        },
    ),
)

a2a_msg = await a2a_bridge.translate_from_aurc(aurc_delegation)
# Result:
# {
#     "jsonrpc": "2.0",
#     "id": "...",
#     "method": "tasks/send",
#     "params": {
#         "id": "task-002",
#         "sessionId": "session-xyz",
#         "messages": [{"role": "user", "parts": [{"type": "text", "text": "..."}]}]
#     }
# }
```

### A2A Agent Card Conversion

Convert A2A Agent Cards to AURC Agent Descriptors:

```python
agent_card = {
    "name": "Expert Researcher",
    "description": "Deep research and analysis agent",
    "skills": [
        {"id": "research", "name": "Research", "description": "Deep research"},
        {"id": "analyze", "name": "Analyze", "description": "Data analysis"}
    ],
    "authentication": {"schemes": ["api_key"]}
}

aurc_descriptor = a2a_bridge.map_agent_card(agent_card)
# Returns dict with aurc_id, capabilities, protocols, etc.
```

### A2A Task State Mapping

| AURC Event | A2A State |
|---|---|
| `task_started` | `working` |
| `task_paused` | `input-required` |
| `task_completed` | `completed` |
| `task_failed` | `failed` |
| `task_cancelled` | `canceled` |

---

## ACP Bridge

GaiaAgent ships a built-in **ACPBridge** (`gaiaagent.bridges.acp`) that translates between IBM's ACP (Agent Communication Protocol) and AURC. ACP is a lightweight, HTTP-native protocol that uses a simple JSON envelope (not JSON-RPC) with method-based dispatch.

### Creating an ACP Bridge

```python
from gaiaagent.bridges.acp import ACPBridge
from gaiaagent.bridges.base import BridgeRegistry

acp_bridge = ACPBridge()
registry = BridgeRegistry()
registry.register(acp_bridge)

print(acp_bridge.source_protocol)  # "acp/1.0"
```

### Translating ACP → AURC

ACP `invoke` becomes an AURC `delegation`:

```python
acp_message = {
    "method": "invoke",
    "id": "acp-req-1",
    "params": {
        "agent_id": "acp-agent-01",
        "task": "Summarize the latest AI news",
        "input": {"topic": "AI agents"},
        "session_id": "session-acp-001",
    }
}

aurc_msg = await acp_bridge.translate_to_aurc(acp_message)

print(aurc_msg.type)              # MessageDirection.DELEGATION
print(aurc_msg.body.method)       # "invoke"
print(aurc_msg.body.skill)        # "summarize" (inferred from task)
print(aurc_msg.body.params["task"])        # "Summarize the latest AI news"
print(aurc_msg.body.params["session_id"])  # "session-acp-001"
print(aurc_msg.protocol_context.origin_protocol)  # "acp/1.0"
```

### Supported ACP Methods

| ACP Method | AURC Type | Description |
|---|---|---|
| `invoke` | `delegation` | Agent invocation — primary work entry |
| `cancel` | `notification` | Cancel a running task |
| `get-task` | `request` | Query task status |
| `list-tasks` | `request` | List tasks with filtering |
| `set-task` | `notification` | Update task state directly |

### Translating AURC → ACP

```python
from gaiaagent.core.message import AURCMessage, MessageBody
from gaiaagent.core.types import MessageDirection

aurc_delegation = AURCMessage(
    source="aurc:gaia/orchestrator:v1.0",
    target="acp:external/summarizer",
    type=MessageDirection.DELEGATION,
    body=MessageBody(
        method="invoke",
        skill="summarize",
        params={
            "agent_id": "acp-agent-01",
            "task": "Summarize the latest AI news",
            "input": {"topic": "AI agents"},
            "session_id": "session-acp-001",
        },
    ),
)

acp_msg = await acp_bridge.translate_from_aurc(aurc_delegation)
# {
#     "method": "invoke",
#     "id": "...",
#     "params": {"agent_id": "acp-agent-01", "task": "...", "input": {...}, "session_id": "..."}
# }
```

AURC `response` messages map to ACP `completed`/`failed` results, `stream` messages map to ACP streaming updates, and `notification` messages map to ACP notification events (`task.started`, `task.completed`, etc.).

### ACP Agent Descriptor Conversion

```python
acp_descriptor = {
    "name": "Summarizer",
    "description": "Summarization agent",
    "skills": [{"id": "summarize", "name": "Summarize", "description": "Summarize text"}],
    "authentication": {"methods": ["api_key"]},
}

aurc_descriptor = acp_bridge.map_agent_card(acp_descriptor)
# Returns dict with aurc_id, capabilities, protocols, auth, etc.
```

> **Note:** The template below remains useful as a reference for bridges whose semantics differ from ACP's. For ACP itself, prefer the built-in `ACPBridge`.

---

## Messaging Channel Bridges (Slack / Telegram)

The MCP / A2A / ACP bridges target *agent* protocols. GaiaAgent also ships
bridges for *messaging channels* -- chat surfaces where real users live -- so a
Slack workspace, a Telegram chat, or a Discord server can act as a first-class
AURC channel. This extends the "bridges, not walls" thesis to a protocol family
beyond agent RPC.

Each channel bridge comes in two halves, matching the MCP/A2A/ACP split:

- a **translator** (`SlackBridge` / `TelegramBridge` / `DiscordBridge`) that
  converts an external event to/from an `AURCMessage`, with no network dependency;
- a **sender** (`SlackSender` / `TelegramSender` / `DiscordSender`) that wraps
  the translator and adds connectivity -- it POSTs the translated payload and
  builds an AURC `response` from the reply.

### Slack Bridge

`SlackBridge` (`gaiaagent.bridges.slack`) translates between Slack's Events API
/ Web API and AURC. Inbound: `message` / `app_mention` -> AURC `notification`
(`event="channel.message"`); `slash_command` and `interactive` payloads -> AURC
`request` (`method="invoke"`); `url_verification` -> `url_verify`. Outbound:
AURC `notification` / `response` -> `chat.postMessage`; `stream` ->
`chat.update`. Slack `thread_ts` (or message `ts`) is carried as the AURC
`correlation_id`, so a whole thread maps to one trace.

```python
from gaiaagent.bridges import SlackBridge, SlackSender
from gaiaagent.bus.router import MessageRouter

bridge = SlackBridge()
sender = SlackSender(token="xoxb-...")  # pass client_factory= for tests

router = MessageRouter()
router.register_bridge_forwarder("slack", sender.forward)

# An inbound Slack event -> AURC; an AURC reply to slack:C123 -> chat.postMessage
```

`SlackSender` POSTs to `https://slack.com/api/<method>` with a Bearer token and
returns a `response` carrying the Slack result, or an `ErrorInfo`
(`slack_error` for `ok=false`, `transport_error` for network/HTTP failures).

### Telegram Bridge

`TelegramBridge` (`gaiaagent.bridges.telegram`) translates between the Telegram
Bot API and AURC. Inbound: a `message` with text -> AURC `notification`
(`event="channel.message"`), or an AURC `request` (`method="invoke"`) when the
text is a `/command`; `callback_query` (inline button) -> `request`;
`edited_message` -> `channel.message_edited`. Outbound: `notification` /
`response` -> `sendMessage`; `stream` -> `editMessageText` (in-place refresh),
all rendered with `parse_mode=Markdown`. Group `@bot` mentions and the
`/cmd@bot` suffix are stripped; `reply_to_message.message_id` (or the message
id) is the AURC `correlation_id`.

```python
from gaiaagent.bridges import TelegramBridge, TelegramSender
from gaiaagent.bus.router import MessageRouter

bridge = TelegramBridge(bot_username="mybot")  # strips @mybot in groups
sender = TelegramSender(token="123456:ABC-DEF")

router = MessageRouter()
router.register_bridge_forwarder("telegram", sender.forward)
```

`TelegramSender` POSTs to `https://api.telegram.org/bot<token>/<method>` (the
token rides in the URL path, per the Bot API) and maps `{"ok": true, "result":
...}` to an AURC `response`; `ok=false` becomes a `telegram_error`.

### Discord Bridge

`DiscordBridge` (`gaiaagent.bridges.discord`) translates between the Discord
Gateway / Bot API and AURC. Inbound: a gateway `MESSAGE_CREATE` becomes an AURC
`notification` (`event="channel.message"`) -- a DM when `guild_id` is absent, a
server `@mention` otherwise (the `<@id>` / `<@!id>` mention is stripped);
`MESSAGE_UPDATE` -> `channel.message_edited`; an `INTERACTION_CREATE` (slash
command) -> AURC `request` (`method="invoke"`), with `data.name` +
`data.options` carried as the skill and params. Outbound: `notification` /
`response` -> `createMessage`; `stream` -> `editMessage` (in-place refresh).
Reply correlation uses `message_reference.message_id` (or the message `id`) as
the AURC `correlation_id`, so a reply thread maps to one trace. The gateway
envelope `{"t": "...", "d": {...}}` is unwrapped; a bare dict is auto-detected
by shape.

```python
from gaiaagent.bridges import DiscordBridge, DiscordSender
from gaiaagent.bus.router import MessageRouter

bridge = DiscordBridge()
sender = DiscordSender(token="<bot token>")  # pass client_factory= for tests

router = MessageRouter()
router.register_bridge_forwarder("discord", sender.forward)
```

`DiscordSender` POSTs to `https://discord.com/api/v10/channels/<id>/messages`
with an `Authorization: Bot <token>` header and maps the reply to an AURC
`response`; a missing `id` becomes a `discord_error`, network/HTTP failures
become a `transport_error`. `editMessage` is a PATCH to the same path with the
message id appended.

### Channel Conformance

All three channel bridges satisfy the `ProtocolBridge` contract, so they register
with `BridgeRegistry` and stamp `bridge_chain` (`slack->aurc` / `telegram->aurc`
/ `discord->aurc`) exactly like the MCP/A2A/ACP bridges. Targets use the
`slack:` / `telegram:` / `discord:` prefixes, which `MessageRouter` routes to the
registered sender. Each ships a full round-trip test suite
(`tests/test_slack_bridge.py`, `tests/test_telegram_bridge.py`,
`tests/test_discord_bridge.py`) covering the contract, conformance invariants
(correlation propagation, idempotent inbound, bridge-chain stamping), outbound
rendering, and the sender translate -> POST -> build-response loop with an
injected fake client.
See `examples/e2e_channel_interop.py` for a runnable end-to-end demo: a
Slack mention, a Telegram `/command`, and a Discord DM all reach a real
`@aurc_agent` skill and are answered back in-channel, with correlation carried
across all three channel boundaries (no network; a fake client stands in for
the wire).


---

## Building Custom Bridges

### Step-by-Step Tutorial

Let's build a bridge for a hypothetical "Slack" protocol.

**Step 1: Define the Bridge Class**

```python
from gaiaagent.core.message import AURCMessage, BridgeContext, MessageBody
from gaiaagent.core.types import MessageDirection

class SlackBridge:
    """Slack ↔ AURC Bridge"""

    @property
    def source_protocol(self) -> str:
        return "slack/1.0"

    def can_bridge(self, source: str, target: str) -> bool:
        return (source == "slack/1.0" and target == "aurc/0.1") or \
               (source == "aurc/0.1" and target == "slack/1.0")
```

**Step 2: Implement translate_to_aurc**

```python
    async def translate_to_aurc(self, slack_event: dict) -> AURCMessage:
        """Slack event → AURC message"""
        bridge_ctx = BridgeContext(
            origin_protocol="slack/1.0",
            bridged_from="slack/1.0",
            bridge_chain=["slack→aurc"],
        )

        event_type = slack_event.get("type", "")
        text = slack_event.get("text", "")
        user = slack_event.get("user", "unknown")

        if event_type == "message":
            return AURCMessage(
                source=f"slack:user/{user}",
                target="aurc:local/slack-handler",
                type=MessageDirection.REQUEST,
                body=MessageBody(
                    method="invoke",
                    skill="process-message",
                    params={"text": text, "channel": slack_event.get("channel", "")},
                ),
                protocol_context=bridge_ctx,
            )

        # Fallback for other event types
        return AURCMessage(
            source=f"slack:event/{event_type}",
            target="aurc:local/slack-handler",
            type=MessageDirection.NOTIFICATION,
            body=MessageBody(event=f"slack_{event_type}", data=slack_event),
            protocol_context=bridge_ctx,
        )
```

**Step 3: Implement translate_from_aurc**

```python
    async def translate_from_aurc(self, aurc_message: AURCMessage) -> dict:
        """AURC message → Slack message"""
        body = aurc_message.body

        if aurc_message.type == MessageDirection.RESPONSE:
            return {
                "channel": body.metadata.get("channel", "general"),
                "text": str(body.result),
            }
        elif aurc_message.type == MessageDirection.NOTIFICATION:
            return {
                "channel": "alerts",
                "text": f"[{body.event}] {body.data}",
            }

        return {"text": str(body.result or body.data or "")}
```

**Step 4: Implement map_capabilities**

```python
    async def map_capabilities(self, slack_commands: list[dict]) -> list[dict]:
        return [
            {
                "skill_id": f"slack:{cmd.get('command', '')}",
                "name": cmd.get("command", ""),
                "description": cmd.get("description", ""),
                "tags": ["slack-bridge"],
            }
            for cmd in slack_commands
        ]
```

**Step 5: Register and Use**

```python
from gaiaagent.bridges.base import BridgeRegistry
from gaiaagent.bus.router import MessageRouter

# Register bridge
registry = BridgeRegistry()
registry.register(SlackBridge())

# Register forwarder with router
router = MessageRouter()

async def forward_to_slack(msg: AURCMessage):
    slack_bridge = registry.get_bridge("slack/1.0")
    slack_msg = await slack_bridge.translate_from_aurc(msg)
    # Send via Slack API
    print(f"Sending to Slack: {slack_msg}")

router.register_bridge_forwarder("slack", forward_to_slack)
```

---

## Cross-Protocol Routing

AURC's MessageRouter can route messages across protocol boundaries transparently.

### Example: Orchestrating MCP + A2A Agents

```python
from gaiaagent.bus.router import MessageRouter
from gaiaagent.bridges.base import MCPBridge, BridgeRegistry
from gaiaagent.bridges.a2a import A2ABridge
from gaiaagent.core.message import AURCMessage, MessageBody
from gaiaagent.core.types import MessageDirection

# Setup
registry = BridgeRegistry()
registry.register(MCPBridge())
registry.register(A2ABridge())

router = MessageRouter()

# Register bridge forwarders
async def forward_to_mcp(msg):
    bridge = registry.get_bridge("mcp/2025-06-18")
    mcp_msg = await bridge.translate_from_aurc(msg)
    # Send to MCP server...
    return {"status": "sent_to_mcp"}

async def forward_to_a2a(msg):
    bridge = registry.get_bridge("a2a/1.0")
    a2a_msg = await bridge.translate_from_aurc(msg)
    # Send to A2A agent...
    return {"status": "sent_to_a2a"}

router.register_bridge_forwarder("mcp", forward_to_mcp)
router.register_bridge_forwarder("a2a", forward_to_a2a)

# Register a local AURC agent handler
async def handle_local(msg):
    return {"status": "processed_locally", "skill": msg.body.skill}

router.register_handler("aurc:gaia/researcher:v1.0", handle_local)

# Route to different protocols
msg_mcp = AURCMessage(
    source="aurc:gaia/orchestrator:v1.0",
    target="mcp:web-search/server",
    type=MessageDirection.REQUEST,
    body=MessageBody(method="invoke", skill="web-search", params={"query": "AI"}),
)

msg_a2a = AURCMessage(
    source="aurc:gaia/orchestrator:v1.0",
    target="a2a:external/expert",
    type=MessageDirection.DELEGATION,
    body=MessageBody(method="invoke", skill="research", params={"task_id": "t1"}),
)

msg_local = AURCMessage(
    source="aurc:gaia/orchestrator:v1.0",
    target="aurc:gaia/researcher:v1.0",
    type=MessageDirection.REQUEST,
    body=MessageBody(method="invoke", skill="summarize", params={"text": "..."}),
)

# All three route correctly based on target prefix
await router.route(msg_mcp)    # → MCP bridge forwarder
await router.route(msg_a2a)    # → A2A bridge forwarder
await router.route(msg_local)  # → Direct local handler
```

### Group/Broadcast Routing

```python
# Subscribe to a group
async def on_broadcast(msg):
    print(f"Broadcast received: {msg.body.event}")

router.subscribe("aurc:group/researchers", on_broadcast)

# Send to group
broadcast_msg = AURCMessage(
    source="aurc:gaia/orchestrator:v1.0",
    target="aurc:group/researchers",
    type=MessageDirection.NOTIFICATION,
    body=MessageBody(event="new_task_available", data={"topic": "AI safety"}),
)
await router.route(broadcast_msg)  # Delivered to all subscribers
```

---

## Bridge Testing and Debugging

### Unit Testing a Bridge

```python
import asyncio
from gaiaagent.bridges.base import MCPBridge
from gaiaagent.core.types import MessageDirection

async def test_mcp_bridge():
    bridge = MCPBridge()

    # Test tools/call translation
    mcp_msg = {
        "jsonrpc": "2.0",
        "id": "test-1",
        "method": "tools/call",
        "params": {"name": "calculator", "arguments": {"expression": "2+2"}}
    }

    aurc_msg = await bridge.translate_to_aurc(mcp_msg)

    assert aurc_msg.type == MessageDirection.REQUEST
    assert aurc_msg.body.method == "invoke"
    assert aurc_msg.body.skill == "calculator"
    assert aurc_msg.body.params["expression"] == "2+2"
    assert aurc_msg.protocol_context.origin_protocol == "mcp/2025-06-18"
    assert "mcp→aurc" in aurc_msg.protocol_context.bridge_chain

    # Test reverse translation
    mcp_result = await bridge.translate_from_aurc(aurc_msg)
    assert mcp_result["method"] == "tools/call"
    assert mcp_result["params"]["name"] == "calculator"

    print("All bridge tests passed!")

asyncio.run(test_mcp_bridge())
```

### Debugging Tips

**1. Inspect Bridge Context**

```python
# Check how many protocol hops a message has traversed
msg = await bridge.translate_to_aurc(external_msg)
print(f"Hop count: {msg.protocol_context.hop_count}")
print(f"Is bridged: {msg.protocol_context.is_bridged}")
print(f"Bridge chain: {msg.protocol_context.bridge_chain}")
```

**2. Test Capability Mapping**

```python
# Verify capability mapping is correct
external_caps = [{"name": "search", "description": "Web search"}]
aurc_skills = await bridge.map_capabilities(external_caps)
for skill in aurc_skills:
    print(f"  Skill: {skill['skill_id']} — {skill['description']}")
```

**3. Use the BridgeRegistry for discovery**

```python
registry = BridgeRegistry()
registry.register(MCPBridge())
registry.register(A2ABridge())

# List available protocols
print(f"Protocols: {registry.list_protocols()}")
print(f"Bridge count: {registry.count}")

# Find bridge for protocol pair
bridge = registry.find_bridge("mcp/2025-06-18", "aurc/0.1")
print(f"Found bridge: {bridge.source_protocol if bridge else 'None'}")
```

**4. Monitor Router Statistics**

```python
# Check routing stats after processing messages
stats = router.stats.to_dict()
print(f"Total routed: {stats['total_routed']}")
print(f"Direct: {stats['direct']}")
print(f"Bridged: {stats['bridged']}")
print(f"Broadcast: {stats['broadcast']}")
print(f"Dead lettered: {stats['dead_lettered']}")
print(f"Errors: {stats['errors']}")

# Check dead letter queue
dead = router.dead_letter_queue
if dead:
    for msg in dead:
        print(f"Dead letter: {msg.source} → {msg.target} ({msg.body.method})")
```

**5. Correlation Tracking**

Use `correlation_id` to trace messages across protocol boundaries:

```python
# Set correlation_id on the original message
original_msg = AURCMessage(
    source="aurc:gaia/orchestrator:v1.0",
    target="mcp:tool/server",
    type=MessageDirection.REQUEST,
    correlation_id="corr-trace-001",  # Track across boundaries
    body=MessageBody(method="invoke", skill="web-search"),
)

# After bridging, the correlation_id is preserved
bridged_msg = await mcp_bridge.translate_to_aurc(mcp_response)
assert bridged_msg.correlation_id == "corr-trace-001"
```

---

*See also: [Architecture Deep Dive](../architecture.md) | [Security Guide](security.md) | [API Reference](../api-reference.md)*
