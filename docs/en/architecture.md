# Architecture Deep Dive

> 🌐 [中文版](../zh/architecture.md)
> **[← Back to README](../../README.md)** | [Protocol Spec](../../PROTOCOL.md) | [API Reference](api-reference.md) | [Quick Start](guides/quickstart.md)
>
> A comprehensive guide to the AURC protocol architecture — the first complete 8-layer protocol stack for AI agent communication.

---

## Table of Contents

1. [Design Philosophy](#design-philosophy)
2. [Layered Architecture](#layered-architecture)
3. [L0: Transport Layer](#l0-transport-layer)
4. [L1: Agent Identity](#l1-agent-identity)
5. [L2: Runtime Harness](#l2-runtime-harness)
6. [L3: Unified Message Bus](#l3-unified-message-bus)
7. [L4: Protocol Bridges](#l4-protocol-bridges)
8. [L5: Context Correlation](#l5-context-correlation)
9. [L6: Security Layer](#l6-security-layer)
10. [L7: Discovery Layer](#l7-discovery-layer)
11. [Data Flow Diagrams](#data-flow-diagrams)
12. [State Machine](#state-machine)
13. [Async Model](#async-model)
14. [Extension Points](#extension-points)

---

## Design Philosophy

AURC is built on five core design principles:

| # | Principle | Rationale |
|---|---|---|
| 1 | **Bridge First** | Don't reinvent communication primitives; unify existing protocols |
| 2 | **Runtime is King** | Agent = Model + Harness; the Harness is a first-class citizen |
| 3 | **Progressive Complexity** | Simple core, enterprise features as optional modules |
| 4 | **Protocol-Agnostic Identity** | One agent, one identity across all protocols |
| 5 | **Security by Default** | Permissions enforceable at the protocol level |

### Why AURC Exists

The 2025–2026 AI agent ecosystem produced several protocols, each solving a narrow layer:

- **MCP** (Anthropic): Agent-to-Tool communication
- **A2A** (Google): Agent-to-Agent delegation
- **ACP** (IBM): Lightweight REST messaging

**Problem:** No single solution bridges these protocols or provides agent lifecycle management. An agent using MCP for tools cannot seamlessly delegate to an A2A agent, and neither protocol manages agent state, error recovery, or context persistence.

**AURC solves this** by layering on top — not replacing — existing protocols, adding runtime lifecycle, security, and cross-protocol context tracking.

---

## Layered Architecture

AURC uses an 8-layer model (L0–L7). Each layer is independently testable and replaceable.

```
┌──────────────────────────────────────────────────────────────────────┐
│ L7  Discovery                                                        │
│     LocalRegistry, capability matching, health-based routing         │
├──────────────────────────────────────────────────────────────────────┤
│ L6  Security                                                         │
│     APIKeyAuthenticator, JWTAuthenticator, AuthorizationEngine       │
│     DelegationValidator, AuditLog                                    │
├──────────────────────────────────────────────────────────────────────┤
│ L5  Context Correlation                                              │
│     ContextStore (session/agent/shared/global scopes)                │
│     correlation_id, bridge_chain tracking                            │
├──────────────────────────────────────────────────────────────────────┤
│ L4  Protocol Bridges                                                 │
│     MCPBridge  — MCP JSON-RPC ↔ AURC                                │
│     A2ABridge  — A2A tasks/send ↔ AURC                              │
│     ACPBridge  — ACP REST envelope ↔ AURC                           │
│     BridgeRegistry — manages all bridges                            │
├──────────────────────────────────────────────────────────────────────┤
│ L3  Unified Message Bus                                              │
│     AURCMessage (canonical format)                                  │
│     MessageRouter (direct/bridge/broadcast/dead-letter)              │
│     SessionManager (conversation tracking)                          │
├──────────────────────────────────────────────────────────────────────┤
│ L2  Runtime Harness                                                  │
│     RuntimeHarness (lifecycle state machine)                        │
│     AgentInstance (per-agent state wrapper)                         │
│     RecoveryPolicy (error recovery strategies)                      │
│     ContextStore (multi-scope memory)                               │
├──────────────────────────────────────────────────────────────────────┤
│ L1  Agent Identity                                                   │
│     AURCId (URN-format ID parsing)                                  │
│     AgentDescriptor (identity document)                             │
│     Capabilities, ProtocolSupport, AuthDeclaration                  │
├──────────────────────────────────────────────────────────────────────┤
│ L0  Transport                                                        │
│     HTTPTransportServer / HTTPTransportClient (HTTP/2 + ASGI)       │
│     WebSocketTransportServer / WebSocketTransportClient             │
│     stdio (local development)                                       │
└──────────────────────────────────────────────────────────────────────┘
```

### Layer Dependency Rule

Each layer may only depend on layers below it. This ensures clean separation:

- L7 (Discovery) can query L2 (Harness) for health, use L6 (Security) for auth
- L4 (Bridges) produces L3 (Messages) but does not manage lifecycle (L2)
- L0 (Transport) is protocol-agnostic — it moves bytes, not semantics

---

## L0: Transport Layer

The transport layer handles raw message delivery over the network.

### Supported Transports

| Transport | Use Case | Status |
|-----------|----------|--------|
| HTTP/2 (ASGI + uvicorn) | Production, cross-network | Implemented |
| WebSocket | Real-time bidirectional | Implemented |
| stdio | Local dev, CLI tools | Interface only |
| gRPC | High-performance internal | Planned |

### HTTP Transport Architecture

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

**Endpoints:**
- `POST /aurc` — Send an AURC message
- `GET /health` — Health check

---

## L1: Agent Identity

The identity layer provides globally unique, human-readable agent identification.

### AURC ID Format

```
aurc:{namespace}/{agent_name}:{version}

Examples:
  aurc:gaia/researcher:v1.2
  aurc:mycompany/code-reviewer:v2.0
  aurc:community/translator:v1.0
```

**Design rationale:**
- URN-style is simpler than DID (no blockchain dependency)
- Namespace provides decentralized uniqueness (like Docker Hub)
- Version pinning ensures reproducibility
- Glob-like pattern matching for routing

**Key class: `AURCId`** — parses and validates the format with regex, supports glob matching via `matches()`:

```python
aurc_id = AURCId.parse("aurc:gaia/researcher:v1.2")
print(aurc_id.namespace)  # "gaia"
print(aurc_id.name)       # "researcher"
print(aurc_id.version)    # "v1.2"
aurc_id.matches("aurc:gaia/*")  # True
```

### Agent Descriptor

The `AgentDescriptor` is the identity document — the single source of truth for:

1. **Who** the agent is (identity)
2. **What** it can do (capabilities/skills)
3. **How** to communicate (protocols)
4. **What** it needs (runtime requirements)
5. **How** to authenticate (security)

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

## L2: Runtime Harness

This is the **core innovation** of AURC — neither MCP, A2A, nor ACP provides agent lifecycle management.

### Components

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
│  │ AgentInstance (per agent)                             │  │
│  │  - descriptor: AgentDescriptor                       │  │
│  │  - state: AgentState (current)                       │  │
│  │  - _state_history: [(state, timestamp), ...]         │  │
│  │  - metrics: ResourceMetrics                          │  │
│  │  - _pause_event: asyncio.Event                       │  │
│  │  - _retry_count: int                                 │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

### Error Recovery

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

## L3: Unified Message Bus

The message bus is the central nervous system of AURC. Every communication flows through it as `AURCMessage`.

### AURCMessage Structure

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

### MessageRouter Flow

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

## L4: Protocol Bridges

Bridges are the key interoperability mechanism. They translate between AURC's canonical `AURCMessage` format and external protocols.

### Bridge Interface

Every bridge must implement the `ProtocolBridge` protocol:

```python
class ProtocolBridge(Protocol):
    source_protocol: str          # e.g. "mcp/2025-06-18"
    def can_bridge(src, tgt) -> bool
    async def translate_to_aurc(msg) -> AURCMessage
    async def translate_from_aurc(msg) -> ExternalMessage
    async def map_capabilities(caps) -> list[AURCCapability]
```

### MCP Bridge Mapping

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

### A2A Bridge Mapping

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

### BridgeRegistry

```python
registry = BridgeRegistry()
registry.register(MCPBridge())     # "mcp/2025-06-18"
registry.register(A2ABridge())     # "a2a/1.0"

bridge = registry.get_bridge("mcp/2025-06-18")
bridge = registry.find_bridge("a2a/1.0", "aurc/0.1")
```

---

## L5: Context Correlation

This layer tracks context across protocol boundaries and manages agent memory.

### Cross-Protocol Tracking

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

### Context Scopes

```
┌──────────────────────────────────────────────────────┐
│ Global Scope                                           │
│  Lifetime: Harness runtime                             │
│  Visibility: All agents (permission-gated)            │
│  ┌────────────────────────────────────────────────┐  │
│  │ Shared Scope                                    │  │
│  │  Lifetime: Cross-agent                           │  │
│  │  Visibility: Authorized groups                   │  │
│  │  ┌─────────────────────────────────────────┐   │  │
│  │  │ Agent Scope                              │   │  │
│  │  │  Lifetime: Agent lifetime                 │   │  │
│  │  │  Visibility: Current agent only          │   │  │
│  │  │  ┌───────────────────────────────────┐  │   │  │
│  │  │  │ Session Scope                      │  │   │  │
│  │  │  │  Lifetime: Single task             │  │   │  │
│  │  │  │  Visibility: Current agent only    │  │   │  │
│  │  │  └───────────────────────────────────┘  │   │  │
│  │  └─────────────────────────────────────────┘   │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

---

## L6: Security Layer

AURC implements CapABAC — a hybrid of Capability-Based Security and Attribute-Based Access Control.

```
┌──────────────────────────────────────────────────────┐
│ Security Layer                                         │
│                                                      │
│  ┌────────────────┐  ┌──────────────────────────┐    │
│  │ Authentication │  │ Authorization             │    │
│  │                │  │                            │    │
│  │ APIKeyAuth..   │  │ AuthorizationEngine        │    │
│  │ JWTAuthent..   │  │  (CapABAC)                 │    │
│  │ MultiAuthen..  │  │  AgentPolicy + Rules       │    │
│  └────────────────┘  └──────────────────────────┘    │
│  ┌────────────────┐  ┌──────────────────────────┐    │
│  │ Delegation     │  │ Audit                     │    │
│  │                │  │                            │    │
│  │ DelegationVal. │  │ AuditLog                   │    │
│  │ DelegationBui. │  │  (append-only, queryable)  │    │
│  └────────────────┘  └──────────────────────────┘    │
└──────────────────────────────────────────────────────┘
```

**Permission Rules:**
1. **Scopes only narrow, never widen**
2. **Cross-bridge = intersection**
3. **Chain is auditable**

---

## L7: Discovery Layer

```python
registry = LocalRegistry()

# Find by skills
matches = registry.find_by_skills(["web-search", "summarize"])

# Find by tag
researchers = registry.find_by_tag("research")

# Find by protocol
mcp_agents = registry.find_by_protocol("mcp/2025-06-18")

# Find best match
best = registry.find_best(["deep-research"])
```

---

## Data Flow Diagrams

### Scenario 1: AURC Agent Calls MCP Tool

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

### Scenario 2: Multi-Protocol Workflow

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

### Scenario 3: Delegation Chain Flow

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

## State Machine

### 9 States

| State | Enum Value | Terminal? | Active? | Description |
|-------|------------|:---------:|:-------:|-------------|
| `REGISTERING` | `"registering"` | No | No | Agent registering descriptor |
| `READY` | `"ready"` | No | No | Waiting for tasks |
| `RUNNING` | `"running"` | No | Yes | Actively executing |
| `PAUSED` | `"paused"` | No | No | Paused (HITL, resource wait) |
| `FAILING` | `"failing"` | No | Yes | Error, recovery pending |
| `RECOVERING` | `"recovering"` | No | Yes | Recovery in progress |
| `COMPLETED` | `"completed"` | **Yes** | No | Success |
| `FAILED` | `"failed"` | **Yes** | No | Unrecoverable |
| `STOPPED` | `"stopped"` | **Yes** | No | Externally stopped |

### Valid Transitions

```
REGISTERING ──→ READY, FAILED
READY       ──→ RUNNING, STOPPED
RUNNING     ──→ PAUSED, FAILING, COMPLETED, STOPPED
PAUSED      ──→ RUNNING, STOPPED, READY
FAILING     ──→ RECOVERING, FAILED, STOPPED
RECOVERING  ──→ READY, FAILED
COMPLETED   ──→ (terminal)
FAILED      ──→ (terminal)
STOPPED     ──→ (terminal)
```

### State Transition Diagram

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

## Async Model

AURC is built entirely on Python's `asyncio`.

**Key patterns:**

- All lifecycle methods (`register`, `start`, `pause`, `resume`, `stop`) are `async`
- Message routing via `await router.route(message)`
- Parallel fan-out uses `asyncio.gather(*coros, return_exceptions=True)`
- First-successful uses `asyncio.as_completed(tasks)`
- Pause/resume uses `asyncio.Event` for non-blocking coordination

```python
# Pause via event
instance._pause_event.clear()   # Agent pauses
await instance._pause_event.wait()  # Blocks until resumed

# Parallel fan-out
results = await asyncio.gather(*task_coros, return_exceptions=True)
```

---

## Extension Points

### Custom Bridge

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

# Register
registry = BridgeRegistry()
registry.register(MyCustomBridge())
```

### Custom Recovery Strategy

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

### State Change Listeners

```python
def on_state_change(agent_id: str, old_state: AgentState, new_state: AgentState):
    print(f"Agent {agent_id}: {old_state.value} → {new_state.value}")

harness.add_listener(on_state_change)
```

---

*See also: [Bridge Integration Guide](guides/bridges.md) | [Security Guide](guides/security.md) | [API Reference](api-reference.md)*
