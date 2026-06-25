# 架构深度解析

> 🌐 [English](../en/architecture.md)
> **[← 返回 README](../../README.zh.md)** | [协议规范](../../PROTOCOL.zh.md) | [API 参考](api-reference.md) | [快速开始](guides/quickstart.md)
>
> AURC 协议架构全面指南 — AI Agent 通信领域首个完整的 8 层协议栈。

---

## 目录

1. [设计哲学](#设计哲学)
2. [分层架构](#分层架构)
3. [L0：传输层](#l0传输层)
4. [L1：Agent 身份](#l1agent-身份)
5. [L2：运行时 Harness](#l2运行时-harness)
6. [L3：统一消息总线](#l3统一消息总线)
7. [L4：协议桥接层](#l4协议桥接层)
8. [L5：上下文关联层](#l5上下文关联层)
9. [L6：安全层](#l6安全层)
10. [L7：发现层](#l7发现层)
11. [数据流图](#数据流图)
12. [状态机详解](#状态机详解)
13. [异步模型](#异步模型)
14. [扩展点](#扩展点)

---

## 设计哲学

AURC 基于五大核心设计原则：

| # | 原则 | 理由 |
|---|---|---|
| 1 | **桥接优先** | 不重新发明通信原语，统一现有协议 |
| 2 | **运行时为核心** | Agent = 模型 + Harness；Harness 是一等公民 |
| 3 | **渐进复杂度** | 简单核心，企业功能作为可选模块 |
| 4 | **协议无关身份** | 一个 Agent，跨所有协议的统一身份 |
| 5 | **安全第一** | 权限可在协议层面强制执行 |

### AURC 为什么存在

2025–2026 年的 AI Agent 生态系统产生了若干协议，各自只解决某一层的问题：

- **MCP**（Anthropic）：Agent 到工具的通信
- **A2A**（Google）：Agent 到 Agent 的委托
- **ACP**（IBM）：轻量级 REST 消息传递

**问题：** 没有任何单一方案能够桥接这些协议或提供 Agent 生命周期管理。使用 MCP 调用工具的 Agent 无法无缝委托给 A2A Agent，而这两个协议都不管理 Agent 状态、错误恢复或上下文持久化。

**AURC 解决了这个问题** —— 通过在现有协议之上分层（而非替代），增加运行时生命周期、安全以及跨协议上下文追踪能力。

---

## 分层架构

AURC 使用 8 层模型（L0–L7）。每一层都可以独立测试和替换。

```
┌──────────────────────────────────────────────────────────────────────┐
│ L7  发现层                                                            │
│     Agent 注册中心、能力匹配、健康路由                                    │
├──────────────────────────────────────────────────────────────────────┤
│ L6  安全层                                                            │
│     API Key / JWT 认证、CapABAC 授权引擎、委托链验证、审计日志            │
├──────────────────────────────────────────────────────────────────────┤
│ L5  上下文关联层                                                       │
│     多作用域上下文存储、关联 ID、桥接链追踪                                │
├──────────────────────────────────────────────────────────────────────┤
│ L4  协议桥接层                                                         │
│     MCPBridge  — MCP JSON-RPC ↔ AURC                                │
│     A2ABridge  — A2A tasks/send ↔ AURC                              │
│     ACPBridge  — ACP REST envelope ↔ AURC                           │
│     BridgeRegistry — 管理所有桥接器                                     │
├──────────────────────────────────────────────────────────────────────┤
│ L3  统一消息总线                                                       │
│     AURCMessage（标准消息格式）                                       │
│     MessageRouter（direct/bridge/broadcast/dead-letter）              │
│     SessionManager（会话管理）                                        │
├──────────────────────────────────────────────────────────────────────┤
│ L2  运行时 Harness                                                    │
│     RuntimeHarness（生命周期状态机）                                   │
│     AgentInstance（每个 Agent 的状态包装）                             │
│     RecoveryPolicy（错误恢复策略）                                    │
│     ContextStore（多作用域内存）                                      │
├──────────────────────────────────────────────────────────────────────┤
│ L1  Agent 身份                                                        │
│     AURCId（URN 格式 ID 解析）                                       │
│     AgentDescriptor（身份描述文档）                                   │
│     Capabilities, ProtocolSupport, AuthDeclaration                  │
├──────────────────────────────────────────────────────────────────────┤
│ L0  传输层                                                            │
│     HTTPTransportServer / HTTPTransportClient（HTTP/2 + ASGI）       │
│     WebSocketTransportServer / WebSocketTransportClient             │
│     stdio（标准输入输出，本地开发）                                    │
└──────────────────────────────────────────────────────────────────────┘
```

### 层依赖规则

每一层只能依赖其下方的层。这确保了清晰的分离：

- L7（发现层）可查询 L2（Harness）的健康状态，使用 L6（安全层）做认证
- L4（桥接层）产生 L3（消息）但不管理生命周期（L2）
- L0（传输层）与协议无关 —— 它搬运的是字节，而非语义

---

## L0：传输层

传输层负责通过网络传递原始消息。

### 支持的传输方式

| 传输方式 | 用例 | 状态 |
|-----------|----------|--------|
| HTTP/2（ASGI + uvicorn） | 生产环境，跨网络 | Implemented |
| WebSocket | 实时双向 | Implemented |
| stdio | 本地开发，CLI 工具 | Interface only |
| gRPC | 高性能内部 | Planned |

### HTTP 传输架构

```
┌─────────────────┐     HTTP POST /aurc      ┌─────────────────┐
│  AURC Agent A   │ ────────────────────────→ │  HTTPTransport  │
│  (Client)       │ ←──────────────────────── │  Server         │
│                 │     JSON response          │  (ASGI/uvicorn) │
└─────────────────┘                            └────────┬────────┘
                                                        │
                                                  routes to
                                                        │
                                                 ┌──────▼──────┐
                                                 │  Message    │
                                                 │  Router     │
                                                 └─────────────┘
```

**端点：**
- `POST /aurc` —— 发送 AURC 消息
- `GET /health` —— 健康检查

---

## L1：Agent 身份

身份层提供全局唯一、人类可读的 Agent 标识。

### AURC ID 格式

```
aurc:{namespace}/{agent_name}:{version}

示例：
  aurc:gaia/researcher:v1.2
  aurc:mycompany/code-reviewer:v2.0
  aurc:community/translator:v1.0
```

**设计理由：**
- URN 风格比 DID 更简单（无需区块链依赖）
- 命名空间提供去中心化唯一性（类似 Docker Hub）
- 版本固定确保可复现性
- 支持通配符匹配用于路由

**关键类：`AURCId`** —— 通过正则解析并校验该格式，支持通过 `matches()` 做通配匹配：

```python
aurc_id = AURCId.parse("aurc:gaia/researcher:v1.2")
print(aurc_id.namespace)  # "gaia"
print(aurc_id.name)       # "researcher"
print(aurc_id.version)    # "v1.2"
aurc_id.matches("aurc:gaia/*")  # True
```

### Agent 描述文档

`AgentDescriptor` 是身份文档 —— 以下内容的单一真相来源：

1. Agent 是**谁**（身份）
2. 能做**什么**（能力/技能）
3. **如何**通信（协议）
4. **需要**什么（运行时需求）
5. **如何**认证（安全）

```
┌─────────────────────────────────────────┐
│ AgentDescriptor                         │
├─────────────────────────────────────────┤
│ aurc_id: "aurc:gaia/researcher:v1.2"   │
│ display_name: "Research Agent"          │
│ version: "1.2.0"                        │
├─────────────────────────────────────────┤
│ capabilities:                           │
│   provides: [deep-research, summarize]  │
│   consumes: [web-search]                │
├─────────────────────────────────────────┤
│ protocols:                              │
│   native: "aurc/0.1"                    │
│   bridges: ["mcp/2025-06-18","a2a/1.0"]│
├─────────────────────────────────────────┤
│ runtime:                                │
│   max_concurrency: 10                   │
│   supports_streaming: true              │
│   timeout_seconds: 3600                 │
├─────────────────────────────────────────┤
│ auth:                                   │
│   methods: ["api_key", "oauth2"]        │
│   scopes: ["research:read"]             │
└─────────────────────────────────────────┘
```

---

## L2：运行时 Harness

这是 AURC 的**核心创新** —— MCP、A2A 和 ACP 都不提供 Agent 生命周期管理。

### 组件

```
┌────────────────────────────────────────────────────────────┐
│ RuntimeHarness                                             │
│                                                            │
│  _agents: { agent_id → AgentInstance }                     │
│  _listeners: [StateListener, ...]                          │
│  _recovery_policy: RecoveryPolicy                          │
│  _resource_limits: ResourceLimits                          │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ AgentInstance（每个 Agent 的实例）                     │  │
│  │  - descriptor: AgentDescriptor                       │  │
│  │  - state: AgentState (current)                       │  │
│  │  - _state_history: [(state, timestamp), ...]         │  │
│  │  - metrics: ResourceMetrics                          │  │
│  │  - _pause_event: asyncio.Event                       │  │
│  │  - _retry_count: int                                 │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

### 错误恢复

```
Error occurs → FAILING state → check RecoveryPolicy
    │
    ├─ retry_count > max_retries? → FAILED (terminal)
    │
    └─ within limits → RECOVERING state
         │
         ├─ RETRY_WITH_BACKOFF: sleep(1s → 5s → 15s), then READY
         ├─ RETRY_ALTERNATIVE: try different skill, then READY
         ├─ COMPACT_AND_RETRY: summarize context, then READY
         ├─ REFRESH_AND_RETRY: refresh auth credentials, then READY
         ├─ ESCALATE: send to human operator
         └─ FAIL: transition to FAILED
```

---

## L3：统一消息总线

消息总线是 AURC 的中枢神经系统。所有通信都以 `AURCMessage` 流经它。

### AURCMessage 结构

```
┌──────────────────────────────────────────────────────────┐
│ AURCMessage                                              │
├──────────────────────────────────────────────────────────┤
│ aurc_version: "0.1"                                      │
│ message_id: "msg-a1b2c3d4e5f6"                           │
│ correlation_id: "corr-xyz-789"   ← cross-protocol       │
│ trace_id: "trace-dist-456"       ← distributed tracing   │
│ timestamp: 2026-06-24T10:30:00Z                          │
├──────────────────────────────────────────────────────────┤
│ source: "aurc:gaia/orchestrator:v1.0"                    │
│ target: "aurc:gaia/researcher:v1.2"                      │
│ type: request | response | notification | stream |       │
│       delegation | handoff | heartbeat                   │
├──────────────────────────────────────────────────────────┤
│ body: MessageBody                                        │
│   method, skill, params, result, error, ...              │
├──────────────────────────────────────────────────────────┤
│ protocol_context: BridgeContext                          │
│   origin_protocol, bridged_from, bridge_chain            │
├──────────────────────────────────────────────────────────┤
│ session: SessionInfo  |  routing: RoutingInfo            │
│ security: MessageSecurity                                │
└──────────────────────────────────────────────────────────┘
```

### MessageRouter 流程

```
AURCMessage arrives
    │
    ├─ TTL check: ttl_hops <= 0? → drop
    │
    ├─ 1. Direct routing: target in _handlers → call handler
    │
    ├─ 2. Bridge routing: target starts with "mcp:"/"a2a:"/"acp:"
    │     → forward via _bridge_forwarders
    │
    ├─ 3. Group routing: target starts with "aurc:group/"
    │     → broadcast to _subscriptions
    │
    ├─ 4. Wildcard routing: pattern contains "*"
    │     → match and forward
    │
    └─ 5. Dead letter queue: no route found (max 100)
```

---

## L4：协议桥接层

桥接器是关键互操作机制。它们在 AURC 的标准 `AURCMessage` 格式和外部协议之间进行翻译。

### 桥接器接口

每个桥接器都必须实现 `ProtocolBridge` 协议：

```python
class ProtocolBridge(Protocol):
    source_protocol: str          # 例如 "mcp/2025-06-18"
    def can_bridge(src, tgt) -> bool
    async def translate_to_aurc(msg) -> AURCMessage
    async def translate_from_aurc(msg) -> ExternalMessage
    async def map_capabilities(caps) -> list[AURCCapability]
```

### MCP 桥接映射

```
MCP JSON-RPC              AURC Message
─────────────              ────────────
tools/call        ──→      request (method="invoke", skill=tool_name)
tools/list        ──→      request (method="list_capabilities")
resources/read    ──→      request (method="load_context")
initialize        ──→      notification (event="mcp_server_initialized")

AURC request      ──→      tools/call (if method="invoke")
AURC response     ──→      JSON-RPC result/error
AURC notification ──→      notifications/{event}
AURC stream       ──→      notifications/stream
```

### A2A 桥接映射

```
A2A JSON-RPC              AURC Message
─────────────              ────────────
tasks/send         ──→     delegation (method="invoke")
tasks/sendSubscribe ──→    delegation (with streaming metadata)
tasks/get          ──→     request (method="query_task_status")
tasks/cancel       ──→     notification (event="task_cancelled")

AURC delegation    ──→     tasks/send
AURC response      ──→     Task result (completed/failed)
AURC stream        ──→     SSE events (status-update/artifact-update)
AURC notification  ──→     Task state change
```

### 桥接器注册中心

```python
registry = BridgeRegistry()
registry.register(MCPBridge())     # "mcp/2025-06-18"
registry.register(A2ABridge())     # "a2a/1.0"

bridge = registry.get_bridge("mcp/2025-06-18")
bridge = registry.find_bridge("a2a/1.0", "aurc/0.1")
```

---

## L5：上下文关联层

此层追踪跨协议边界的上下文并管理 Agent 内存。

### 跨协议追踪

每条消息都携带 `correlation_id` 和 `bridge_chain`：

```
User Request (A2A)
  correlation_id: "corr-xyz-789"
  bridge_chain: []
    │
    ▼ A2A Bridge
AURC Orchestrator
  correlation_id: "corr-xyz-789"
  bridge_chain: ["a2a→aurc"]
    │
    ▼ MCP Bridge
MCP Web Search Server
  correlation_id: "corr-xyz-789"
  bridge_chain: ["a2a→aurc", "aurc→mcp"]
```

### 上下文作用域

```
┌──────────────────────────────────────────────────────┐
│ 全局作用域（Global）                                    │
│  生命周期：Harness 运行期间                              │
│  可见性：所有 Agent（受权限限制）                        │
│  ┌────────────────────────────────────────────────┐  │
│  │ 共享作用域（Shared）                              │  │
│  │  生命周期：跨 Agent                               │  │
│  │  可见性：授权组                                   │  │
│  │  ┌─────────────────────────────────────────┐   │  │
│  │  │ Agent 作用域                              │   │  │
│  │  │  生命周期：Agent 存续期                     │   │  │
│  │  │  可见性：仅当前 Agent                       │   │  │
│  │  │  ┌───────────────────────────────────┐  │   │  │
│  │  │  │ 会话作用域                          │  │   │  │
│  │  │  │  生命周期：单次任务                  │  │   │  │
│  │  │  │  可见性：仅当前 Agent               │  │   │  │
│  │  │  └───────────────────────────────────┘  │   │  │
│  │  └─────────────────────────────────────────┘   │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

---

## L6：安全层

AURC 实现 CapABAC —— 能力安全与属性访问控制的混合模型。

```
┌──────────────────────────────────────────────────────┐
│ 安全层                                                 │
│                                                      │
│  ┌────────────────┐  ┌──────────────────────────┐    │
│  │ 认证            │  │ 授权                      │    │
│  │                │  │                            │    │
│  │ APIKeyAuth..   │  │ AuthorizationEngine        │    │
│  │ JWTAuthent..   │  │  (CapABAC)                 │    │
│  │ MultiAuthen..  │  │  AgentPolicy + Rules       │    │
│  └────────────────┘  └──────────────────────────┘    │
│  ┌────────────────┐  ┌──────────────────────────┐    │
│  │ 委托            │  │ 审计                      │    │
│  │                │  │                            │    │
│  │ DelegationVal. │  │ AuditLog                   │    │
│  │ DelegationBui. │  │  (append-only, queryable)  │    │
│  └────────────────┘  └──────────────────────────┘    │
└──────────────────────────────────────────────────────┘
```

**权限规则：**
1. **权限只缩小不扩大**
2. **跨桥接 = 交集**
3. **链可审计**

---

## L7：发现层

```python
registry = LocalRegistry()

# 按技能查找
matches = registry.find_by_skills(["web-search", "summarize"])

# 按标签查找
researchers = registry.find_by_tag("research")

# 按协议查找
mcp_agents = registry.find_by_protocol("mcp/2025-06-18")

# 查找最佳匹配
best = registry.find_best(["deep-research"])
```

---

## 数据流图

### 场景 1：AURC Agent 调用 MCP 工具

```
┌────────────┐     AURCMessage       ┌────────────┐    MCP JSON-RPC    ┌────────────┐
│ AURC       │  ──────────────────→  │  MCP       │  ──────────────→  │  MCP       │
│ Agent      │  source:aurc:gaia/..  │  Bridge    │  tools/call       │  Server    │
│            │  target:mcp:web-srch  │            │  {name:"search"}  │            │
│            │                       │            │                   │            │
│            │  ←──────────────────  │            │  ←──────────────  │            │
│            │  AURCMessage response │            │  JSON-RPC result  │            │
└────────────┘                       └────────────┘                   └────────────┘
```

### 场景 2：多协议工作流

```
User Request
     │
     ▼
┌────────────────┐
│ AURC           │
│ Orchestrator   │───── Sub-task A ────→ AURC Agent (native)
│                │
│                │───── Sub-task B ────→ MCPBridge ────→ MCP Server
│                │
│                │───── Sub-task C ────→ A2ABridge ────→ A2A Agent
│                │
│   correlation_id: "corr-xyz-789" (shared across all)
└────────────────┘
     │
     ▼
Aggregated Result → User
```

### 场景 3：委托链流程

```
User (Alice)
  scopes: [research:read, web:search, admin]
     │  delegates to (narrows to [research:read, web:search])
     ▼
Orchestrator
  scopes: [research:read, web:search]
     │  delegates to (narrows to [research:read])
     ▼
Researcher Agent
  scopes: [research:read]        ← cannot access web:search or admin
     │  uses MCP tool via bridge
     ▼
MCP Web Search Server
  effective scopes: [research:read] ∩ MCP permissions
```

---

## 状态机详解

### 9 个状态

| 状态 | Enum Value | Terminal? | Active? | 描述 |
|-------|------------|:---------:|:-------:|-------------|
| `REGISTERING` | `"registering"` | No | No | 正在注册描述文档 |
| `READY` | `"ready"` | No | No | 等待任务 |
| `RUNNING` | `"running"` | No | Yes | 正在执行 |
| `PAUSED` | `"paused"` | No | No | 暂停（HITL、资源等待） |
| `FAILING` | `"failing"` | No | Yes | 出错，待恢复 |
| `RECOVERING` | `"recovering"` | No | Yes | 恢复中 |
| `COMPLETED` | `"completed"` | **Yes** | No | 成功完成 |
| `FAILED` | `"failed"` | **Yes** | No | 不可恢复 |
| `STOPPED` | `"stopped"` | **Yes** | No | 外部停止 |

### 合法转换

```
REGISTERING ──→ READY, FAILED
READY       ──→ RUNNING, STOPPED
RUNNING     ──→ PAUSED, FAILING, COMPLETED, STOPPED
PAUSED      ──→ RUNNING, STOPPED, READY
FAILING     ──→ RECOVERING, FAILED, STOPPED
RECOVERING  ──→ READY, FAILED
COMPLETED   ──→ (终态)
FAILED      ──→ (终态)
STOPPED     ──→ (终态)
```

### 状态转换图

```
                    ┌──────────────────────────────────┐
                    │                                  │
                    ▼                                  │
  ┌─────────────┐   ┌───────┐    ┌─────────┐    ┌────┴────┐
  │ REGISTERING │──→│ READY │⇄  │ RUNNING │──→│ PAUSED  │
  └──────┬──────┘   └───┬───┘    └────┬────┘    └────┬────┘
         │              │             │   │           │
         ▼              ▼             ▼   ▼           ▼
    ┌────────┐    ┌─────────┐  ┌──────┐ ┌────────┐ ┌─────────┐
    │ FAILED │    │ STOPPED │  │COMPL.│ │FAILING │ │ STOPPED │
    └────────┘    └─────────┘  └──────┘ └───┬────┘ └─────────┘
                                            │
                                            ▼
                                      ┌───────────┐
                                      │RECOVERING │
                                      └─────┬─────┘
                                            │
                               ┌────────────┼────────┐
                               ▼                     ▼
                          ┌───────┐            ┌────────┐
                          │ READY │            │ FAILED │
                          └───────┘            └────────┘
```

任何非法转换都会抛出 `StateTransitionError`。

---

## 异步模型

AURC 完全基于 Python 的 `asyncio` 构建。

**关键模式：**

- 所有生命周期方法（`register`、`start`、`pause`、`resume`、`stop`）都是 `async`
- 通过 `await router.route(message)` 路由消息
- 并行扇出使用 `asyncio.gather(*coros, return_exceptions=True)`
- 首次成功使用 `asyncio.as_completed(tasks)`
- 暂停/恢复使用 `asyncio.Event` 做非阻塞协调

```python
# 通过事件暂停
instance._pause_event.clear()   # Agent 暂停
await instance._pause_event.wait()  # 阻塞直到恢复

# 并行扇出
results = await asyncio.gather(*task_coros, return_exceptions=True)
```

---

## 扩展点

### 自定义桥接器

```python
class MyCustomBridge:
    @property
    def source_protocol(self) -> str:
        return "my-protocol/1.0"

    def can_bridge(self, source: str, target: str) -> bool:
        return (source == "my-protocol/1.0" and target == "aurc/0.1") or \
               (source == "aurc/0.1" and target == "my-protocol/1.0")

    async def translate_to_aurc(self, msg: dict) -> AURCMessage:
        ...

    async def translate_from_aurc(self, msg: AURCMessage) -> dict:
        ...

    async def map_capabilities(self, caps: list[dict]) -> list[dict]:
        ...

# 注册
registry = BridgeRegistry()
registry.register(MyCustomBridge())
```

### 自定义恢复策略

```python
policy = RecoveryPolicy(
    max_retries=5,
    backoff_ms=[1000, 2000, 5000, 10000, 30000],
    strategies=[
        RecoveryStrategy(trigger="timeout", action=RecoveryAction.RETRY_WITH_BACKOFF),
        RecoveryStrategy(trigger="auth_expired", action=RecoveryAction.REFRESH_AND_RETRY),
        RecoveryStrategy(trigger="unrecoverable", action=RecoveryAction.ESCALATE,
                         escalate_to="ops@example.com"),
    ],
)
harness = RuntimeHarness(recovery_policy=policy)
```

### 状态变化监听器

```python
def on_state_change(agent_id: str, old_state: AgentState, new_state: AgentState):
    print(f"Agent {agent_id}: {old_state.value} → {new_state.value}")

harness.add_listener(on_state_change)
```

---

*另请参阅：[桥接集成指南](guides/bridges.md) | [安全指南](guides/security.md) | [API 参考](api-reference.md)*
