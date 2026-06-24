# Architecture Deep Dive / 架构深度解析

> **[← Back to README](../README.md)** | [Protocol Spec](../PROTOCOL.md) | [API Reference](api-reference.md) | [Quick Start](guides/quickstart.md)
>
> A comprehensive guide to the AURC protocol architecture — the first complete 8-layer protocol stack for AI agent communication.
>
> AURC 协议架构全面指南 — AI Agent 通信领域首个完整的 8 层协议栈。

---

## Table of Contents / 目录

1. [Design Philosophy / 设计哲学](#design-philosophy--设计哲学)
2. [Layered Architecture / 分层架构](#layered-architecture--分层架构)
3. [L0: Transport Layer / 传输层](#l0-transport-layer--传输层)
4. [L1: Agent Identity / Agent 身份](#l1-agent-identity--agent-身份)
5. [L2: Runtime Harness / 运行时 Harness](#l2-runtime-harness--运行时-harness)
6. [L3: Unified Message Bus / 统一消息总线](#l3-unified-message-bus--统一消息总线)
7. [L4: Protocol Bridges / 协议桥接层](#l4-protocol-bridges--协议桥接层)
8. [L5: Context Correlation / 上下文关联层](#l5-context-correlation--上下文关联层)
9. [L6: Security Layer / 安全层](#l6-security-layer--安全层)
10. [L7: Discovery Layer / 发现层](#l7-discovery-layer--发现层)
11. [Data Flow Diagrams / 数据流图](#data-flow-diagrams--数据流图)
12. [State Machine / 状态机详解](#state-machine--状态机详解)
13. [Async Model / 异步模型](#async-model--异步模型)
14. [Extension Points / 扩展点](#extension-points--扩展点)

---

## Design Philosophy / 设计哲学

AURC is built on five core design principles / AURC 基于五大核心设计原则:

| # | Principle / 原则 | Rationale / 理由 |
|---|---|---|
| 1 | **Bridge First** / 桥接优先 | Don't reinvent communication primitives; unify existing protocols / 不重新发明通信原语，统一现有协议 |
| 2 | **Runtime is King** / 运行时为核心 | Agent = Model + Harness; the Harness is a first-class citizen / Agent = 模型 + Harness；Harness 是一等公民 |
| 3 | **Progressive Complexity** / 渐进复杂度 | Simple core, enterprise features as optional modules / 简单核心，企业功能作为可选模块 |
| 4 | **Protocol-Agnostic Identity** / 协议无关身份 | One agent, one identity across all protocols / 一个 Agent，跨所有协议的统一身份 |
| 5 | **Security by Default** / 安全第一 | Permissions enforceable at the protocol level / 权限可在协议层面强制执行 |

### Why AURC Exists / AURC 为什么存在

The 2025–2026 AI agent ecosystem produced several protocols, each solving a narrow layer:

- **MCP** (Anthropic): Agent-to-Tool communication
- **A2A** (Google): Agent-to-Agent delegation
- **ACP** (IBM): Lightweight REST messaging

**Problem / 问题:** No single solution bridges these protocols or provides agent lifecycle management. An agent using MCP for tools cannot seamlessly delegate to an A2A agent, and neither protocol manages agent state, error recovery, or context persistence.

**AURC solves this** by layering on top — not replacing — existing protocols, adding runtime lifecycle, security, and cross-protocol context tracking.

---

## Layered Architecture / 分层架构

AURC uses an 8-layer model (L0–L7). Each layer is independently testable and replaceable.

AURC 使用 8 层模型 (L0–L7)。每一层都可以独立测试和替换。

```
┌──────────────────────────────────────────────────────────────────────┐
│ L7  Discovery / 发现层                                               │
│     LocalRegistry, capability matching, health-based routing         │
│     Agent 注册中心、能力匹配、健康路由                                    │
├──────────────────────────────────────────────────────────────────────┤
│ L6  Security / 安全层                                                │
│     APIKeyAuthenticator, JWTAuthenticator, AuthorizationEngine       │
│     DelegationValidator, AuditLog                                    │
│     API Key / JWT 认证、CapABAC 授权引擎、委托链验证、审计日志            │
├──────────────────────────────────────────────────────────────────────┤
│ L5  Context Correlation / 上下文关联层                                 │
│     ContextStore (session/agent/shared/global scopes)                │
│     correlation_id, bridge_chain tracking                            │
│     多作用域上下文存储、关联 ID、桥接链追踪                                │
├──────────────────────────────────────────────────────────────────────┤
│ L4  Protocol Bridges / 协议桥接层                                     │
│     MCPBridge  — MCP JSON-RPC ↔ AURC                                │
│     A2ABridge  — A2A tasks/send ↔ AURC                              │
│     ACPBridge  — ACP REST envelope ↔ AURC                           │
│     BridgeRegistry — manages all bridges / 管理所有桥接器              │
├──────────────────────────────────────────────────────────────────────┤
│ L3  Unified Message Bus / 统一消息总线                                │
│     AURCMessage (canonical format) / 标准消息格式                     │
│     MessageRouter (direct/bridge/broadcast/dead-letter)              │
│     SessionManager (conversation tracking) / 会话管理                 │
├──────────────────────────────────────────────────────────────────────┤
│ L2  Runtime Harness / 运行时 Harness                                 │
│     RuntimeHarness (lifecycle state machine) / 生命周期状态机          │
│     AgentInstance (per-agent state wrapper) / Agent 状态包装          │
│     RecoveryPolicy (error recovery strategies) / 错误恢复策略          │
│     ContextStore (multi-scope memory) / 多作用域内存                  │
├──────────────────────────────────────────────────────────────────────┤
│ L1  Agent Identity / Agent 身份                                      │
│     AURCId (URN-format ID parsing) / URN 格式 ID 解析                │
│     AgentDescriptor (identity document) / 身份描述文档                │
│     Capabilities, ProtocolSupport, AuthDeclaration                   │
├──────────────────────────────────────────────────────────────────────┤
│ L0  Transport / 传输层                                               │
│     HTTPTransportServer / HTTPTransportClient (HTTP/2 + ASGI)       │
│     WebSocketTransportServer / WebSocketTransportClient             │
│     stdio (local development) / 标准输入输出（本地开发）                │
└──────────────────────────────────────────────────────────────────────┘
```

### Layer Dependency Rule / 层依赖规则

Each layer may only depend on layers below it. This ensures clean separation:

- L7 (Discovery) can query L2 (Harness) for health, use L6 (Security) for auth
- L4 (Bridges) produces L3 (Messages) but does not manage lifecycle (L2)
- L0 (Transport) is protocol-agnostic — it moves bytes, not semantics

---

## L0: Transport Layer / 传输层

The transport layer handles raw message delivery over the network.

传输层负责通过网络传递原始消息。

### Supported Transports / 支持的传输方式

| Transport | Use Case / 用例 | Status / 状态 |
|-----------|----------|--------|
| HTTP/2 (ASGI + uvicorn) | Production, cross-network / 生产环境 | Implemented |
| WebSocket | Real-time bidirectional / 实时双向 | Implemented |
| stdio | Local dev, CLI tools / 本地开发 | Interface only |
| gRPC | High-performance internal / 高性能内部 | Planned |

### HTTP Transport Architecture / HTTP 传输架构

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

**Endpoints / 端点:**
- `POST /aurc` — Send an AURC message / 发送 AURC 消息
- `GET /health` — Health check / 健康检查

---

## L1: Agent Identity / Agent 身份

The identity layer provides globally unique, human-readable agent identification.

身份层提供全局唯一、人类可读的 Agent 标识。

### AURC ID Format / AURC ID 格式

```
aurc:{namespace}/{agent_name}:{version}

Examples / 示例:
  aurc:gaia/researcher:v1.2
  aurc:mycompany/code-reviewer:v2.0
  aurc:community/translator:v1.0
```

**Design rationale / 设计理由:**
- URN-style is simpler than DID (no blockchain dependency) / URN 风格比 DID 更简单
- Namespace provides decentralized uniqueness (like Docker Hub) / 命名空间提供去中心化唯一性
- Version pinning ensures reproducibility / 版本固定确保可复现性
- Glob-like pattern matching for routing / 支持通配符匹配用于路由

**Key class: `AURCId`** — parses and validates the format with regex, supports glob matching via `matches()`:

```python
aurc_id = AURCId.parse("aurc:gaia/researcher:v1.2")
print(aurc_id.namespace)  # "gaia"
print(aurc_id.name)       # "researcher"
print(aurc_id.version)    # "v1.2"
aurc_id.matches("aurc:gaia/*")  # True
```

### Agent Descriptor / Agent 描述文档

The `AgentDescriptor` is the identity document — the single source of truth for:

1. **Who** the agent is (identity) / Agent 是谁（身份）
2. **What** it can do (capabilities/skills) / 能做什么（能力/技能）
3. **How** to communicate (protocols) / 如何通信（协议）
4. **What** it needs (runtime requirements) / 需要什么（运行时需求）
5. **How** to authenticate (security) / 如何认证（安全）

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

## L2: Runtime Harness / 运行时 Harness

This is the **core innovation** of AURC — neither MCP, A2A, nor ACP provides agent lifecycle management.

这是 AURC 的**核心创新** — MCP、A2A 和 ACP 都不提供 Agent 生命周期管理。

### Components / 组件

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
│  │ AgentInstance (per agent) / 每个 Agent 的实例         │  │
│  │  - descriptor: AgentDescriptor                       │  │
│  │  - state: AgentState (current)                       │  │
│  │  - _state_history: [(state, timestamp), ...]         │  │
│  │  - metrics: ResourceMetrics                          │  │
│  │  - _pause_event: asyncio.Event                       │  │
│  │  - _retry_count: int                                 │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

### Error Recovery / 错误恢复

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

## L3: Unified Message Bus / 统一消息总线

The message bus is the central nervous system of AURC. Every communication flows through it as `AURCMessage`.

消息总线是 AURC 的中枢神经系统。所有通信都以 `AURCMessage` 流经它。

### AURCMessage Structure / AURCMessage 结构

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

### MessageRouter Flow / MessageRouter 流程

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

## L4: Protocol Bridges / 协议桥接层

Bridges are the key interoperability mechanism. They translate between AURC's canonical `AURCMessage` format and external protocols.

桥接器是关键互操作机制。它们在 AURC 的标准 `AURCMessage` 格式和外部协议之间进行翻译。

### Bridge Interface / 桥接器接口

Every bridge must implement the `ProtocolBridge` protocol:

```python
class ProtocolBridge(Protocol):
    source_protocol: str          # e.g. "mcp/2025-06-18"
    def can_bridge(src, tgt) -> bool
    async def translate_to_aurc(msg) -> AURCMessage
    async def translate_from_aurc(msg) -> ExternalMessage
    async def map_capabilities(caps) -> list[AURCCapability]
```

### MCP Bridge Mapping / MCP 桥接映射

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

### A2A Bridge Mapping / A2A 桥接映射

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

### BridgeRegistry / 桥接器注册中心

```python
registry = BridgeRegistry()
registry.register(MCPBridge())     # "mcp/2025-06-18"
registry.register(A2ABridge())     # "a2a/1.0"

bridge = registry.get_bridge("mcp/2025-06-18")
bridge = registry.find_bridge("a2a/1.0", "aurc/0.1")
```

---

## L5: Context Correlation / 上下文关联层

This layer tracks context across protocol boundaries and manages agent memory.

此层追踪跨协议边界的上下文并管理 Agent 内存。

### Cross-Protocol Tracking / 跨协议追踪

Every message carries `correlation_id` and `bridge_chain`:

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

### Context Scopes / 上下文作用域

```
┌──────────────────────────────────────────────────────┐
│ Global Scope (全局)                                   │
│  Lifetime: Harness runtime / Harness 运行期间         │
│  Visibility: All agents (permission-gated)            │
│  ┌────────────────────────────────────────────────┐  │
│  │ Shared Scope (共享)                             │  │
│  │  Lifetime: Cross-agent / 跨 Agent               │  │
│  │  Visibility: Authorized groups / 授权组          │  │
│  │  ┌─────────────────────────────────────────┐   │  │
│  │  │ Agent Scope (Agent)                      │   │  │
│  │  │  Lifetime: Agent lifetime / Agent 存续期 │   │  │
│  │  │  Visibility: Current agent only          │   │  │
│  │  │  ┌───────────────────────────────────┐  │   │  │
│  │  │  │ Session Scope (会话)               │  │   │  │
│  │  │  │  Lifetime: Single task / 单次任务  │  │   │  │
│  │  │  │  Visibility: Current agent only    │  │   │  │
│  │  │  └───────────────────────────────────┘  │   │  │
│  │  └─────────────────────────────────────────┘   │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

---

## L6: Security Layer / 安全层

AURC implements CapABAC — a hybrid of Capability-Based Security and Attribute-Based Access Control.

AURC 实现 CapABAC — 能力安全与属性访问控制的混合模型。

```
┌──────────────────────────────────────────────────────┐
│ Security Layer / 安全层                               │
│                                                      │
│  ┌────────────────┐  ┌──────────────────────────┐    │
│  │ Authentication │  │ Authorization             │    │
│  │ 认证           │  │ 授权                       │    │
│  │                │  │                            │    │
│  │ APIKeyAuth..   │  │ AuthorizationEngine        │    │
│  │ JWTAuthent..   │  │  (CapABAC)                 │    │
│  │ MultiAuthen..  │  │  AgentPolicy + Rules       │    │
│  └────────────────┘  └──────────────────────────┘    │
│  ┌────────────────┐  ┌──────────────────────────┐    │
│  │ Delegation     │  │ Audit                     │    │
│  │ 委托           │  │ 审计                       │    │
│  │                │  │                            │    │
│  │ DelegationVal. │  │ AuditLog                   │    │
│  │ DelegationBui. │  │  (append-only, queryable)  │    │
│  └────────────────┘  └──────────────────────────┘    │
└──────────────────────────────────────────────────────┘
```

**Permission Rules / 权限规则:**
1. **Scopes only narrow, never widen** / 权限只缩小不扩大
2. **Cross-bridge = intersection** / 跨桥接 = 交集
3. **Chain is auditable** / 链可审计

---

## L7: Discovery Layer / 发现层

```python
registry = LocalRegistry()

# Find by skills / 按技能查找
matches = registry.find_by_skills(["web-search", "summarize"])

# Find by tag / 按标签查找
researchers = registry.find_by_tag("research")

# Find by protocol / 按协议查找
mcp_agents = registry.find_by_protocol("mcp/2025-06-18")

# Find best match / 查找最佳匹配
best = registry.find_best(["deep-research"])
```

---

## Data Flow Diagrams / 数据流图

### Scenario 1: AURC Agent Calls MCP Tool / AURC Agent 调用 MCP 工具

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

### Scenario 2: Multi-Protocol Workflow / 多协议工作流

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

### Scenario 3: Delegation Chain Flow / 委托链流程

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

## State Machine / 状态机详解

### 9 States / 9 个状态

| State / 状态 | Enum Value | Terminal? | Active? | Description / 描述 |
|-------|------------|:---------:|:-------:|-------------|
| `REGISTERING` | `"registering"` | No | No | Agent registering descriptor / 正在注册 |
| `READY` | `"ready"` | No | No | Waiting for tasks / 等待任务 |
| `RUNNING` | `"running"` | No | Yes | Actively executing / 正在执行 |
| `PAUSED` | `"paused"` | No | No | Paused (HITL, resource wait) / 暂停 |
| `FAILING` | `"failing"` | No | Yes | Error, recovery pending / 出错 |
| `RECOVERING` | `"recovering"` | No | Yes | Recovery in progress / 恢复中 |
| `COMPLETED` | `"completed"` | **Yes** | No | Success / 成功完成 |
| `FAILED` | `"failed"` | **Yes** | No | Unrecoverable / 不可恢复 |
| `STOPPED` | `"stopped"` | **Yes** | No | Externally stopped / 外部停止 |

### Valid Transitions / 合法转换

```
REGISTERING ──→ READY, FAILED
READY       ──→ RUNNING, STOPPED
RUNNING     ──→ PAUSED, FAILING, COMPLETED, STOPPED
PAUSED      ──→ RUNNING, STOPPED, READY
FAILING     ──→ RECOVERING, FAILED, STOPPED
RECOVERING  ──→ READY, FAILED
COMPLETED   ──→ (terminal / 终态)
FAILED      ──→ (terminal / 终态)
STOPPED     ──→ (terminal / 终态)
```

### State Transition Diagram / 状态转换图

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

Any invalid transition raises `StateTransitionError`.

---

## Async Model / 异步模型

AURC is built entirely on Python's `asyncio`.

AURC 完全基于 Python 的 `asyncio` 构建。

**Key patterns / 关键模式:**

- All lifecycle methods (`register`, `start`, `pause`, `resume`, `stop`) are `async`
- Message routing via `await router.route(message)`
- Parallel fan-out uses `asyncio.gather(*coros, return_exceptions=True)`
- First-successful uses `asyncio.as_completed(tasks)`
- Pause/resume uses `asyncio.Event` for non-blocking coordination

```python
# Pause via event / 通过事件暂停
instance._pause_event.clear()   # Agent pauses
await instance._pause_event.wait()  # Blocks until resumed

# Parallel fan-out / 并行扇出
results = await asyncio.gather(*task_coros, return_exceptions=True)
```

---

## Extension Points / 扩展点

### Custom Bridge / 自定义桥接器

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

# Register / 注册
registry = BridgeRegistry()
registry.register(MyCustomBridge())
```

### Custom Recovery Strategy / 自定义恢复策略

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

### State Change Listeners / 状态变化监听器

```python
def on_state_change(agent_id: str, old_state: AgentState, new_state: AgentState):
    print(f"Agent {agent_id}: {old_state.value} → {new_state.value}")

harness.add_listener(on_state_change)
```

---

*See also / 另请参阅: [Bridge Integration Guide](guides/bridges.md) | [Security Guide](guides/security.md) | [API Reference](api-reference.md)*
