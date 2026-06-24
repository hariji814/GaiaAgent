# AURC Protocol Specification v0.1

**Agent Unified Runtime & Communication Protocol**
**Agent 统一运行时与通信协议**

> **[← Back to README](README.md)** | [Architecture](docs/architecture.md) | [API Reference](docs/api-reference.md) | [Quick Start](docs/guides/quickstart.md)
>
> Status: Draft / 状态：草案
> Version: 0.1.0
> License: CC BY-SA 4.0 (specification) / AGPL-3.0 (implementation)

---

## Table of Contents / 目录

1. [Introduction / 介绍](#1-introduction)
2. [Design Principles / 设计原则](#2-design-principles)
3. [Architecture Overview / 架构概览](#3-architecture)
4. [L1: Agent Identity / Agent 身份](#4-l1-agent-identity)
5. [L2: Runtime Harness / 运行时 Harness](#5-l2-runtime-harness)
6. [L3: Unified Message Bus / 统一消息总线](#6-l3-unified-message-bus)
7. [L4: Protocol Bridges / 协议桥接](#7-l4-protocol-bridges)
8. [L5: Context Correlation / 上下文关联](#8-l5-context-correlation)
9. [L6: Security / 安全](#9-l6-security)
10. [L7: Discovery / 发现](#10-l7-discovery)
11. [L0: Transport / 传输](#11-l0-transport)
12. [Comparison with Existing Protocols / 与现有协议对比](#12-comparison)
13. [Use Case Scenarios / 使用场景](#13-use-cases)
14. [SDK Design / SDK 设计](#14-sdk-design)
15. [Roadmap / 路线图](#15-roadmap)
16. [Glossary / 术语表](#16-glossary)

---

## 1. Introduction

### 1.1 Motivation / 动机

The 2025-2026 AI agent ecosystem has produced several communication protocols, each solving a specific layer:

- **MCP** (Anthropic): Agent-to-Tool communication
- **A2A** (Google): Agent-to-Agent delegation
- **ACP** (IBM): Lightweight REST messaging
- **ANP** (Community): Decentralized identity

**Problem:** No single solution bridges these protocols or provides agent runtime lifecycle management. An agent using MCP for tools cannot seamlessly delegate to an A2A agent, and neither protocol manages agent state, error recovery, or context persistence.

**AURC solves this** by providing:
1. A **runtime harness** for agent lifecycle management
2. **Protocol bridges** for translating between MCP, A2A, and ACP
3. A **unified identity** system that works across all protocols
4. **Security enforcement** at the protocol level

### 1.2 Scope / 范围

This specification defines:
- The AURC message format and protocol semantics
- The Runtime Harness state machine and interfaces
- Protocol Bridge interfaces for MCP and A2A
- Security model (CapABAC) and delegation chain validation
- Agent discovery and capability matching

This specification does NOT define:
- The internal implementation of AI agents
- LLM model selection or inference logic
- UI/UX for agent interaction
- Specific transport implementations (only interfaces)

---

## 2. Design Principles

| # | Principle / 原则 | Meaning / 含义 |
|---|---|---|
| 1 | **Bridge First** / 桥接优先 | Don't invent new communication primitives; unify existing protocols |
| 2 | **Runtime is King** / 运行时为核心 | Agent = Model + Harness; the Harness is a first-class citizen |
| 3 | **Progressive Complexity** / 渐进复杂度 | Simple core, enterprise features as optional modules |
| 4 | **Protocol-Agnostic Identity** / 协议无关身份 | One agent, one identity across all protocols |
| 5 | **Security by Default** / 安全第一 | Permissions are enforceable at the protocol level, not just declarative |

---

## 3. Architecture

### 3.1 Layered Model / 分层模型

```
┌──────────────────────────────────────────────────────────────┐
│ L7  Discovery / 发现层                                        │
│     Agent registry, capability matching, health-based routing │
├──────────────────────────────────────────────────────────────┤
│ L6  Security / 安全层                                         │
│     Auth, CapABAC authorization, delegation chains, audit     │
├──────────────────────────────────────────────────────────────┤
│ L5  Context Correlation / 上下文关联层                         │
│     Cross-protocol context tracking, permission propagation   │
├──────────────────────────────────────────────────────────────┤
│ L4  Protocol Bridges / 协议桥接层                              │
│     MCP Bridge / A2A Bridge / ACP Bridge / Custom Bridge      │
├──────────────────────────────────────────────────────────────┤
│ L3  Unified Message Bus / 统一消息总线                         │
│     Canonical message format, routing, session management     │
├──────────────────────────────────────────────────────────────┤
│ L2  Runtime Harness / 运行时 Harness                          │
│     Lifecycle, health monitoring, context/memory, recovery    │
├──────────────────────────────────────────────────────────────┤
│ L1  Agent Identity / Agent 身份                               │
│     AURC ID, capability declaration, protocol binding         │
├──────────────────────────────────────────────────────────────┤
│ L0  Transport / 传输层                                        │
│     HTTP/2, WebSocket, stdio, gRPC                            │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 Roles / 角色

| Role | Description |
|------|-------------|
| **AURC Host** | Main process running the Harness, managing agent lifecycles |
| **AURC Agent** | An AI agent registered in the Harness, possessing an AURC ID |
| **AURC Router** | Message router delivering messages between agents |
| **Protocol Bridge** | Adapter translating AURC messages to/from external protocols |
| **AURC Registry** | Agent discovery service with capability matching |

---

## 4. L1: Agent Identity

### 4.1 AURC ID Format

AURC uses a **hierarchical URN** format for globally unique, human-readable agent identification:

```
aurc:{namespace}/{agent_name}:{version}

Examples:
  aurc:gaia/researcher:v1.2
  aurc:mycompany/code-reviewer:v2.0
  aurc:community/translator:v1.0
```

**Design rationale:**
- URN is simpler than DID (no blockchain dependency)
- Namespace provides decentralized uniqueness (like Docker Hub org/image)
- Version pinning ensures reproducibility
- DID's `did:wba` method can be used as an optional supplementary identity layer

### 4.2 Agent Descriptor

The Agent Descriptor is the identity document for an AURC agent. It serves as the single source of truth for identity, capabilities, protocols, runtime requirements, and security.

```json
{
  "schema_version": "aurc://spec/v0.1/agent-descriptor.json",
  "aurc_id": "aurc:gaia/researcher:v1.2",
  "display_name": "Research Agent",
  "description": "Deep research with multi-source analysis",
  "version": "1.2.0",
  "author": "GaiaAgent Team",
  "license": "AGPL-3.0",
  "capabilities": {
    "provides": [
      {
        "skill_id": "deep-research",
        "name": "Deep Research",
        "description": "Multi-source research and synthesis",
        "input_schema": {
          "type": "object",
          "properties": {
            "query": {"type": "string"},
            "depth": {"type": "string", "enum": ["shallow", "medium", "deep"]}
          },
          "required": ["query"]
        },
        "output_schema": {"type": "object"}
      }
    ],
    "consumes": ["web-search", "document-reader"]
  },
  "protocols": {
    "native": "aurc/0.1",
    "bridges": ["mcp/2025-06-18", "a2a/1.0"]
  },
  "runtime": {
    "max_concurrency": 10,
    "supports_streaming": true,
    "supports_pause": true,
    "timeout_seconds": 3600
  },
  "auth": {
    "methods": ["api_key", "oauth2"],
    "scopes": ["research:read", "research:write"]
  }
}
```

---

## 5. L2: Runtime Harness

This is the **core innovation** of AURC — neither MCP, A2A, nor ACP provides agent lifecycle management.

### 5.1 State Machine

```
REGISTERING → READY ⇄ RUNNING → COMPLETED
                           ↕         ↕
                        PAUSED    FAILING → RECOVERING → READY
                                                ↕
                                             FAILED / STOPPED
```

| State | Description |
|-------|-------------|
| `REGISTERING` | Agent is registering its descriptor and capabilities |
| `READY` | Agent is registered and waiting for tasks |
| `RUNNING` | Agent is actively executing a task |
| `PAUSED` | Agent execution is paused (human approval, resource wait, etc.) |
| `FAILING` | Agent encountered an error, attempting automatic recovery |
| `RECOVERING` | Agent is recovering from a failure |
| `COMPLETED` | Task finished successfully (terminal) |
| `FAILED` | Task failed and cannot be recovered (terminal) |
| `STOPPED` | Agent was externally stopped (terminal) |

### 5.2 Error Recovery Strategies

| Trigger | Action | Description |
|---------|--------|-------------|
| `timeout` | `retry_with_backoff` | Retry with exponential backoff (1s, 5s, 15s) |
| `tool_error` | `retry_alternative` | Try an alternative tool/skill |
| `context_overflow` | `compact_and_retry` | Summarize oldest context and retry |
| `auth_expired` | `refresh_and_retry` | Refresh credentials and retry |
| `unrecoverable` | `escalate` | Escalate to human operator |

### 5.3 Context Scopes

| Scope | Lifetime | Visibility | Use Case |
|-------|----------|------------|----------|
| `session` | Single task | Current agent only | Temporary computation state |
| `agent` | Agent lifetime | Current agent only | Learning preferences, history |
| `shared` | Cross-agent | Authorized agent groups | Shared knowledge base |
| `global` | Harness lifetime | All agents (permission-gated) | System configuration |

### 5.4 Human-in-the-Loop

AURC standardizes human intervention with the HITL protocol:

```json
{
  "hitl_request": {
    "id": "hitl-20260624-001",
    "agent_id": "aurc:gaia/researcher:v1.2",
    "type": "approval",
    "priority": "normal",
    "context": {
      "question": "Found 3 conflicting data sources, need human judgment",
      "options": [
        {"id": "trust-source-a", "label": "Trust Source A (academic journals)"},
        {"id": "investigate-further", "label": "Investigate further"}
      ],
      "timeout_seconds": 3600,
      "timeout_action": "pause_and_wait"
    }
  }
}
```

---

## 6. L3: Unified Message Bus

### 6.1 Message Format

JSON is the canonical format (human-readable, broad ecosystem). MessagePack is supported as an optional high-performance encoding.

```json
{
  "aurc_version": "0.1",
  "message_id": "msg-20260624-a1b2c3",
  "correlation_id": "corr-xyz-789",
  "trace_id": "trace-dist-456",
  "timestamp": "2026-06-24T10:30:00.000Z",
  "source": "aurc:gaia/orchestrator:v1.0",
  "target": "aurc:gaia/researcher:v1.2",
  "type": "request",
  "protocol_context": {
    "origin_protocol": "aurc",
    "bridged_from": null,
    "bridge_chain": []
  },
  "session": {
    "session_id": "session-20260624-001",
    "conversation_id": "conv-abc",
    "turn": 5
  },
  "body": {
    "method": "invoke",
    "skill": "deep-research",
    "params": {
      "query": "2026 AI Agent protocol interoperability",
      "depth": "deep"
    }
  },
  "routing": {
    "ttl_hops": 5,
    "priority": "normal",
    "timeout_ms": 30000
  },
  "security": {
    "scopes": ["research:read"],
    "delegation_chain": [
      {
        "from": "aurc:user/alice:v1.0",
        "to": "aurc:gaia/orchestrator:v1.0",
        "scopes": ["research:read", "web:search"],
        "timestamp": "2026-06-24T10:00:00.000Z"
      }
    ]
  }
}
```

### 6.2 Message Types

| Type | Direction | Description |
|------|-----------|-------------|
| `request` | Initiator → Target | Request an operation, requires response |
| `response` | Target → Initiator | Reply to a request |
| `notification` | One-way | Event notification, no response needed |
| `stream` | Target → Initiator | Streaming data chunks |
| `delegation` | Agent → Agent | Task delegation with full context |
| `handoff` | Agent → Agent | Task ownership transfer |
| `heartbeat` | Bidirectional | Keep-alive signal |

---

## 7. L4: Protocol Bridges

### 7.1 Bridge Interface

Every bridge must implement:

```python
class ProtocolBridge(Protocol):
    source_protocol: str              # e.g. "mcp/2025-06-18"
    def can_bridge(src, tgt) -> bool
    async def translate_to_aurc(msg) -> AURCMessage
    async def translate_from_aurc(msg) -> ExternalMessage
    async def map_capabilities(caps) -> list[AURCCapability]
```

### 7.2 MCP Bridge Mapping

| MCP Method | AURC Equivalent |
|------------|----------------|
| `tools/call` | `request` (method=invoke) |
| `tools/list` | `request` (method=list_capabilities) |
| `resources/read` | `request` (method=load_context) |
| `initialize` | `notification` (event=mcp_server_initialized) |

### 7.3 A2A Bridge Mapping

| A2A Method | AURC Equivalent |
|------------|----------------|
| `tasks/send` | `delegation` |
| `tasks/get` | `request` (method=query_task_status) |
| `tasks/cancel` | `notification` (event=task_cancelled) |
| Task state changes | `notification` / `stream` |

### 7.4 Capability Mapping

| AURC Concept | MCP | A2A | ACP |
|-------------|-----|-----|-----|
| Skill | Tool | Skill | Endpoint |
| Agent Descriptor | Server Capabilities | Agent Card | Service Registration |
| Request | tools/call | tasks/send | POST /tasks |
| Context | Resources | Messages/Artifacts | Payload |

---

## 8. L5: Context Correlation

### 8.1 Cross-Protocol Tracking

Every message carries a `correlation_id` and `bridge_chain` that tracks its path across protocol boundaries:

```json
{
  "correlation_id": "corr-xyz-789",
  "bridge_chain": [
    {"hop": 1, "from": "a2a/1.0", "to": "aurc/0.1"},
    {"hop": 2, "from": "aurc/0.1", "to": "mcp/2025-06-18"}
  ]
}
```

### 8.2 Permission Propagation Rules

1. **Scopes only narrow, never widen** — each delegation hop can only reduce permissions
2. **Cross-bridge permissions are intersection** — bridged permissions = AURC ∩ external protocol
3. **Delegation chain is auditable** — every hop is recorded and verifiable

---

## 9. L6: Security

### 9.1 Authentication Methods

| Method | Use Case | Security Level |
|--------|----------|:---:|
| API Key | Development, internal services | ★★☆ |
| OAuth 2.1 | User authorization scenarios | ★★★★ |
| mTLS | Enterprise agent interconnection | ★★★★★ |
| JWT + JWKS | Cross-organization federation | ★★★★ |

### 9.2 CapABAC Authorization

AURC combines Capability-Based Security with Attribute-Based Access Control:

```json
{
  "policy": {
    "subject": "aurc:gaia/researcher:v1.2",
    "conditions": [
      {
        "resource_type": "web-search",
        "actions": ["execute"],
        "constraints": {
          "max_queries_per_hour": 100,
          "allowed_domains": ["*.edu", "*.gov", "arxiv.org"]
        }
      }
    ],
    "delegation": {
      "allowed": true,
      "max_depth": 3,
      "scope_reduction_required": true
    }
  }
}
```

### 9.3 Solving MCP's Confused Deputy Problem

MCP's core security issue: servers act on behalf of users but cannot distinguish or enforce what users are authorized to do.

**AURC's solution:**

1. Every invocation carries a **Delegation Chain** recording the full permission path
2. Bridge layer **enforces permission mapping** — validates each hop's legality
3. **Immutable audit log** — all cross-protocol calls recorded for compliance

---

## 10. L7: Discovery

### 10.1 Discovery Modes

| Mode | Use Case | Mechanism |
|------|----------|-----------|
| Local | Single-machine development | In-memory agent list |
| File | Small teams | YAML/JSON configuration |
| HTTP Registry | Production | REST API registry service |
| mDNS | LAN discovery | Multicast DNS auto-discovery |
| Federation | Cross-organization | Registry synchronization protocol |

### 10.2 Discovery Flow

```
1. Query Registry → search by capability, tag, protocol
2. Capability Match → score agents by skill fit
3. Health Route → prefer healthy, low-latency instances
4. Protocol Negotiate → confirm shared protocol support
5. Establish Connection → complete auth handshake
```

---

## 11. L0: Transport

| Transport | Use Case | Features |
|-----------|----------|----------|
| HTTP/2 | Production, cross-network | Reliable, universal, multiplexing |
| WebSocket | Real-time bidirectional | Low latency, persistent connection |
| stdio | Local development, CLI | Fastest, zero network overhead |
| gRPC | High-performance internal | Binary encoding, strong typing, streaming |

Transport is negotiated during connection setup:

```json
{
  "offered": [
    {"type": "http2", "url": "https://agent.example.com/aurc"},
    {"type": "websocket", "url": "wss://agent.example.com/aurc/ws"}
  ],
  "preferred": "http2"
}
```

---

## 12. Comparison

| Capability | MCP | A2A | ACP | ANP | **AURC** |
|---|:---:|:---:|:---:|:---:|:---:|
| Agent Identity | ✗ | Agent Card | ✗ | DID | **AURC ID** |
| Tool Invocation | ✓ | ✗ | ✓ | ✗ | **via Bridge** |
| Agent-to-Agent | ✗ | ✓ | ✓ | ✓ | **via Bridge** |
| Runtime Lifecycle | ✗ | Task state | ✗ | ✗ | **✓ (core)** |
| Context/Memory | Resources | ✗ | ✗ | ✗ | **✓ (multi-scope)** |
| Cross-Protocol Interop | ✗ | ✗ | ✗ | ✗ | **✓ (core)** |
| Permission Enforcement | ✗ | ✗ | ✗ | ✗ | **✓ (CapABAC)** |
| Delegation Chain Audit | ✗ | ✗ | ✗ | ✗ | **✓** |
| Error Recovery | ✗ | ✗ | ✗ | ✗ | **✓ (policy engine)** |
| Human-in-the-Loop | ✗ | Input-Required | ✗ | ✗ | **✓ (standardized)** |
| Decentralized Identity | ✗ | ✗ | ✗ | ✓ | **Optional (DID compat)** |

---

## 13. Use Cases

### Scenario 1: AURC Agent calls MCP Tool

```
1. AURC Orchestrator needs web search
2. Queries Registry → finds MCP Web Search Server
3. Establishes connection via MCP Bridge
4. AURC message → translated to MCP tools/call
5. MCP Server returns result → translated back to AURC
6. Result delivered to Researcher Agent
```

### Scenario 2: AURC Agent delegates to A2A Agent

```
1. AURC Orchestrator receives complex research task
2. Discovers external expert Agent (A2A-only)
3. Creates A2A Task via A2A Bridge
4. AURC message → translated to A2A tasks/send
5. A2A Agent streams progress via SSE
6. A2A events → translated to AURC stream messages
7. Task completion → AURC context and tracking updated
```

### Scenario 3: Multi-Protocol Mixed Workflow

```
1. User request → AURC Orchestrator
2. Orchestrator delegates sub-tasks:
   ├─ Sub-task A → AURC Agent (native, direct communication)
   ├─ Sub-task B → MCP Agent (tool call via MCP Bridge)
   └─ Sub-task C → A2A Agent (delegation via A2A Bridge)
3. All sub-tasks correlated via correlation_id
4. Permissions unified via delegation_chain
5. Results aggregated → returned to user
```

---

## 14. SDK Design

### 14.1 Declarative Agent Definition

```python
@aurc_agent(
    id="aurc:gaia/researcher:v1.2",
    capabilities=["deep-research", "summarize"]
)
class ResearchAgent:
    @skill("deep-research")
    async def research(self, query: str, depth: str = "medium") -> dict:
        context = await self.harness.load_context("previous_searches", scope="agent")
        result = await self.search_web(query)
        await self.harness.save_context("previous_searches", context + [result])
        return result
```

### 14.2 Design Principles

| Principle | Description |
|-----------|-------------|
| Decorator-driven | Python decorators for zero-boilerplate agent declaration |
| Auto-injection | Harness manages lifecycle automatically |
| Protocol-transparent | Agent code doesn't know if it uses MCP or A2A |
| Type-safe | Python type hints + Pydantic for schema validation |
| Testable | MockHarness provided for unit testing |

---

## 15. Roadmap

| Phase | Scope | Duration |
|-------|-------|----------|
| **1: Foundation** | Protocol spec, core types, Harness, Registry, SDK | 4 weeks |
| **2: Messaging** | Message Bus, routing, session management | 3 weeks |
| **3: Bridges** | MCP/A2A/ACP bridges, E2E demos | 4 weeks |
| **4: Enterprise** | CapABAC, audit, health dashboard | 3 weeks |
| **5: Ecosystem** | Full docs, example agents, community | Ongoing |

---

## 16. Glossary

| Term | Definition |
|------|------------|
| **Harness** | Agent runtime management layer — lifecycle, context, error recovery |
| **Bridge** | Protocol adapter translating between AURC and external protocols |
| **Skill** | A specific capability an agent provides |
| **Delegation Chain** | Complete permission path from originator to executor |
| **CapABAC** | Capability-Attribute Based Access Control — AURC's hybrid auth model |
| **AURC ID** | Globally unique agent identifier in URN format |
| **HITL** | Human-In-The-Loop — standardized human intervention protocol |
