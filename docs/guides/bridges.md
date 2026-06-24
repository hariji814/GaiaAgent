# Bridge Integration Guide / 桥接集成指南

> **[← Back to README](../../README.md)** | [Architecture](../architecture.md) | [Bridge Developer Guide](../architecture/bridge-guide.md) | [Protocol Spec](../../PROTOCOL.md)
>
> Connect AURC agents to MCP servers, A2A agents, and custom protocols
> 将 AURC Agent 连接到 MCP 服务器、A2A Agent 和自定义协议

---

## Table of Contents / 目录

1. [Overview / 概述](#overview--概述)
2. [MCP Bridge / MCP 桥接器](#mcp-bridge--mcp-桥接器)
3. [A2A Bridge / A2A 桥接器](#a2a-bridge--a2a-桥接器)
4. [ACP Bridge / ACP 桥接器](#acp-bridge--acp-桥接器)
5. [Building Custom Bridges / 构建自定义桥接器](#building-custom-bridges--构建自定义桥接器)
6. [Cross-Protocol Routing / 跨协议路由](#cross-protocol-routing--跨协议路由)
7. [Bridge Testing and Debugging / 桥接测试和调试](#bridge-testing-and-debugging--桥接测试和调试)

---

## Overview / 概述

Bridges are AURC's interoperability mechanism. Each bridge translates between AURC's canonical `AURCMessage` format and an external protocol.

桥接器是 AURC 的互操作机制。每个桥接器在 AURC 的标准 `AURCMessage` 格式和外部协议之间进行翻译。

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

### Bridge Lifecycle / 桥接器生命周期

1. **Register** bridge with `BridgeRegistry` / 向 `BridgeRegistry` 注册桥接器
2. **Register** forwarder with `MessageRouter` / 向 `MessageRouter` 注册转发函数
3. **Translate** incoming external messages to `AURCMessage` / 将外部消息翻译为 `AURCMessage`
4. **Route** through the message bus / 通过消息总线路由
5. **Translate** outgoing AURC messages back to external format / 将 AURC 消息翻译回外部格式

---

## MCP Bridge / MCP 桥接器

The MCP Bridge translates between MCP's JSON-RPC 2.0 protocol and AURC messages.

MCP 桥接器在 MCP 的 JSON-RPC 2.0 协议和 AURC 消息之间进行翻译。

### Creating an MCP Bridge / 创建 MCP 桥接器

```python
from gaiaagent.bridges.base import MCPBridge, BridgeRegistry

# Create and register / 创建并注册
mcp_bridge = MCPBridge()
registry = BridgeRegistry()
registry.register(mcp_bridge)

print(mcp_bridge.source_protocol)  # "mcp/2025-06-18"
```

### Translating MCP → AURC / 翻译 MCP → AURC

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

### Supported MCP Methods / 支持的 MCP 方法

| MCP Method | AURC Type | AURC Body Method |
|---|---|---|
| `tools/call` | `request` | `"invoke"` |
| `tools/list` | `request` | `"list_capabilities"` |
| `resources/read` | `request` | `"load_context"` |
| `initialize` | `notification` | event: `"mcp_server_initialized"` |
| (other) | `request` | (method name as-is) |

### Translating AURC → MCP / 翻译 AURC → MCP

```python
from gaiaagent.core.message import AURCMessage, MessageBody
from gaiaagent.core.types import MessageDirection

# Create an AURC request / 创建 AURC 请求
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

### MCP Capability Mapping / MCP 能力映射

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

## A2A Bridge / A2A 桥接器

The A2A Bridge translates between Google's Agent-to-Agent protocol and AURC.

A2A 桥接器在 Google 的 Agent-to-Agent 协议和 AURC 之间进行翻译。

### Creating an A2A Bridge / 创建 A2A 桥接器

```python
from gaiaagent.bridges.a2a import A2ABridge

a2a_bridge = A2ABridge()
registry.register(a2a_bridge)

print(a2a_bridge.source_protocol)  # "a2a/1.0"
```

### Translating A2A → AURC / 翻译 A2A → AURC

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

### Supported A2A Methods / 支持的 A2A 方法

| A2A Method | AURC Type | Description / 描述 |
|---|---|---|
| `tasks/send` | `delegation` | New task delegation / 新任务委派 |
| `tasks/sendSubscribe` | `delegation` | Delegation with streaming / 带流式的委派 |
| `tasks/get` | `request` | Task status query / 任务状态查询 |
| `tasks/cancel` | `notification` | Task cancellation / 任务取消 |
| `tasks/pushNotification/set` | `notification` | Push notification config / 推送通知配置 |

### Translating AURC → A2A / 翻译 AURC → A2A

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

### A2A Agent Card Conversion / A2A Agent Card 转换

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

### A2A Task State Mapping / A2A 任务状态映射

| AURC Event | A2A State |
|---|---|
| `task_started` | `working` |
| `task_paused` | `input-required` |
| `task_completed` | `completed` |
| `task_failed` | `failed` |
| `task_cancelled` | `canceled` |

---

## ACP Bridge / ACP 桥接器

GaiaAgent ships a built-in **ACPBridge** (`gaiaagent.bridges.acp`) that translates between IBM's ACP (Agent Communication Protocol) and AURC. ACP is a lightweight, HTTP-native protocol that uses a simple JSON envelope (not JSON-RPC) with method-based dispatch.

GaiaAgent 内置 **ACPBridge**（`gaiaagent.bridges.acp`），在 IBM 的 ACP（Agent Communication Protocol）与 AURC 之间翻译。ACP 是一个轻量级、HTTP 原生的协议，使用简单的 JSON 信封（非 JSON-RPC）进行基于方法的分发。

### Creating an ACP Bridge / 创建 ACP 桥接器

```python
from gaiaagent.bridges.acp import ACPBridge
from gaiaagent.bridges.base import BridgeRegistry

acp_bridge = ACPBridge()
registry = BridgeRegistry()
registry.register(acp_bridge)

print(acp_bridge.source_protocol)  # "acp/1.0"
```

### Translating ACP → AURC / 翻译 ACP → AURC

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

### Supported ACP Methods / 支持的 ACP 方法

| ACP Method | AURC Type | Description / 描述 |
|---|---|---|
| `invoke` | `delegation` | Agent invocation — primary work entry / Agent 调用，主要工作入口 |
| `cancel` | `notification` | Cancel a running task / 取消运行中的任务 |
| `get-task` | `request` | Query task status / 查询任务状态 |
| `list-tasks` | `request` | List tasks with filtering / 列出任务（可过滤） |
| `set-task` | `notification` | Update task state directly / 直接更新任务状态 |

### Translating AURC → ACP / 翻译 AURC → ACP

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

AURC `response` 映射为 ACP `completed`/`failed` 结果，`stream` 映射为 ACP 流式更新，`notification` 映射为 ACP 通知事件（`task.started`、`task.completed` 等）。

### ACP Agent Descriptor Conversion / ACP Agent 描述符转换

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

> **Note / 说明:** The template below remains useful as a reference for bridges whose semantics differ from ACP's. For ACP itself, prefer the built-in `ACPBridge`.
>
> **说明：** 下方模板对于语义与 ACP 不同的桥接器仍有参考价值。对于 ACP 本身，请优先使用内置 `ACPBridge`。

---

## Building Custom Bridges / 构建自定义桥接器

### Step-by-Step Tutorial / 分步教程

Let's build a bridge for a hypothetical "Slack" protocol.

让我们为一个假设的 "Slack" 协议构建桥接器。

**Step 1: Define the Bridge Class / 步骤 1：定义桥接器类**

```python
from gaiaagent.core.message import AURCMessage, BridgeContext, MessageBody
from gaiaagent.core.types import MessageDirection

class SlackBridge:
    """Slack ↔ AURC Bridge / Slack ↔ AURC 桥接器"""

    @property
    def source_protocol(self) -> str:
        return "slack/1.0"

    def can_bridge(self, source: str, target: str) -> bool:
        return (source == "slack/1.0" and target == "aurc/0.1") or \
               (source == "aurc/0.1" and target == "slack/1.0")
```

**Step 2: Implement translate_to_aurc / 步骤 2：实现 translate_to_aurc**

```python
    async def translate_to_aurc(self, slack_event: dict) -> AURCMessage:
        """Slack event → AURC message / Slack 事件 → AURC 消息"""
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

        # Fallback for other event types / 其他事件类型的兜底
        return AURCMessage(
            source=f"slack:event/{event_type}",
            target="aurc:local/slack-handler",
            type=MessageDirection.NOTIFICATION,
            body=MessageBody(event=f"slack_{event_type}", data=slack_event),
            protocol_context=bridge_ctx,
        )
```

**Step 3: Implement translate_from_aurc / 步骤 3：实现 translate_from_aurc**

```python
    async def translate_from_aurc(self, aurc_message: AURCMessage) -> dict:
        """AURC message → Slack message / AURC 消息 → Slack 消息"""
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

**Step 4: Implement map_capabilities / 步骤 4：实现 map_capabilities**

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

**Step 5: Register and Use / 步骤 5：注册并使用**

```python
from gaiaagent.bridges.base import BridgeRegistry
from gaiaagent.bus.router import MessageRouter

# Register bridge / 注册桥接器
registry = BridgeRegistry()
registry.register(SlackBridge())

# Register forwarder with router / 向路由器注册转发函数
router = MessageRouter()

async def forward_to_slack(msg: AURCMessage):
    slack_bridge = registry.get_bridge("slack/1.0")
    slack_msg = await slack_bridge.translate_from_aurc(msg)
    # Send via Slack API / 通过 Slack API 发送
    print(f"Sending to Slack: {slack_msg}")

router.register_bridge_forwarder("slack", forward_to_slack)
```

---

## Cross-Protocol Routing / 跨协议路由

AURC's MessageRouter can route messages across protocol boundaries transparently.

AURC 的 MessageRouter 可以透明地跨协议边界路由消息。

### Example: Orchestrating MCP + A2A Agents / 示例：编排 MCP + A2A Agent

```python
from gaiaagent.bus.router import MessageRouter
from gaiaagent.bridges.base import MCPBridge, BridgeRegistry
from gaiaagent.bridges.a2a import A2ABridge
from gaiaagent.core.message import AURCMessage, MessageBody
from gaiaagent.core.types import MessageDirection

# Setup / 设置
registry = BridgeRegistry()
registry.register(MCPBridge())
registry.register(A2ABridge())

router = MessageRouter()

# Register bridge forwarders / 注册桥接转发函数
async def forward_to_mcp(msg):
    bridge = registry.get_bridge("mcp/2025-06-18")
    mcp_msg = await bridge.translate_from_aurc(msg)
    # Send to MCP server... / 发送到 MCP 服务器...
    return {"status": "sent_to_mcp"}

async def forward_to_a2a(msg):
    bridge = registry.get_bridge("a2a/1.0")
    a2a_msg = await bridge.translate_from_aurc(msg)
    # Send to A2A agent... / 发送到 A2A Agent...
    return {"status": "sent_to_a2a"}

router.register_bridge_forwarder("mcp", forward_to_mcp)
router.register_bridge_forwarder("a2a", forward_to_a2a)

# Register a local AURC agent handler / 注册本地 AURC Agent 处理函数
async def handle_local(msg):
    return {"status": "processed_locally", "skill": msg.body.skill}

router.register_handler("aurc:gaia/researcher:v1.0", handle_local)

# Route to different protocols / 路由到不同协议
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

# All three route correctly based on target prefix / 三者都根据目标前缀正确路由
await router.route(msg_mcp)    # → MCP bridge forwarder
await router.route(msg_a2a)    # → A2A bridge forwarder
await router.route(msg_local)  # → Direct local handler
```

### Group/Broadcast Routing / 组播路由

```python
# Subscribe to a group / 订阅组
async def on_broadcast(msg):
    print(f"Broadcast received: {msg.body.event}")

router.subscribe("aurc:group/researchers", on_broadcast)

# Send to group / 发送到组
broadcast_msg = AURCMessage(
    source="aurc:gaia/orchestrator:v1.0",
    target="aurc:group/researchers",
    type=MessageDirection.NOTIFICATION,
    body=MessageBody(event="new_task_available", data={"topic": "AI safety"}),
)
await router.route(broadcast_msg)  # Delivered to all subscribers
```

---

## Bridge Testing and Debugging / 桥接测试和调试

### Unit Testing a Bridge / 桥接器单元测试

```python
import asyncio
from gaiaagent.bridges.base import MCPBridge
from gaiaagent.core.types import MessageDirection

async def test_mcp_bridge():
    bridge = MCPBridge()

    # Test tools/call translation / 测试工具调用翻译
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

    # Test reverse translation / 测试反向翻译
    mcp_result = await bridge.translate_from_aurc(aurc_msg)
    assert mcp_result["method"] == "tools/call"
    assert mcp_result["params"]["name"] == "calculator"

    print("All bridge tests passed! / 所有桥接测试通过!")

asyncio.run(test_mcp_bridge())
```

### Debugging Tips / 调试技巧

**1. Inspect Bridge Context / 检查桥接上下文**

```python
# Check how many protocol hops a message has traversed / 检查消息经过了多少协议跳数
msg = await bridge.translate_to_aurc(external_msg)
print(f"Hop count: {msg.protocol_context.hop_count}")
print(f"Is bridged: {msg.protocol_context.is_bridged}")
print(f"Bridge chain: {msg.protocol_context.bridge_chain}")
```

**2. Test Capability Mapping / 测试能力映射**

```python
# Verify capability mapping is correct / 验证能力映射是否正确
external_caps = [{"name": "search", "description": "Web search"}]
aurc_skills = await bridge.map_capabilities(external_caps)
for skill in aurc_skills:
    print(f"  Skill: {skill['skill_id']} — {skill['description']}")
```

**3. Use the BridgeRegistry for discovery / 使用 BridgeRegistry 发现**

```python
registry = BridgeRegistry()
registry.register(MCPBridge())
registry.register(A2ABridge())

# List available protocols / 列出可用协议
print(f"Protocols: {registry.list_protocols()}")
print(f"Bridge count: {registry.count}")

# Find bridge for protocol pair / 查找协议对的桥接器
bridge = registry.find_bridge("mcp/2025-06-18", "aurc/0.1")
print(f"Found bridge: {bridge.source_protocol if bridge else 'None'}")
```

**4. Monitor Router Statistics / 监控路由器统计**

```python
# Check routing stats after processing messages / 处理消息后检查路由统计
stats = router.stats.to_dict()
print(f"Total routed: {stats['total_routed']}")
print(f"Direct: {stats['direct']}")
print(f"Bridged: {stats['bridged']}")
print(f"Broadcast: {stats['broadcast']}")
print(f"Dead lettered: {stats['dead_lettered']}")
print(f"Errors: {stats['errors']}")

# Check dead letter queue / 检查死信队列
dead = router.dead_letter_queue
if dead:
    for msg in dead:
        print(f"Dead letter: {msg.source} → {msg.target} ({msg.body.method})")
```

**5. Correlation Tracking / 关联追踪**

Use `correlation_id` to trace messages across protocol boundaries:

```python
# Set correlation_id on the original message / 在原始消息上设置关联 ID
original_msg = AURCMessage(
    source="aurc:gaia/orchestrator:v1.0",
    target="mcp:tool/server",
    type=MessageDirection.REQUEST,
    correlation_id="corr-trace-001",  # Track across boundaries / 跨边界追踪
    body=MessageBody(method="invoke", skill="web-search"),
)

# After bridging, the correlation_id is preserved / 桥接后，关联 ID 保持不变
bridged_msg = await mcp_bridge.translate_to_aurc(mcp_response)
assert bridged_msg.correlation_id == "corr-trace-001"
```

---

*See also / 另请参阅: [Architecture Deep Dive](../architecture.md) | [Security Guide](security.md) | [API Reference](../api-reference.md)*
