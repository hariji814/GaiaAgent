# [DEPRECATED] AURC Protocol Specification (Old Draft)

> **This document is SUPERSEDED by [PROTOCOL.md](../PROTOCOL.md).**
> **本文档已被 [PROTOCOL.md](../PROTOCOL.md) 取代。**
>
> This was an early draft that diverged from the implemented specification.
> It is kept here for historical reference only. Do not use this document
> for implementation or integration — refer to PROTOCOL.md instead.

---

# AURC Protocol Specification
## Agent Unified Runtime & Communication Protocol
### Version 0.1.0-draft

**Document Status**: Draft RFC  
**Created**: 2026-06-24  
**Project**: GaiaAgent (Open Source)  
**Python**: 3.10+  

---

## 文档信息 / Document Information

| 字段 / Field | 值 / Value |
|---|---|
| 标题 / Title | AURC: Agent Unified Runtime & Communication Protocol |
| 版本 / Version | 0.1.0-draft |
| 状态 / Status | Draft |
| 语言 / Languages | English, 中文 |

---

## Table of Contents

1. [Introduction / 引言](#1-introduction)
2. [Design Principles / 设计原则](#2-design-principles)
3. [Architecture Overview / 架构概览](#3-architecture-overview)
4. [Layer 1: Agent Identity / 代理身份](#4-layer-1-agent-identity)
5. [Layer 2: Runtime Harness / 运行时引擎](#5-layer-2-runtime-harness)
6. [Layer 3: Unified Message Bus / 统一消息总线](#6-layer-3-unified-message-bus)
7. [Layer 4: Protocol Bridges / 协议桥接](#7-layer-4-protocol-bridges)
8. [Layer 5: Context Correlation / 上下文关联](#8-layer-5-context-correlation)
9. [Layer 6: Transport / 传输层](#9-layer-6-transport)
10. [Layer 7: Security / 安全层](#10-layer-7-security)
11. [Layer 8: Discovery / 发现层](#11-layer-8-discovery)
12. [Protocol Comparison / 协议对比](#12-protocol-comparison)
13. [Use Case Scenarios / 使用场景](#13-use-case-scenarios)
14. [SDK Design Principles / SDK设计原则](#14-sdk-design-principles)
15. [Governance Model / 治理模型](#15-governance-model)
16. [Appendix: JSON Schemas / 附录：JSON Schema](#16-appendix-json-schemas)

---

## 1. Introduction

### 1.1 问题陈述 / Problem Statement

The 2026 AI agent ecosystem has fragmented into multiple, incompatible protocol standards:

| Protocol | Origin | Scope | Limitation |
|----------|--------|-------|------------|
| **MCP** (Model Context Protocol) | Anthropic | Agent ↔ Tool | No agent-to-agent communication; no lifecycle management |
| **A2A** (Agent-to-Agent) | Google | Agent ↔ Agent | Heavy dependency on Google Cloud; no tool bridging |
| **ACP** (Agent Communication Protocol) | IBM | Agent ↔ Agent (REST) | Minimal feature set; no streaming, no context propagation |
| **ANP** (Agent Network Protocol) | Community | Identity & Discovery | Identity-only; no messaging or runtime |

**No single protocol provides**:
- Cross-protocol message translation
- Unified agent lifecycle management
- Context propagation across protocol boundaries
- A single developer interface regardless of underlying protocol

### 1.2 AURC的目标 / AURC Goals

AURC is a **meta-protocol** — it does not replace MCP, A2A, ACP, or ANP. Instead, it:

1. **Bridges** between existing protocols through a canonical message format
2. **Manages** agent runtime lifecycle (start, pause, resume, stop, error recovery)
3. **Propagates** context, permissions, and traces across protocol boundaries
4. **Discovers** agents regardless of their native protocol
5. **Secures** communication with capability-based authorization

### 1.3 Scope

This specification defines:
- The AURC protocol wire format
- Agent identity and capability declaration
- Runtime lifecycle state machine
- Message bus and routing rules
- Bridge interfaces for MCP, A2A, ACP
- Context correlation and distributed tracing
- Transport negotiation
- Security model (authentication, authorization, delegation)
- Discovery and registry protocol

**Out of scope**:
- Specific AI model integration (use MCP for tool access)
- Agent implementation logic (AURC is protocol-only)
- UI/UX for agent management (separate dashboard spec)

---

## 2. Design Principles / 设计原则

### 2.1 Core Principles

| # | Principle | Description |
|---|-----------|-------------|
| P1 | **Protocol Agnostic** | AURC translates between protocols but does not mandate any specific one |
| P2 | **Developer-First** | Simple core API; enterprise features as optional modules |
| P3 | **Capability-Based Security** | Unforgeable capability tokens; no ambient authority |
| P4 | **Fail Gracefully** | Every component has defined failure modes and recovery strategies |
| P5 | **Observable by Default** | Distributed tracing, health checks, and audit logging are built-in |
| P6 | **Incremental Adoption** | Can wrap a single MCP tool or orchestrate 100 agents across protocols |
| P7 | **Bilingual** | All error messages, docs, and logs support English and Chinese |

### 2.2 Non-Goals

- **Not a new AI model protocol**: AURC bridges existing protocols, it doesn't compete with them
- **Not a cloud platform**: AURC is a library/protocol, not a hosted service
- **Not opinionated about AI models**: Works with any LLM via MCP or direct integration

---

## 3. Architecture Overview / 架构概览

### 3.1 Layered Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        APPLICATION LAYER                            │
│                                                                     │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │
│   │  Developer   │  │   CLI Tool   │  │  Agent Dashboard / UI    │ │
│   │  SDK (Py)    │  │              │  │                          │ │
│   └──────┬───────┘  └──────┬───────┘  └────────────┬─────────────┘ │
│          │                 │                        │               │
├──────────┴─────────────────┴────────────────────────┴───────────────┤
│                                                                      │
│                      AURC PROTOCOL STACK                             │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  Layer 8: DISCOVERY                                            │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │ │
│  │  │ Registry │  │  DNS-SD  │  │ Catalog  │  │ Health Route │   │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────────┘   │ │
│  ├────────────────────────────────────────────────────────────────┤ │
│  │  Layer 7: SECURITY                                             │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │ │
│  │  │   Auth   │  │  Authz   │  │Delegation│  │    Audit     │   │ │
│  │  │(OAuth2.1)│  │  (OCap)  │  │  Chains  │  │    Log       │   │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────────┘   │ │
│  ├────────────────────────────────────────────────────────────────┤ │
│  │  Layer 5: CONTEXT CORRELATION                                  │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐   │ │
│  │  │ Trace Context│  │  Permission  │  │   Audit Trail      │   │ │
│  │  │  (W3C TC)    │  │  Propagation │  │                    │   │ │
│  │  └──────────────┘  └──────────────┘  └────────────────────┘   │ │
│  ├────────────────────────────────────────────────────────────────┤ │
│  │  Layer 4: PROTOCOL BRIDGES                                     │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │ │
│  │  │  MCP     │  │   A2A    │  │   ACP    │  │   Custom     │   │ │
│  │  │ Bridge   │  │  Bridge  │  │  Bridge  │  │   Bridge     │   │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────────┘   │ │
│  ├────────────────────────────────────────────────────────────────┤ │
│  │  Layer 3: UNIFIED MESSAGE BUS                                  │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐   │ │
│  │  │  Canonical   │  │   Routing    │  │   Conversation     │   │ │
│  │  │   Format     │  │    Rules     │  │    Manager         │   │ │
│  │  └──────────────┘  └──────────────┘  └────────────────────┘   │ │
│  ├────────────────────────────────────────────────────────────────┤ │
│  │  Layer 2: RUNTIME HARNESS                                      │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │ │
│  │  │Lifecycle │  │ Context  │  │ Resource │  │    Error     │   │ │
│  │  │  State   │  │  Memory  │  │  Mgmt    │  │   Recovery   │   │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────────┘   │ │
│  ├────────────────────────────────────────────────────────────────┤ │
│  │  Layer 1: AGENT IDENTITY                                       │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐   │ │
│  │  │   AURC ID    │  │  Capability  │  │   DID Document     │   │ │
│  │  │   Format     │  │  Declaration │  │   Compatible       │   │ │
│  │  └──────────────┘  └──────────────┘  └────────────────────┘   │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  Layer 6: TRANSPORT (cross-cutting)                            │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │ │
│  │  │  HTTP/2  │  │WebSocket │  │  stdio   │  │    gRPC      │   │ │
│  │  │  + SSE   │  │          │  │          │  │  (optional)  │   │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────────┘   │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.2 Component Interaction Flow

```
Developer Code
     │
     ▼
┌─────────────────────────────────────────────────────────────────────┐
│  AURC SDK                                                           │
│                                                                     │
│  ┌────────────┐    ┌────────────┐    ┌────────────┐                │
│  │   Agent    │───▶│  Runtime   │───▶│  Message   │                │
│  │   Builder  │    │  Harness   │    │    Bus     │                │
│  └────────────┘    └────────────┘    └─────┬──────┘                │
│                                            │                        │
│  ┌────────────┐    ┌────────────┐    ┌─────▼──────┐                │
│  │  Security  │◀───│  Context   │◀───│  Protocol  │                │
│  │   Layer    │    │ Correlation│    │  Bridges   │                │
│  └────────────┘    └────────────┘    └─────┬──────┘                │
│                                            │                        │
└────────────────────────────────────────────┼────────────────────────┘
                                             │
                    ┌────────────────────────┼────────────────────────┐
                    │                        │                        │
               ┌────▼────┐            ┌──────▼────┐            ┌─────▼─────┐
               │   MCP   │            │    A2A    │            │    ACP    │
               │  Server │            │   Agent   │            │  Service  │
               └─────────┘            └───────────┘            └───────────┘
```

---

## 4. Layer 1: Agent Identity

### 4.1 AURC ID Format

**Design Decision: DID-compatible hierarchical identifier**

We evaluated three approaches:

| Approach | Example | Pros | Cons |
|----------|---------|------|------|
| URN | `urn:aurc:agent:my-agent` | Simple, RFC-standard | No verification, no resolution |
| DID | `did:aurc:abc123` | Cryptographic, self-sovereign | Complex, overkill for local agents |
| Custom | `aurc://agent/my-agent@v1` | Flexible | Non-standard, interoperability risk |

**Chosen: Hierarchical DID-compatible format**

```
aurc:<namespace>:<agent-type>/<instance-id>[@<version>]
```

**Grammar (ABNF)**:
```
aurc-id        = "aurc:" namespace ":" agent-path [ "@" version ]
namespace      = 1*64(ALPHA / DIGIT / "-" / ".")
agent-path     = agent-type [ "/" instance-id ]
agent-type     = 1*128(ALPHA / DIGIT / "-" / "_")
instance-id    = 1*256(ALPHA / DIGIT / "-" / "_" / ".")
version        = semver
semver         = major "." minor "." patch [ "-" pre-release ]
major          = 1*DIGIT
minor          = 1*DIGIT
patch          = 1*DIGIT
pre-release    = 1*DIGIT / 1*ALPHA *(ALPHA / DIGIT / "-" / ".")
```

**Examples**:
```
aurc:anthropic:claude-agent/sonnet-4@2.1.0
aurc:self:my-custom-agent@1.0.0
aurc:registry.example.com:finance-agent/instance-abc@0.5.2
aurc:local:data-processor@0.1.0-dev
```

**Design Rationale**:
- `namespace` enables decentralized registration (like DID methods)
- `agent-type` classifies the agent's role (e.g., "finance-agent")
- `instance-id` distinguishes multiple instances of the same type
- `version` enables capability versioning and A/B testing
- The format is simple enough to use without a DID library, but can be wrapped in a DID document for interoperability

### 4.2 AURC ID Resolution

AURC IDs resolve to **Agent Descriptors** via a pluggable resolution mechanism:

```python
class AgentDescriptor:
    """Resolved description of an AURC agent."""
    
    id: str                          # The AURC ID
    display_name: str                # Human-readable name
    description: str                 # Agent description (bilingual)
    protocol: Literal["mcp", "a2a", "acp", "aurc"]  # Native protocol
    capabilities: list[Capability]   # Declared capabilities
    transports: list[TransportInfo]  # Supported transports
    auth_methods: list[AuthMethod]   # Supported auth methods
    health_endpoint: str | None      # Health check URL
    metadata: dict[str, Any]         # Arbitrary metadata
    
    # DID Document compatibility
    did_document: dict | None        # Optional W3C DID Document
```

**Resolution Priority**:
1. **Local registry** (in-process, fastest)
2. **Network registry** (HTTP lookup)
3. **DNS-SD** (local network discovery)
4. **Direct connection** (if transport info is embedded in ID metadata)

### 4.3 Capability Declaration

Capabilities are hierarchical, versioned declarations of what an agent can do:

```python
class Capability:
    """A declared agent capability."""
    
    name: str              # Hierarchical name: "file.read", "code.execute"
    version: str           # Capability version: "1.2.0"
    description: str       # Human-readable description
    parameters: dict       # JSON Schema for parameters
    returns: dict          # JSON Schema for return value
    scope: Scope           # Required scope/permissions
    idempotent: bool       # Whether repeated calls are safe
    streaming: bool        # Whether this capability supports streaming
    rate_limit: int | None # Max calls per minute (None = unlimited)
```

**Capability Namespace Hierarchy**:
```
file
  file.read
  file.write
  file.delete
code
  code.execute
  code.analyze
  code.generate
data
  data.query
  data.transform
  data.visualize
web
  web.search
  web.fetch
  web.browse
communication
  communication.send
  communication.receive
  communication.delegate
system
  system.monitor
  system.configure
```

### 4.4 DID Document Compatibility

For interoperability with the ANP (Agent Network Protocol) and W3C DID ecosystem, AURC agents can optionally publish a DID Document:

```json
{
  "@context": [
    "https://www.w3.org/ns/did/v1",
    "https://w3id.org/security/multikey/v1"
  ],
  "id": "did:aurc:anthropic:claude-agent/sonnet-4",
  "alsoKnownAs": ["aurc:anthropic:claude-agent/sonnet-4@2.1.0"],
  "verificationMethod": [{
    "id": "did:aurc:anthropic:claude-agent/sonnet-4#key-1",
    "type": "Ed25519VerificationKey2020",
    "controller": "did:aurc:anthropic:claude-agent/sonnet-4",
    "publicKeyMultibase": "z6MkjL..."
  }],
  "authentication": ["#key-1"],
  "service": [{
    "id": "#aurc-endpoint",
    "type": "AURCService",
    "serviceEndpoint": "https://api.anthropic.com/aurc/v1",
    "capabilities": ["file.read", "code.execute", "web.search"],
    "transports": ["https", "websocket"],
    "protocol": "aurc"
  }]
}
```

---

## 5. Layer 2: Runtime Harness

### 5.1 Agent Lifecycle State Machine

This is the **core innovation** of AURC — no existing protocol provides a standardized agent lifecycle.

#### 5.1.1 States

```python
class AgentState(Enum):
    """Agent lifecycle states."""
    
    CREATED      = "created"       # Instance exists, not initialized
    INITIALIZING = "initializing"  # Loading config, connecting deps
    IDLE         = "idle"          # Ready to accept work
    RUNNING      = "running"       # Actively processing a task
    PAUSED       = "paused"        # Suspended, context preserved
    STOPPING     = "stopping"      # Graceful shutdown in progress
    STOPPED      = "stopped"       # Clean shutdown complete
    ERROR        = "error"         # Unrecoverable error
    RECOVERING   = "recovering"    # Attempting automatic recovery
```

#### 5.1.2 State Transition Diagram

```
                    ┌──────────────────────────────────────────────┐
                    │                                              │
                    ▼                                              │
              ┌──────────┐    init()     ┌──────────────┐         │
              │ CREATED  │──────────────▶│ INITIALIZING │         │
              └──────────┘               └──────┬───────┘         │
                                                │                  │
                                    ┌───────────┴───────────┐     │
                                    │                       │     │
                              ready()│                error()│     │
                                    │                       │     │
                                    ▼                       ▼     │
                              ┌──────────┐          ┌──────────┐  │
                    ┌────────▶│   IDLE   │          │  ERROR   │  │
                    │         └────┬─────┘          └────┬─────┘  │
                    │              │                      │        │
                    │        task()│                recover()│     │
                    │              │                      │        │
                    │              ▼                      ▼        │
                    │     ┌──────────────┐      ┌──────────────┐  │
                    │     │   RUNNING    │      │  RECOVERING  │  │
                    │     └──┬───┬───┬──┘      └──┬────────┬──┘  │
                    │        │   │   │             │        │     │
                    │        │   │   │      success()   fail()   │
                    │        │   │   │             │        │     │
                    │        │   │   │             │        │     │
                    │        │   │   │             ▼        ▼     │
                    │        │   │   │         ┌──────┐  ┌─────┐ │
                    │        │   │   │         │ IDLE │  │STOPPED││
                    │        │   │   │         └──────┘  └─────┘ │
                    │        │   │   │                             │
         complete() │  pause()│   │   │stop()                      │
                    │        │   │   │                             │
                    │        │   │   ▼                             │
                    │        │   │ ┌───────────┐                  │
                    │        │   └▶│  STOPPING │──────────────────┘
                    │        │     └─────┬─────┘  shutdown()
                    │        │           │
                    │        ▼           │
                    │   ┌────────┐       │
                    │   │ PAUSED │       │
                    │   └──┬──┬──┘       │
                    │      │  │          │
                    │resume()│  │stop()   │
                    │      │  │          │
                    │      │  └──────────┘
                    │      │
                    └──────┘
```

#### 5.1.3 State Transition Table

| From State | Event | To State | Action |
|------------|-------|----------|--------|
| CREATED | `init()` | INITIALIZING | Load config, connect dependencies |
| INITIALIZING | `ready()` | IDLE | Mark agent as available |
| INITIALIZING | `error()` | ERROR | Log initialization failure |
| IDLE | `task_received()` | RUNNING | Begin task processing |
| RUNNING | `task_completed()` | IDLE | Clean up task state |
| RUNNING | `pause_requested()` | PAUSED | Save context, suspend execution |
| RUNNING | `stop_requested()` | STOPPING | Begin graceful shutdown |
| RUNNING | `error()` | ERROR | Log error, attempt classification |
| PAUSED | `resume()` | RUNNING | Restore context, resume execution |
| PAUSED | `stop_requested()` | STOPPING | Begin graceful shutdown |
| STOPPING | `shutdown_complete()` | STOPPED | Release all resources |
| ERROR | `recover()` | RECOVERING | Attempt recovery strategy |
| RECOVERING | `recovery_success()` | IDLE | Resume normal operation |
| RECOVERING | `recovery_failed()` | STOPPED | Terminal failure, release resources |
| STOPPED | `restart()` | INITIALIZING | Re-initialize agent |

#### 5.1.4 Transition Guards

Every transition has **guards** (preconditions) and **effects** (side effects):

```python
class Transition:
    """A state machine transition with guards and effects."""
    
    from_state: AgentState
    to_state: AgentState
    event: str
    guards: list[Guard]       # Preconditions that must be true
    effects: list[Effect]     # Side effects to execute
    timeout: timedelta | None # Max time for this transition
    on_timeout: AgentState    # State to enter on timeout
```

**Example Guards**:
- `RUNNING → PAUSED`: Guard = "no active transactions" OR "all transactions are pausable"
- `IDLE → RUNNING`: Guard = "all dependencies healthy"
- `ERROR → RECOVERING`: Guard = "recovery attempts < max_retries"

### 5.2 Context and Memory Management

#### 5.2.1 Context Scopes

AURC defines four context scopes with clear lifetimes and sharing rules:

```python
class ContextScope(Enum):
    """Context scope levels."""
    
    SESSION = "session"   # Per-conversation, ephemeral
    AGENT   = "agent"     # Per-agent instance, persistent
    SHARED  = "shared"    # Cross-agent, workspace-scoped
    GLOBAL  = "global"    # System-wide, read-only for agents
```

| Scope | Lifetime | Visibility | Mutability | Example |
|-------|----------|------------|------------|---------|
| SESSION | Single conversation | Single agent + caller | Read/Write | Chat history, task state |
| AGENT | Agent instance lifetime | Single agent | Read/Write | Agent memory, learned preferences |
| SHARED | Workspace lifetime | Multiple agents in workspace | Read/Write | Shared documents, workspace config |
| GLOBAL | System lifetime | All agents | Read-only | System config, global policies |

#### 5.2.2 Context Data Structure

```python
class ContextStore:
    """Hierarchical context storage with scope-based access."""
    
    class Entry:
        key: str
        value: Any
        scope: ContextScope
        created_at: datetime
        updated_at: datetime
        ttl: timedelta | None       # Auto-expiry
        version: int                 # Optimistic locking
        encrypted: bool              # Whether value is encrypted
        tags: list[str]              # For search/filtering
    
    def get(self, key: str, scope: ContextScope) -> Entry | None: ...
    def set(self, key: str, value: Any, scope: ContextScope, 
            ttl: timedelta | None = None) -> Entry: ...
    def delete(self, key: str, scope: ContextScope) -> bool: ...
    def list(self, scope: ContextScope, 
             prefix: str | None = None) -> list[Entry]: ...
    def snapshot(self, scope: ContextScope) -> ContextSnapshot: ...
    def restore(self, snapshot: ContextSnapshot) -> None: ...
```

#### 5.2.3 Memory Subsystem

The memory subsystem provides long-term persistent storage for agents:

```python
class MemoryStore:
    """Agent memory with semantic search and forgetting."""
    
    def remember(self, content: str, metadata: dict | None = None,
                 importance: float = 0.5) -> MemoryEntry: ...
    
    def recall(self, query: str, limit: int = 10,
               min_relevance: float = 0.7) -> list[MemoryEntry]: ...
    
    def forget(self, entry_id: str) -> None: ...
    
    def consolidate(self) -> ConsolidationReport:
        """Merge similar memories, prune low-importance ones."""
        ...
    
    def get_statistics(self) -> MemoryStatistics:
        """Get memory usage statistics."""
        ...

class MemoryEntry:
    id: str
    content: str
    embedding: list[float] | None   # Vector embedding for similarity search
    importance: float               # 0.0 - 1.0
    access_count: int               # How often this memory is recalled
    last_accessed: datetime
    created_at: datetime
    metadata: dict[str, Any]
    related_ids: list[str]          # Links to related memories
```

### 5.3 Health Monitoring

```python
class HealthStatus:
    """Agent health status."""
    
    state: AgentState
    healthy: bool
    uptime: timedelta
    last_heartbeat: datetime
    
    # Resource metrics
    cpu_percent: float
    memory_bytes: int
    memory_limit_bytes: int
    
    # Task metrics
    active_tasks: int
    completed_tasks: int
    failed_tasks: int
    avg_task_duration: timedelta
    
    # Dependency health
    dependencies: dict[str, DependencyHealth]
    
    # Custom health indicators
    indicators: dict[str, HealthIndicator]

class HealthIndicator:
    name: str
    status: Literal["healthy", "degraded", "unhealthy"]
    message: str | None
    value: float | None
    threshold: float | None
```

**Health Check Protocol**:
1. Runtime harness sends `HEARTBEAT` every `heartbeat_interval` (default: 30s)
2. Agent must respond within `heartbeat_timeout` (default: 10s)
3. Missing 3 consecutive heartbeats → mark as `degraded`
4. Missing 5 consecutive heartbeats → trigger `error()` transition

### 5.4 Error Recovery

#### 5.4.1 Error Classification

```python
class ErrorClass(Enum):
    """Error classification for recovery strategy selection."""
    
    TRANSIENT       = "transient"        # Temporary, retry likely to succeed
    RESOURCE        = "resource"         # Resource exhaustion, backoff needed
    CONFIGURATION   = "configuration"    # Bad config, requires human intervention
    DEPENDENCY      = "dependency"       # External dependency failure
    DATA            = "data"             # Bad input data
    INTERNAL        = "internal"         # Agent internal error
    PERMISSION      = "permission"       # Insufficient permissions
    TIMEOUT         = "timeout"          # Operation timed out
    FATAL           = "fatal"            # Unrecoverable, must stop
```

#### 5.4.2 Recovery Strategies

```python
class RecoveryStrategy(Enum):
    """Error recovery strategies."""
    
    RETRY              = "retry"               # Same input, same agent
    RETRY_WITH_BACKOFF = "retry_with_backoff"  # Exponential backoff
    CHECKPOINT_ROLLBACK = "checkpoint_rollback" # Rollback to last checkpoint
    FALLBACK           = "fallback"            # Use fallback agent
    DEGRADE            = "degrade"             # Continue with reduced capability
    HUMAN_IN_THE_LOOP  = "human_in_the_loop"   # Escalate to human
    ABORT              = "abort"               # Terminal failure

class RecoveryPolicy:
    """Configurable recovery policy."""
    
    max_retries: int = 3
    backoff_base: timedelta = timedelta(seconds=1)
    backoff_max: timedelta = timedelta(minutes=5)
    backoff_multiplier: float = 2.0
    strategies: dict[ErrorClass, list[RecoveryStrategy]]
    fallback_agent_id: str | None
    human_escalation_timeout: timedelta = timedelta(minutes=5)
    
    # Default strategy mapping
    DEFAULT_STRATEGIES = {
        ErrorClass.TRANSIENT: [RETRY_WITH_BACKOFF, RETRY, ABORT],
        ErrorClass.RESOURCE: [RETRY_WITH_BACKOFF, DEGRADE, ABORT],
        ErrorClass.DEPENDENCY: [RETRY_WITH_BACKOFF, FALLBACK, DEGRADE],
        ErrorClass.TIMEOUT: [RETRY_WITH_BACKOFF, FALLBACK, ABORT],
        ErrorClass.DATA: [HUMAN_IN_THE_LOOP, ABORT],
        ErrorClass.CONFIGURATION: [HUMAN_IN_THE_LOOP, ABORT],
        ErrorClass.PERMISSION: [ABORT],
        ErrorClass.INTERNAL: [CHECKPOINT_ROLLBACK, RETRY, ABORT],
        ErrorClass.FATAL: [ABORT],
    }
```

### 5.5 Human-in-the-Loop Integration

```python
class HumanIntervention:
    """A request for human intervention."""
    
    intervention_id: str
    agent_id: str
    reason: str
    context: dict[str, Any]
    options: list[HumanOption] | None  # Pre-defined options for the human
    timeout: timedelta
    priority: Literal["low", "normal", "high", "critical"]
    created_at: datetime
    
    # Bilingual
    reason_zh: str | None  # Chinese translation of reason

class HumanOption:
    """A pre-defined option for human decision."""
    
    option_id: str
    label: str
    label_zh: str | None
    description: str
    action: dict[str, Any]  # Action to execute if selected
```

**Human-in-the-loop flow**:
```
Agent RUNNING
    │
    ├─ encounters uncertainty / permission needed / error
    │
    ▼
Creates HumanIntervention
    │
    ├─ state: RUNNING → PAUSED
    │
    ▼
Notification sent to configured human channel
    │
    ├─ (Slack, Email, Dashboard, Webhook)
    │
    ▼
Human responds with decision
    │
    ├─ option selected / custom response / timeout
    │
    ▼
Agent resumes with human context
    │
    ├─ state: PAUSED → RUNNING
    │
    ▼
Task continues with human-provided context
```

### 5.6 Resource Management

```python
class ResourceLimits:
    """Resource limits for an agent."""
    
    max_memory_bytes: int = 1024 * 1024 * 1024   # 1 GB default
    max_cpu_percent: float = 100.0
    max_concurrent_tasks: int = 10
    max_open_connections: int = 100
    max_context_size_bytes: int = 100 * 1024 * 1024  # 100 MB
    max_execution_time: timedelta = timedelta(hours=1)
    
    # Rate limiting
    max_requests_per_minute: int = 1000
    max_tokens_per_minute: int = 100000

class ResourceManager:
    """Monitors and enforces resource limits."""
    
    def check_limits(self) -> ResourceReport: ...
    def acquire(self, resource_type: str, amount: float) -> ResourceHandle: ...
    def release(self, handle: ResourceHandle) -> None: ...
    def get_usage(self) -> ResourceUsage: ...
```

---

## 6. Layer 3: Unified Message Bus

### 6.1 Serialization Decision

| Format | Human-Readable | Performance | Schema Support | Ecosystem |
|--------|---------------|-------------|----------------|-----------|
| **JSON** | Yes | Good | JSON Schema | Universal |
| MessagePack | No | Excellent | Limited | Good |
| Protobuf | No | Excellent | .proto files | Google ecosystem |
| CBOR | No | Excellent | CDDL | IoT-focused |

**Decision: JSON as canonical, MessagePack as binary optimization**

- **JSON** is the canonical wire format (human-readable, universal tooling)
- **MessagePack** is available as a binary optimization (negotiated during handshake)
- Both formats use the same schema; only encoding differs
- The `content-type` header or transport metadata indicates which encoding is used

### 6.2 Canonical Message Format

```json
{
  "$schema": "https://aurc.dev/schemas/message/v0.1.0.json",
  
  "aurc_version": "0.1.0",
  "message_id": "01928a3b-7c4d-7000-8000-000000000001",
  "correlation_id": "01928a3b-7c4d-7000-8000-000000000000",
  "causation_id": null,
  "timestamp": "2026-06-24T10:30:00.000Z",
  
  "source": "aurc:self:orchestrator/main@1.0.0",
  "destination": "aurc:anthropic:claude-agent/sonnet-4@2.1.0",
  "reply_to": null,
  
  "message_type": "request",
  "content_type": "application/json",
  
  "context": {
    "trace_id": "abc123def456",
    "span_id": "span789",
    "parent_span_id": null,
    "session_id": "session-001",
    "conversation_id": "conv-001",
    "permissions": {
      "capabilities": ["file.read", "web.search"],
      "scope": "session",
      "expires_at": "2026-06-24T11:30:00.000Z"
    }
  },
  
  "payload": {
    "method": "agent.invoke",
    "params": {
      "task": "Analyze the provided dataset and generate a summary report",
      "input_data": { "type": "reference", "uri": "context://shared/dataset-001" }
    }
  },
  
  "metadata": {
    "priority": "normal",
    "ttl_seconds": 300,
    "idempotency_key": "idem-key-001",
    "language": "en"
  }
}
```

### 6.3 Message Types

```python
class MessageType(Enum):
    """AURC message types."""
    
    REQUEST      = "request"       # Expects a response
    RESPONSE     = "response"      # Reply to a request
    NOTIFICATION = "notification"  # Fire-and-forget
    STREAM_START = "stream_start"  # Begin a streaming response
    STREAM_CHUNK = "stream_chunk"  # Streaming data chunk
    STREAM_END   = "stream_end"    # End of streaming response
    DELEGATION   = "delegation"    # Forward task to another agent
    HEARTBEAT    = "heartbeat"     # Keep-alive ping
    ERROR        = "error"         # Error notification
```

#### 6.3.1 Request/Response Pattern

```
Agent A                    Agent B
  │                          │
  │──── REQUEST ────────────▶│  message_id: "req-001"
  │                          │  correlation_id: null
  │                          │
  │◀──── RESPONSE ───────────│  message_id: "resp-001"
  │                          │  correlation_id: "req-001"
```

#### 6.3.2 Streaming Pattern

```
Agent A                    Agent B
  │                          │
  │──── REQUEST ────────────▶│  message_id: "req-002"
  │                          │
  │◀──── STREAM_START ───────│  correlation_id: "req-002"
  │◀──── STREAM_CHUNK ───────│  chunk_index: 0
  │◀──── STREAM_CHUNK ───────│  chunk_index: 1
  │◀──── STREAM_CHUNK ───────│  chunk_index: 2
  │◀──── STREAM_END ─────────│  total_chunks: 3
```

#### 6.3.3 Delegation Pattern

```
Agent A              Agent B              Agent C
  │                    │                    │
  │── REQUEST ────────▶│                    │
  │                    │── DELEGATION ─────▶│
  │                    │   (correlation_id   │
  │                    │    preserved)       │
  │                    │◀── RESPONSE ───────│
  │◀── RESPONSE ──────│                    │
```

### 6.4 Conversation and Thread Management

```python
class ConversationManager:
    """Manages conversations and threads."""
    
    def create_conversation(
        self,
        participants: list[str],
        context: dict | None = None
    ) -> Conversation: ...
    
    def create_thread(
        self,
        conversation_id: str,
        parent_thread_id: str | None = None,
        topic: str | None = None
    ) -> Thread: ...
    
    def send_message(
        self,
        conversation_id: str,
        thread_id: str | None,
        message: Message
    ) -> str: ...
    
    def get_history(
        self,
        conversation_id: str,
        thread_id: str | None = None,
        limit: int = 100,
        before: datetime | None = None
    ) -> list[Message]: ...

class Conversation:
    id: str
    participants: list[str]          # AURC IDs
    created_at: datetime
    context: dict[str, Any]
    threads: list[Thread]
    state: Literal["active", "archived", "closed"]

class Thread:
    id: str
    conversation_id: str
    parent_thread_id: str | None
    topic: str | None
    messages: list[str]              # Message IDs
    created_at: datetime
    state: Literal["active", "resolved", "closed"]
```

### 6.5 Routing Rules

Messages are routed based on the following priority:

1. **Direct routing**: If `destination` is a known, connected agent → send directly
2. **Bridge routing**: If `destination` uses a different protocol → route through appropriate bridge
3. **Registry lookup**: If `destination` is not locally known → query registry
4. **Broadcast**: If `destination` is `null` and `message_type` is `notification` → broadcast to subscribers

```python
class Router:
    """Message router with pluggable strategies."""
    
    def route(self, message: Message) -> RouteDecision:
        """Determine how to deliver a message."""
        
        # Priority 1: Direct connection
        if message.destination in self.local_agents:
            return RouteDecision(
                strategy="direct",
                target=self.local_agents[message.destination]
            )
        
        # Priority 2: Protocol bridge
        descriptor = self.registry.resolve(message.destination)
        if descriptor and descriptor.protocol != "aurc":
            bridge = self.get_bridge(descriptor.protocol)
            return RouteDecision(
                strategy="bridge",
                bridge=bridge,
                target=descriptor
            )
        
        # Priority 3: Registry lookup
        if descriptor and descriptor.transports:
            return RouteDecision(
                strategy="remote",
                target=descriptor
            )
        
        # Priority 4: Broadcast (for notifications only)
        if message.message_type == MessageType.NOTIFICATION:
            return RouteDecision(
                strategy="broadcast",
                targets=self.get_subscribers(message.payload.get("topic"))
            )
        
        raise RoutingError(f"Cannot route message to {message.destination}")
```

---

## 7. Layer 4: Protocol Bridges

### 7.1 Bridge Interface

The bridge pattern is the key mechanism that allows AURC to interoperate with existing protocols.

```python
class ProtocolBridge(ABC):
    """Abstract base class for protocol bridges."""
    
    @property
    @abstractmethod
    def protocol_name(self) -> str:
        """The protocol this bridge handles (e.g., 'mcp', 'a2a', 'acp')."""
        ...
    
    @abstractmethod
    async def connect(self, endpoint: str, config: dict | None = None) -> None:
        """Establish connection to a protocol endpoint."""
        ...
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Close the connection."""
        ...
    
    @abstractmethod
    async def translate_outbound(self, message: AURCMessage) -> Any:
        """Translate an AURC message to the native protocol format."""
        ...
    
    @abstractmethod
    async def translate_inbound(self, native_message: Any) -> AURCMessage:
        """Translate a native protocol message to AURC format."""
        ...
    
    @abstractmethod
    async def map_capabilities(
        self, native_capabilities: list[dict]
    ) -> list[Capability]:
        """Map native protocol capabilities to AURC capabilities."""
        ...
    
    @abstractmethod
    def can_handle(self, agent_id: str) -> bool:
        """Check if this bridge can communicate with the given agent."""
        ...
    
    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Whether the bridge is currently connected."""
        ...
```

### 7.2 MCP Bridge Implementation

```python
class MCPBridge(ProtocolBridge):
    """Bridge between AURC and Model Context Protocol."""
    
    protocol_name = "mcp"
    
    def __init__(self):
        self._client: MCPClient | None = None
        self._tools: dict[str, MCPTool] = {}
        self._resources: dict[str, MCPResource] = {}
    
    async def connect(self, endpoint: str, config: dict | None = None) -> None:
        """Connect to an MCP server.
        
        Supports:
        - stdio: "stdio://path/to/server"
        - HTTP: "http://localhost:3000/mcp"
        - SSE: "sse://localhost:3000/mcp"
        """
        self._client = MCPClient()
        await self._client.connect(endpoint)
        
        # Discover available tools and resources
        self._tools = await self._client.list_tools()
        self._resources = await self._client.list_resources()
    
    async def translate_outbound(self, message: AURCMessage) -> MCPMessage:
        """AURC → MCP translation.
        
        AURC message.method → MCP method mapping:
        - "tool.invoke" → "tools/call"
        - "resource.read" → "resources/read"
        - "resource.list" → "resources/list"
        - "prompt.render" → "prompts/get"
        """
        method_map = {
            "tool.invoke": "tools/call",
            "resource.read": "resources/read",
            "resource.list": "resources/list",
            "prompt.render": "prompts/get",
        }
        
        mcp_method = method_map.get(message.payload.get("method"))
        if not mcp_method:
            raise BridgeError(
                f"Cannot translate AURC method '{message.payload.get('method')}' to MCP"
            )
        
        return MCPMessage(
            jsonrpc="2.0",
            id=message.message_id,
            method=mcp_method,
            params=self._translate_params(message.payload.get("params", {}))
        )
    
    async def translate_inbound(self, native_message: MCPMessage) -> AURCMessage:
        """MCP → AURC translation."""
        return AURCMessage(
            message_id=native_message.id,
            correlation_id=native_message.id,
            message_type=MessageType.RESPONSE if native_message.result else MessageType.ERROR,
            payload={
                "result": native_message.result,
                "error": native_message.error
            },
            context=ContextInfo(
                # MCP has no native tracing; we inject our trace context
                trace_id=self._current_trace_id,
                span_id=generate_span_id()
            )
        )
    
    async def map_capabilities(self, native_capabilities: list[dict]) -> list[Capability]:
        """Map MCP tools/resources to AURC capabilities."""
        capabilities = []
        
        for tool in native_capabilities:
            capabilities.append(Capability(
                name=f"mcp.tool.{tool['name']}",
                version="1.0.0",
                description=tool.get("description", ""),
                parameters=tool.get("inputSchema", {}),
                returns={},  # MCP doesn't declare return schemas
                scope=Scope.READ,  # Conservative default
                idempotent=False,  # Conservative default
                streaming=False,
                rate_limit=None
            ))
        
        return capabilities
```

### 7.3 A2A Bridge Implementation

```python
class A2ABridge(ProtocolBridge):
    """Bridge between AURC and Google's Agent-to-Agent protocol."""
    
    protocol_name = "a2a"
    
    async def translate_outbound(self, message: AURCMessage) -> A2AMessage:
        """AURC → A2A translation.
        
        Key mappings:
        - AURC conversation_id → A2A task_id
        - AURC message_type → A2A message role
        - AURC context.permissions → A2A authentication header
        """
        a2a_task = A2ATask(
            id=message.context.conversation_id or generate_id(),
            status=A2ATaskStatus(state="submitted"),
            messages=[A2AMessage(
                role="user",  # AURC agents appear as "user" to A2A
                parts=self._convert_payload_to_parts(message.payload),
                metadata={
                    "aurc_source": message.source,
                    "aurc_trace_id": message.context.trace_id
                }
            )]
        )
        return a2a_task
    
    async def translate_inbound(self, native_message: A2ATask) -> AURCMessage:
        """A2A → AURC translation."""
        # A2A tasks map to AURC responses
        result_parts = native_message.artifacts or []
        
        return AURCMessage(
            message_id=generate_id(),
            correlation_id=native_message.metadata.get("aurc_source_id"),
            message_type=MessageType.RESPONSE,
            payload={
                "result": {
                    "content": [part.dict() for part in result_parts],
                    "status": native_message.status.state
                }
            },
            context=ContextInfo(
                trace_id=native_message.messages[0].metadata.get("aurc_trace_id"),
                span_id=generate_span_id()
            )
        )
```

### 7.4 ACP Bridge Implementation

```python
class ACPBridge(ProtocolBridge):
    """Bridge between AURC and IBM's Agent Communication Protocol."""
    
    protocol_name = "acp"
    
    async def translate_outbound(self, message: AURCMessage) -> ACPMessage:
        """AURC → ACP translation.
        
        ACP is REST-based, so we map to HTTP operations:
        - AURC request → ACP POST /agents/{id}/messages
        - AURC notification → ACP POST /agents/{id}/notifications
        """
        return ACPMessage(
            type="message",
            source=message.source,
            content=message.payload,
            metadata={
                "aurc_correlation_id": message.correlation_id,
                "aurc_trace_id": message.context.trace_id
            }
        )
    
    async def translate_inbound(self, native_message: ACPResponse) -> AURCMessage:
        """ACP → AURC translation."""
        return AURCMessage(
            message_id=generate_id(),
            correlation_id=native_message.metadata.get("aurc_correlation_id"),
            message_type=MessageType.RESPONSE,
            payload={"result": native_message.content},
            context=ContextInfo(
                trace_id=native_message.metadata.get("aurc_trace_id"),
                span_id=generate_span_id()
            )
        )
```

### 7.5 Bridge Pattern: Cross-Protocol Invocation

**Scenario**: An AURC orchestrator agent calls an MCP-only tool agent.

```
┌─────────────────────────────────────────────────────────────┐
│                    AURC Message Flow                         │
│                                                             │
│  ┌──────────────┐                                           │
│  │  AURC Agent  │                                           │
│  │ (Orchestrator│                                           │
│  │              │                                           │
│  │  Sends:      │                                           │
│  │  AURC        │                                           │
│  │  REQUEST     │                                           │
│  └──────┬───────┘                                           │
│         │                                                   │
│         ▼                                                   │
│  ┌──────────────┐    ┌──────────────────────┐              │
│  │   Router     │───▶│   MCP Bridge         │              │
│  │              │    │                      │              │
│  │  Detects     │    │  1. translate_       │              │
│  │  target is   │    │     outbound()       │              │
│  │  MCP agent   │    │                      │              │
│  └──────────────┘    │  2. AURC REQUEST     │              │
│                      │     → MCP tools/call │              │
│                      │                      │              │
│                      │  3. Send via MCP     │              │
│                      │     transport        │              │
│                      └──────────┬───────────┘              │
│                                 │                          │
└─────────────────────────────────┼──────────────────────────┘
                                  │
                                  ▼
                           ┌──────────────┐
                           │  MCP Server  │
                           │  (Tool Agent) │
                           │              │
                           │  Receives:   │
                           │  JSON-RPC    │
                           │  tools/call  │
                           └──────┬───────┘
                                  │
                                  │ Response
                                  ▼
┌─────────────────────────────────────────────────────────────┐
│  ┌──────────────────────┐                                   │
│  │   MCP Bridge         │                                   │
│  │                      │                                   │
│  │  4. Receive MCP      │                                   │
│  │     response         │                                   │
│  │                      │                                   │
│  │  5. translate_       │                                   │
│  │     inbound()        │                                   │
│  │                      │                                   │
│  │  6. MCP result       │                                   │
│  │     → AURC RESPONSE  │                                   │
│  └──────────┬───────────┘                                   │
│             │                                               │
│             ▼                                               │
│  ┌──────────────┐                                           │
│  │  AURC Agent  │                                           │
│  │              │                                           │
│  │  Receives:   │                                           │
│  │  AURC        │                                           │
│  │  RESPONSE    │                                           │
│  └──────────────┘                                           │
└─────────────────────────────────────────────────────────────┘
```

### 7.6 Capability Mapping

Different protocols expose capabilities differently. The bridge must normalize them:

| AURC Capability | MCP Equivalent | A2A Equivalent | ACP Equivalent |
|----------------|---------------|----------------|----------------|
| `tool.invoke` | `tools/call` | Task message | POST /messages |
| `resource.read` | `resources/read` | N/A | GET /resources |
| `resource.list` | `resources/list` | N/A | N/A |
| `prompt.render` | `prompts/get` | N/A | N/A |
| `agent.delegate` | N/A | Task delegation | POST /delegate |
| `stream.subscribe` | SSE events | Streaming parts | N/A |
| `file.read` | `resources/read` (file://) | Artifact | N/A |

---

## 8. Layer 5: Context Correlation

### 8.1 Distributed Tracing

AURC uses a W3C Trace Context-inspired model, extended for multi-protocol environments:

```python
class TraceContext:
    """Distributed trace context following W3C Trace Context spec."""
    
    trace_id: str          # 128-bit trace identifier (hex)
    span_id: str           # 64-bit span identifier (hex)
    parent_span_id: str | None  # Parent span
    trace_state: dict[str, str] # Vendor-specific trace state
    
    # AURC extensions
    agent_chain: list[str]  # Ordered list of agent AURC IDs in this trace
    protocol_hops: list[ProtocolHop]  # Protocol transitions
    permission_chain: list[PermissionChange]  # Permission changes along the trace

class ProtocolHop:
    """Records a protocol boundary crossing."""
    
    from_protocol: str     # e.g., "aurc"
    to_protocol: str       # e.g., "mcp"
    bridge_id: str         # Which bridge handled the transition
    timestamp: datetime
    context_loss: list[str]  # What context was lost in translation
```

### 8.2 Permission Propagation

**Core Rule: Permissions can only be attenuated (narrowed), never escalated, when crossing protocol boundaries.**

```python
class PermissionPropagator:
    """Propagates permissions across protocol boundaries with attenuation."""
    
    def propagate(
        self,
        permissions: PermissionSet,
        target_protocol: str,
        bridge: ProtocolBridge
    ) -> PermissionSet:
        """Propagate permissions to a target protocol.
        
        Rules:
        1. Permissions can only be narrowed (intersection)
        2. Protocol-specific limitations are applied
        3. All changes are logged for audit
        """
        # Start with current permissions
        propagated = permissions.copy()
        
        # Apply protocol-specific limitations
        protocol_limits = self.get_protocol_limits(target_protocol)
        propagated = propagated.intersect(protocol_limits)
        
        # Apply bridge-specific limitations
        bridge_limits = bridge.get_capability_limits()
        propagated = propagated.intersect(bridge_limits)
        
        # Log the attenuation
        if propagated != permissions:
            self.audit_log.record_attenuation(
                original=permissions,
                propagated=propagated,
                reason=f"Protocol boundary: aurc → {target_protocol}"
            )
        
        return propagated
```

**Example Permission Attenuation**:
```
Original permissions (AURC agent):
  - file.read, file.write, code.execute, web.search

After MCP bridge (MCP has no write concept for tools):
  - file.read, code.execute, web.search
  [LOST: file.write - MCP tools are invoked, not written to]

After ACP bridge (ACP has no streaming):
  - file.read, code.execute
  [LOST: web.search - requires streaming which ACP doesn't support]
```

### 8.3 Audit Logging

```python
class AuditLog:
    """Immutable audit log for all protocol interactions."""
    
    def record(self, event: AuditEvent) -> str:
        """Record an audit event. Returns event ID."""
        ...
    
    def query(
        self,
        agent_id: str | None = None,
        trace_id: str | None = None,
        event_type: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100
    ) -> list[AuditEvent]:
        """Query audit events with filters."""
        ...

class AuditEvent:
    id: str
    timestamp: datetime
    trace_id: str
    
    event_type: Literal[
        "message_sent",
        "message_received",
        "bridge_translation",
        "permission_attenuation",
        "delegation",
        "error",
        "state_transition",
        "human_intervention"
    ]
    
    agent_id: str
    details: dict[str, Any]
    
    # Cryptographic integrity
    previous_hash: str | None  # Hash of previous event (blockchain-style chain)
    event_hash: str            # Hash of this event
```

---

## 9. Layer 6: Transport

### 9.1 Supported Transports

| Transport | Use Case | Bidirectional | Streaming | MCP Compatible |
|-----------|----------|---------------|-----------|----------------|
| **HTTP/2 + SSE** | Inter-service, REST APIs | Request/Response + Push | Yes (SSE) | Yes |
| **WebSocket** | Real-time bidirectional | Yes | Yes | No |
| **stdio** | Local process communication | Yes | Yes | Yes |
| **gRPC** | High-performance internal | Yes | Yes | No |

### 9.2 Transport Negotiation

During connection establishment, agents negotiate the transport:

```python
class TransportNegotiation:
    """Transport negotiation handshake."""
    
    class Hello:
        """Initial greeting sent by both sides."""
        aurc_version: str
        agent_id: str
        supported_transports: list[TransportCapability]
        preferred_transport: str | None
    
    class TransportCapability:
        transport: str           # "http2", "websocket", "stdio", "grpc"
        endpoint: str            # Connection endpoint
        features: list[str]      # "streaming", "compression", "encryption"
        max_message_size: int    # Maximum message size in bytes
    
    class NegotiationResult:
        selected_transport: str
        selected_endpoint: str
        features: list[str]
        keepalive_interval: timedelta
```

**Negotiation Algorithm**:
1. Both sides send `Hello` with supported transports
2. Find intersection of supported transports
3. If `preferred_transport` is in the intersection, use it
4. Otherwise, use priority order: HTTP/2 > WebSocket > stdio > gRPC
5. If no common transport, connection fails with `TransportNegotiationError`

### 9.3 Connection Management

```python
class ConnectionManager:
    """Manages transport connections with reconnection logic."""
    
    async def connect(self, agent_id: str, transport: str, 
                      endpoint: str) -> Connection: ...
    
    async def disconnect(self, connection_id: str) -> None: ...
    
    async def send(self, connection_id: str, message: Message) -> None: ...
    
    async def receive(self, connection_id: str) -> AsyncIterator[Message]: ...
    
    def get_connection_health(self, connection_id: str) -> ConnectionHealth: ...

class Connection:
    id: str
    agent_id: str
    transport: str
    endpoint: str
    state: Literal["connecting", "connected", "reconnecting", "disconnected"]
    created_at: datetime
    last_message_at: datetime
    messages_sent: int
    messages_received: int
    bytes_sent: int
    bytes_received: int
    
    # Reconnection policy
    reconnect_strategy: ReconnectStrategy

class ReconnectStrategy:
    max_retries: int = 10
    initial_delay: timedelta = timedelta(seconds=1)
    max_delay: timedelta = timedelta(minutes=5)
    backoff_multiplier: float = 2.0
    jitter: float = 0.1  # 10% random jitter
```

---

## 10. Layer 7: Security

### 10.1 Authentication

AURC supports multiple authentication methods, negotiated during connection:

```python
class AuthMethod(Enum):
    """Supported authentication methods."""
    
    OAUTH21_JWT   = "oauth21_jwt"     # OAuth 2.1 with JWT tokens
    MTLS          = "mtls"            # Mutual TLS
    API_KEY       = "api_key"         # Simple API key
    DID_AUTH      = "did_auth"        # DID-based authentication
    ANONYMOUS     = "anonymous"       # No authentication (local/dev only)

class AuthConfig:
    """Authentication configuration for an agent."""
    
    methods: list[AuthMethod]
    required_methods: list[AuthMethod]  # All must succeed (AND logic)
    
    # OAuth 2.1 config
    oauth21: OAuth21Config | None
    
    # mTLS config
    mtls: MTLSConfig | None
    
    # API Key config
    api_key: APIKeyConfig | None

class OAuth21Config:
    issuer: str              # Token issuer URL
    audience: str            # Expected audience
    jwks_uri: str            # JSON Web Key Set URI
    required_scopes: list[str]
    token_endpoint: str
    client_id: str
    client_secret: str | None  # For confidential clients
```

### 10.2 Authorization: Capability-Based Model

**Design Decision: Capability-Based Authorization (OCapN-inspired)**

We evaluated three authorization models:

| Model | Pros | Cons |
|-------|------|------|
| **RBAC** | Simple, well-understood | Coarse-grained, confused deputy problem |
| **ABAC** | Fine-grained, flexible | Complex policy language |
| **Capability-Based** | Unforgeable, composable, solves confused deputy | Less familiar to enterprise devs |

**Decision: Capability-Based with RBAC adapter for enterprise integration**

The capability-based model is chosen because:
1. **Solves MCP's confused deputy problem**: Capabilities are unforgeable tokens bound to specific agents
2. **Natural delegation**: Capabilities can be passed between agents with attenuation
3. **Composable**: Capabilities can be combined and intersected
4. **Auditable**: Every capability grant/revocation is logged

```python
class Capability2:
    """An unforgeable capability token."""
    
    id: str                    # Unique capability ID
    issuer: str                # AURC ID of the issuer
    holder: str                # AURC ID of the holder
    resource: str              # Resource this capability grants access to
    actions: list[str]         # Allowed actions (e.g., ["read", "write"])
    scope: dict[str, Any]      # Additional scope constraints
    issued_at: datetime
    expires_at: datetime
    delegatable: bool          # Can this capability be delegated?
    max_delegation_depth: int  # Maximum delegation chain length
    
    # Cryptographic proof
    signature: str             # Ed25519 signature by issuer
    parent_capability_id: str | None  # If delegated, the parent capability

class CapabilityStore:
    """Manages capabilities for an agent."""
    
    def grant(self, capability: Capability2) -> None:
        """Grant a capability to an agent."""
        ...
    
    def revoke(self, capability_id: str) -> None:
        """Revoke a capability. Propagates to all delegated capabilities."""
        ...
    
    def check(self, holder: str, resource: str, action: str) -> bool:
        """Check if an agent has a valid capability."""
        ...
    
    def delegate(
        self,
        capability_id: str,
        new_holder: str,
        attenuated_actions: list[str] | None = None,
        attenuated_scope: dict | None = None
    ) -> Capability2:
        """Delegate a capability to another agent with optional attenuation."""
        ...
    
    def list_capabilities(self, holder: str) -> list[Capability2]:
        """List all capabilities held by an agent."""
        ...
```

### 10.3 Solving the Confused Deputy Problem

**The Problem (in MCP context)**:
When Agent A calls Tool B via MCP, Tool B operates with its own permissions, not Agent A's. This means Tool B could be tricked into performing actions that Agent A shouldn't be allowed to do.

**AURC's Solution: Scoped Capability Delegation**

```
1. Agent A holds capability: "file.read on /data/*"
2. Agent A calls Tool B via MCP bridge
3. AURC creates a DELEGATED capability:
   - Holder: Tool B
   - Resource: /data/* (same as Agent A)
   - Actions: ["read"] (same or narrower)
   - Delegated by: Agent A
   - Expires: when the task completes
   - Parent: Agent A's capability

4. Tool B receives the delegated capability in the MCP call context
5. Tool B can ONLY access /data/* with read permission
6. Tool B CANNOT escalate to write or access /etc/*
7. When the task completes, the delegated capability expires
```

### 10.4 Delegation Chains

```python
class DelegationChain:
    """Tracks a chain of capability delegations."""
    
    root_capability: Capability2     # Original capability
    delegations: list[Delegation]    # Ordered list of delegations
    
    def validate(self) -> bool:
        """Validate the entire delegation chain."""
        current = self.root_capability
        for delegation in self.delegations:
            # Each delegation must be narrower than its parent
            if not delegation.capability.is_subset_of(current):
                return False
            # Delegation depth must not exceed max
            if delegation.depth > current.max_delegation_depth:
                return False
            # Parent must not be revoked
            if current.is_revoked:
                return False
            current = delegation.capability
        return True
    
    def get_effective_permissions(self) -> Capability2:
        """Get the effective (most attenuated) permissions."""
        return self.delegations[-1].capability if self.delegations else self.root_capability

class Delegation:
    from_agent: str
    to_agent: str
    capability: Capability2
    depth: int
    timestamp: datetime
    reason: str | None
```

### 10.5 Protocol-Level Permission Enforcement

Each bridge enforces permissions at the protocol boundary:

```python
class PermissionEnforcer:
    """Enforces permissions at protocol boundaries."""
    
    def enforce(
        self,
        message: AURCMessage,
        bridge: ProtocolBridge
    ) -> AURCMessage:
        """Enforce permissions on an outbound message.
        
        1. Extract required permissions from message
        2. Check if source agent has required capabilities
        3. Create delegated capabilities for the target
        4. Attach delegated capabilities to the message
        5. Log the enforcement decision
        """
        required_perms = self.extract_required_permissions(message)
        
        for perm in required_perms:
            if not self.capability_store.check(
                holder=message.source,
                resource=perm.resource,
                action=perm.action
            ):
                raise PermissionDenied(
                    f"Agent {message.source} lacks capability "
                    f"{perm.action} on {perm.resource}"
                )
        
        # Create delegated capabilities
        delegated = self.create_delegated_capabilities(
            source=message.source,
            target=message.destination,
            permissions=required_perms,
            bridge=bridge
        )
        
        # Attach to message context
        message.context.delegated_capabilities = delegated
        
        return message
```

---

## 11. Layer 8: Discovery

### 11.1 Discovery Methods

```python
class DiscoveryMethod(Enum):
    """Agent discovery methods."""
    
    REGISTRY    = "registry"      # Centralized registry service
    DNS_SD      = "dns_sd"        # DNS Service Discovery (local network)
    BROADCAST   = "broadcast"     # UDP broadcast (local network)
    CATALOG     = "catalog"       # Searchable capability catalog
    DIRECT      = "direct"        # Direct connection (known endpoint)
```

### 11.2 Registry Protocol

```python
class AgentRegistry:
    """Centralized agent registry."""
    
    async def register(self, descriptor: AgentDescriptor, 
                       lease_ttl: timedelta = timedelta(minutes=5)) -> str:
        """Register an agent. Returns registration ID.
        
        The agent must renew the lease before TTL expires.
        """
        ...
    
    async def deregister(self, agent_id: str) -> None:
        """Remove an agent from the registry."""
        ...
    
    async def renew_lease(self, agent_id: str) -> None:
        """Renew the registration lease."""
        ...
    
    async def resolve(self, agent_id: str) -> AgentDescriptor | None:
        """Resolve an AURC ID to an AgentDescriptor."""
        ...
    
    async def search(
        self,
        capabilities: list[str] | None = None,
        protocol: str | None = None,
        namespace: str | None = None,
        healthy_only: bool = True,
        limit: int = 10
    ) -> list[AgentDescriptor]:
        """Search for agents matching criteria."""
        ...
    
    async def subscribe(
        self,
        filter: SearchFilter,
        callback: Callable[[RegistryEvent], None]
    ) -> str:
        """Subscribe to registry changes matching a filter."""
        ...
```

### 11.3 Health-Based Routing

```python
class HealthRouter:
    """Routes requests based on agent health."""
    
    def select_agent(
        self,
        candidates: list[AgentDescriptor],
        strategy: RoutingStrategy = RoutingStrategy.LOWEST_LATENCY
    ) -> AgentDescriptor:
        """Select the best agent from candidates.
        
        Strategies:
        - LOWEST_LATENCY: Pick agent with lowest average response time
        - HIGHEST_AVAILABILITY: Pick agent with highest uptime
        - ROUND_ROBIN: Distribute evenly across healthy agents
        - WEIGHTED: Use agent-declared weights
        - RANDOM: Random selection (for load testing)
        """
        # Filter to healthy agents only
        healthy = [a for a in candidates if self.is_healthy(a)]
        
        if not healthy:
            raise NoHealthyAgentError("No healthy agents available")
        
        if strategy == RoutingStrategy.LOWEST_LATENCY:
            return min(healthy, key=lambda a: self.get_avg_latency(a))
        elif strategy == RoutingStrategy.HIGHEST_AVAILABILITY:
            return max(healthy, key=lambda a: self.get_uptime(a))
        elif strategy == RoutingStrategy.ROUND_ROBIN:
            return self._round_robin_next(healthy)
        # ... etc
    
    def report_health(
        self,
        agent_id: str,
        latency: timedelta,
        success: bool
    ) -> None:
        """Report health metrics for an agent."""
        ...
```

### 11.4 Capability-Based Matching

```python
class CapabilityMatcher:
    """Matches agent requests to agents with required capabilities."""
    
    def find_agents(
        self,
        required_capabilities: list[CapabilityRequirement],
        preferred_capabilities: list[CapabilityRequirement] | None = None,
        exclude_agents: list[str] | None = None
    ) -> list[MatchResult]:
        """Find agents matching capability requirements.
        
        Returns results sorted by match quality:
        1. All required + all preferred capabilities
        2. All required + some preferred capabilities
        3. All required capabilities only
        """
        ...

class CapabilityRequirement:
    name: str                    # e.g., "file.read"
    min_version: str | None      # Minimum required version
    parameters: dict | None      # Required parameter constraints
    required: bool = True        # Required vs preferred
```

---

## 12. Protocol Comparison

### 12.1 Feature Comparison Matrix

| Feature | MCP | A2A | ACP | ANP | **AURC** |
|---------|-----|-----|-----|-----|----------|
| **Agent Identity** | None | Agent Card | Agent ID | DID | AURC ID (DID-compatible) |
| **Agent-to-Tool** | Yes | No | No | No | Yes (via MCP bridge) |
| **Agent-to-Agent** | No | Yes | Yes | No | Yes (native + bridges) |
| **Lifecycle Management** | No | Partial (task states) | No | No | Yes (full state machine) |
| **Context/Memory** | Minimal | Task context | None | None | Yes (4 scopes + memory) |
| **Streaming** | Yes (SSE) | Yes | No | N/A | Yes (all transports) |
| **Error Recovery** | None | Retry only | None | N/A | Yes (6 strategies) |
| **Human-in-the-Loop** | No | Yes (input required) | No | No | Yes (full integration) |
| **Distributed Tracing** | No | No | No | No | Yes (W3C TC) |
| **Permission Model** | None | OAuth | API Key | DID Auth | Capability-based |
| **Delegation** | No | Limited | No | No | Yes (with attenuation) |
| **Discovery** | No | Agent Card URL | Registry | DID resolution | Yes (4 methods) |
| **Health Monitoring** | No | No | No | No | Yes (built-in) |
| **Cross-Protocol** | No | No | No | No | Yes (core feature) |
| **Transport** | stdio/HTTP | HTTP | HTTP | N/A | HTTP/WS/stdio/gRPC |

### 12.2 When to Use What

| Scenario | Recommended Protocol | AURC's Role |
|----------|---------------------|-------------|
| Single agent calling tools | MCP | AURC wraps MCP, adds lifecycle + tracing |
| Two agents collaborating | A2A or AURC native | AURC bridges A2A if needed |
| Simple REST agent API | ACP | AURC bridges ACP for richer features |
| Decentralized agent network | ANP | AURC uses ANP for identity resolution |
| Multi-protocol orchestration | **AURC** | AURC is the only option |
| Enterprise agent platform | **AURC** | AURC provides governance + security |

---

## 13. Use Case Scenarios

### 13.1 Scenario 1: Multi-Protocol Agent Orchestration

**Situation**: A financial analysis system has:
- An AURC orchestrator agent
- An MCP-based data retrieval tool
- An A2A-based risk analysis agent
- An ACP-based report generation service

**Flow**:
```
┌─────────────────────────────────────────────────────────────────┐
│  AURC Orchestrator                                               │
│  aurc:finance:orchestrator/main@1.0.0                           │
│                                                                  │
│  1. Receive user request: "Analyze portfolio risk"              │
│                                                                  │
│  2. Call MCP data tool:                                         │
│     AURC REQUEST → MCP Bridge → tools/call (MCP)                │
│     Retrieve portfolio data                                      │
│                                                                  │
│  3. Delegate to A2A risk agent:                                 │
│     AURC DELEGATION → A2A Bridge → Task (A2A)                   │
│     Risk agent analyzes portfolio                                │
│                                                                  │
│  4. Call ACP report service:                                    │
│     AURC REQUEST → ACP Bridge → POST /messages (ACP)            │
│     Generate PDF report                                          │
│                                                                  │
│  5. Compile results and respond to user                         │
│     All steps traced under single trace_id                      │
│     Permissions attenuated at each protocol boundary             │
└─────────────────────────────────────────────────────────────────┘
```

### 13.2 Scenario 2: Error Recovery with Fallback

**Situation**: Primary risk analysis agent (A2A) fails.

```
1. Orchestrator sends DELEGATION to A2A risk agent
2. A2A Bridge translates and sends A2A Task
3. A2A agent returns error: "service unavailable"
4. A2A Bridge translates to AURC ERROR message
5. Runtime Harness classifies error as DEPENDENCY
6. Recovery Policy: [RETRY_WITH_BACKOFF, FALLBACK, DEGRADE]
7. Attempt 1: RETRY_WITH_BACKOFF (2s delay) → still fails
8. Attempt 2: FALLBACK → switch to backup risk agent (MCP-based)
9. MCP Bridge translates DELEGATION to MCP tools/call
10. Backup agent succeeds, returns risk analysis
11. Orchestrator continues with backup result
12. Audit log records: primary failure, fallback used, latency impact
```

### 13.3 Scenario 3: Human-in-the-Loop Approval

**Situation**: Agent wants to execute a trade but needs human approval.

```
1. Trading agent (AURC) determines trade opportunity
2. Agent checks capabilities: "trade.execute" requires approval > $10,000
3. Trade amount: $50,000 → triggers human-in-the-loop
4. Runtime Harness:
   a. Creates HumanIntervention with trade details
   b. Transitions agent: RUNNING → PAUSED
   c. Sends notification to approval channel (Slack webhook)
5. Human receives notification:
   "Approve trade: Buy 100 shares AAPL @ $500 ($50,000)"
   Options: [Approve, Reject, Modify]
6. Human selects "Approve"
7. Runtime Harness:
   a. Records human decision in context
   b. Transitions agent: PAUSED → RUNNING
   c. Agent resumes with approval context
8. Agent executes trade via MCP bridge to trading platform
9. Audit log records: trade details, approver, timestamp
```

### 13.4 Scenario 4: Cross-Protocol Permission Attenuation

**Situation**: An AURC agent with broad permissions delegates to an MCP tool.

```
AURC Agent permissions:
  - file.read on /data/*
  - file.write on /data/*
  - code.execute
  - web.search
  - web.fetch

Delegation to MCP tool (data-processor):
  1. Permission Enforcer examines task: "process CSV file"
  2. Required permissions: file.read on /data/input.csv
  3. Creates delegated capability:
     - Holder: MCP tool
     - Resource: /data/input.csv (narrowed from /data/*)
     - Actions: ["read"] (narrowed from ["read", "write"])
     - Expires: when task completes
  4. MCP bridge sends tools/call with scoped capability
  5. MCP tool can ONLY read /data/input.csv
  6. MCP tool CANNOT write, execute code, or access web
  7. After task completion, delegated capability expires
```

---

## 14. SDK Design Principles

### 14.1 Core Philosophy

```python
# Principle 1: Zero-config for simple cases
from gaiaagent import Agent

agent = Agent(
    name="my-agent",
    capabilities=["file.read", "code.execute"]
)

@agent.tool("analyze")
async def analyze(data: dict) -> dict:
    return {"result": "analyzed"}

await agent.start()
```

```python
# Principle 2: Progressive complexity
from gaiaagent import Agent, Runtime, Bridge, Security

# Simple: just an agent
agent = Agent(name="simple")

# Intermediate: with runtime configuration
agent = Agent(
    name="configured",
    runtime=Runtime(
        max_concurrent_tasks=5,
        recovery_policy=RecoveryPolicy(max_retries=5)
    )
)

# Advanced: full control
agent = Agent(
    name="enterprise",
    runtime=Runtime(...),
    security=Security(
        auth=OAuth21Config(...),
        capabilities=CapabilityStore(...)
    ),
    bridges=[MCPBridge(), A2ABridge()],
    discovery=AgentRegistry(...)
)
```

### 14.2 SDK Module Structure

```
gaiaagent/
├── __init__.py              # Public API exports
├── core/
│   ├── __init__.py
│   ├── agent.py             # Agent class
│   ├── identity.py          # AURC ID, AgentDescriptor
│   ├── capability.py        # Capability declarations
│   ├── message.py           # Message types and serialization
│   └── context.py           # Context store and scopes
├── runtime/
│   ├── __init__.py
│   ├── harness.py           # Runtime harness
│   ├── state_machine.py     # Lifecycle state machine
│   ├── health.py            # Health monitoring
│   ├── memory.py            # Memory subsystem
│   ├── recovery.py          # Error recovery
│   └── resource.py          # Resource management
├── bus/
│   ├── __init__.py
│   ├── message_bus.py       # Message bus implementation
│   ├── router.py            # Message routing
│   ├── conversation.py      # Conversation management
│   └── serialization.py     # JSON/MessagePack serialization
├── bridges/
│   ├── __init__.py
│   ├── base.py              # ProtocolBridge ABC
│   ├── mcp.py               # MCP bridge
│   ├── a2a.py               # A2A bridge
│   ├── acp.py               # ACP bridge
│   └── registry.py          # Bridge registry
├── security/
│   ├── __init__.py
│   ├── auth.py              # Authentication
│   ├── capabilities.py      # Capability-based authorization
│   ├── delegation.py        # Delegation chains
│   └── enforcement.py       # Permission enforcement
├── discovery/
│   ├── __init__.py
│   ├── registry.py          # Agent registry
│   ├── dns_sd.py            # DNS-SD discovery
│   ├── catalog.py           # Capability catalog
│   └── health_router.py     # Health-based routing
├── tracing/
│   ├── __init__.py
│   ├── trace.py             # Distributed tracing
│   ├── audit.py             # Audit logging
│   └── correlation.py       # Context correlation
├── transport/
│   ├── __init__.py
│   ├── base.py              # Transport ABC
│   ├── http2.py             # HTTP/2 + SSE transport
│   ├── websocket.py         # WebSocket transport
│   ├── stdio.py             # stdio transport
│   ├── grpc.py              # gRPC transport (optional)
│   └── negotiation.py       # Transport negotiation
├── i18n/
│   ├── __init__.py
│   ├── messages_en.py       # English messages
│   └── messages_zh.py       # Chinese messages
└── testing/
    ├── __init__.py
    ├── mock_agent.py         # Mock agent for testing
    ├── mock_bridge.py        # Mock bridge for testing
    └── fixtures.py           # Test fixtures
```

### 14.3 SDK Design Principles

| # | Principle | Example |
|---|-----------|---------|
| 1 | **Decorator-based tool registration** | `@agent.tool("name")` |
| 2 | **Async-first** | All I/O operations are `async` |
| 3 | **Type-safe** | Full type hints with Pydantic models |
| 4 | **Progressive disclosure** | Simple API for simple cases, full control available |
| 5 | **Protocol-transparent** | Developers interact with AURC, not MCP/A2A/ACP |
| 6 | **Testable** | Built-in mock agents and bridges |
| 7 | **Observable** | OpenTelemetry integration out of the box |
| 8 | **Bilingual errors** | `error.message` and `error.message_zh` |

### 14.4 Example: Complete Agent

```python
import asyncio
from gaiaagent import Agent, Capability, ContextScope

# Define an agent with capabilities
agent = Agent(
    name="data-analyst",
    version="1.0.0",
    capabilities=[
        Capability(
            name="data.analyze",
            version="1.0.0",
            description="Analyze datasets and generate insights",
            parameters={"type": "object", "properties": {"dataset": {"type": "string"}}},
            returns={"type": "object", "properties": {"insights": {"type": "array"}}},
            idempotent=True,
            streaming=True,
        )
    ]
)

# Register a tool
@agent.tool("analyze_dataset", streaming=True)
async def analyze_dataset(ctx, dataset: str):
    """Analyze a dataset and stream insights."""
    
    # Store context
    await ctx.set("current_dataset", dataset, scope=ContextScope.SESSION)
    
    # Call an MCP tool (transparent bridging)
    data = await ctx.call_tool("data_loader", {"path": dataset})
    
    # Stream results
    for i, insight in enumerate(analyze(data)):
        yield {"insight": insight, "progress": (i + 1) / len(data)}

# Register error handler
@agent.on_error
async def handle_error(ctx, error):
    """Custom error handling."""
    await ctx.remember(f"Error occurred: {error}", importance=0.8)
    return "retry_with_backoff"

# Start the agent
async def main():
    await agent.start(
        transport="http2",
        endpoint="http://localhost:8080",
        discovery=True  # Auto-register with local registry
    )

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 15. Governance Model

### 15.1 License Choice

| License | Pros | Cons |
|---------|------|------|
| **Apache 2.0** | Permissive, enterprise-friendly, patent protection | No copyleft |
| MIT | Simple, permissive | No patent protection |
| GPL 3.0 | Strong copyleft | Viral, enterprise-unfriendly |
| AGPL 3.0 | Closes SaaS loophole | Very restrictive for cloud providers |
| **Apache 2.0 + CLA** | Permissive + contribution protection | CLA overhead |

**Decision: Apache 2.0 License**

Rationale:
1. **Enterprise adoption**: Apache 2.0 is the standard for enterprise open-source (Kubernetes, TensorFlow, etc.)
2. **Protocol adoption**: A protocol needs maximum adoption; restrictive licenses hinder this
3. **Patent protection**: Apache 2.0 includes patent grant, important for protocol implementations
4. **Compatibility**: Compatible with GPL, MIT, BSD — can be used in any project

### 15.2 Governance Structure

```
┌─────────────────────────────────────────────────────────┐
│                  AURC Governance                         │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Technical Steering Committee (TSC)              │   │
│  │  - 5-7 members                                   │   │
│  │  - Sets technical direction                      │   │
│  │  - Approves RFCs                                 │   │
│  │  - Resolves disputes                             │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Working Groups                                   │   │
│  │  - Protocol Spec WG (core specification)          │   │
│  │  - SDK WG (reference implementation)              │   │
│  │  - Bridge WG (protocol bridges)                   │   │
│  │  - Security WG (security model)                   │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Community                                        │   │
│  │  - Open issues and discussions                    │   │
│  │  - RFC proposals welcome from anyone              │   │
│  │  - Consensus-driven decisions                     │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 15.3 RFC Process

1. **Draft**: Anyone can submit an RFC (Request for Comments)
2. **Discussion**: 2-week public comment period
3. **Revision**: Author addresses feedback
4. **Review**: TSC reviews final draft
5. **Approval**: TSC vote (majority required)
6. **Implementation**: Reference implementation in GaiaAgent
7. **Standardization**: After 2+ implementations, becomes part of spec

### 15.4 Versioning

- **Protocol version**: Semantic versioning (major.minor.patch)
- **Backward compatibility**: Minor versions MUST be backward-compatible
- **Breaking changes**: Require major version bump + migration guide
- **Deprecation**: 6-month deprecation period before removal

---

## 16. Appendix: JSON Schemas

### 16.1 AURC Message Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://aurc.dev/schemas/message/v0.1.0.json",
  "title": "AURC Message",
  "description": "Canonical AURC protocol message",
  "type": "object",
  "required": [
    "aurc_version",
    "message_id",
    "timestamp",
    "source",
    "message_type",
    "payload"
  ],
  "properties": {
    "aurc_version": {
      "type": "string",
      "pattern": "^\\d+\\.\\d+\\.\\d+$",
      "description": "AURC protocol version"
    },
    "message_id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique message identifier (UUID v7 for time-ordering)"
    },
    "correlation_id": {
      "type": ["string", "null"],
      "format": "uuid",
      "description": "Correlates request/response pairs"
    },
    "causation_id": {
      "type": ["string", "null"],
      "format": "uuid",
      "description": "The message that caused this message"
    },
    "timestamp": {
      "type": "string",
      "format": "date-time",
      "description": "ISO 8601 timestamp"
    },
    "source": {
      "type": "string",
      "pattern": "^aurc:",
      "description": "Source agent AURC ID"
    },
    "destination": {
      "type": ["string", "null"],
      "pattern": "^aurc:",
      "description": "Destination agent AURC ID (null for broadcast)"
    },
    "reply_to": {
      "type": ["string", "null"],
      "description": "Reply-to endpoint or agent ID"
    },
    "message_type": {
      "type": "string",
      "enum": [
        "request",
        "response",
        "notification",
        "stream_start",
        "stream_chunk",
        "stream_end",
        "delegation",
        "heartbeat",
        "error"
      ]
    },
    "content_type": {
      "type": "string",
      "default": "application/json",
      "description": "Payload content type"
    },
    "context": {
      "type": "object",
      "properties": {
        "trace_id": { "type": "string" },
        "span_id": { "type": "string" },
        "parent_span_id": { "type": ["string", "null"] },
        "session_id": { "type": "string" },
        "conversation_id": { "type": ["string", "null"] },
        "permissions": {
          "type": "object",
          "properties": {
            "capabilities": {
              "type": "array",
              "items": { "type": "string" }
            },
            "scope": { "type": "string" },
            "expires_at": { "type": "string", "format": "date-time" }
          }
        },
        "delegated_capabilities": {
          "type": "array",
          "items": { "$ref": "#/$defs/capability" }
        }
      }
    },
    "payload": {
      "type": "object",
      "description": "Message payload (method-specific)"
    },
    "metadata": {
      "type": "object",
      "properties": {
        "priority": {
          "type": "string",
          "enum": ["low", "normal", "high", "critical"],
          "default": "normal"
        },
        "ttl_seconds": {
          "type": "integer",
          "minimum": 0
        },
        "idempotency_key": { "type": "string" },
        "language": {
          "type": "string",
          "enum": ["en", "zh"],
          "default": "en"
        }
      }
    }
  },
  "$defs": {
    "capability": {
      "type": "object",
      "required": ["id", "issuer", "holder", "resource", "actions"],
      "properties": {
        "id": { "type": "string" },
        "issuer": { "type": "string" },
        "holder": { "type": "string" },
        "resource": { "type": "string" },
        "actions": {
          "type": "array",
          "items": { "type": "string" }
        },
        "scope": { "type": "object" },
        "issued_at": { "type": "string", "format": "date-time" },
        "expires_at": { "type": "string", "format": "date-time" },
        "delegatable": { "type": "boolean" },
        "max_delegation_depth": { "type": "integer" },
        "signature": { "type": "string" },
        "parent_capability_id": { "type": ["string", "null"] }
      }
    }
  }
}
```

### 16.2 Agent Descriptor Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://aurc.dev/schemas/agent-descriptor/v0.1.0.json",
  "title": "AURC Agent Descriptor",
  "type": "object",
  "required": ["id", "display_name", "protocol", "capabilities", "transports"],
  "properties": {
    "id": {
      "type": "string",
      "pattern": "^aurc:",
      "description": "AURC ID"
    },
    "display_name": {
      "type": "string",
      "maxLength": 256
    },
    "display_name_zh": {
      "type": ["string", "null"],
      "maxLength": 256
    },
    "description": {
      "type": "string",
      "maxLength": 4096
    },
    "description_zh": {
      "type": ["string", "null"],
      "maxLength": 4096
    },
    "protocol": {
      "type": "string",
      "enum": ["mcp", "a2a", "acp", "aurc"]
    },
    "capabilities": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["name", "version"],
        "properties": {
          "name": { "type": "string" },
          "version": { "type": "string" },
          "description": { "type": "string" },
          "parameters": { "type": "object" },
          "returns": { "type": "object" },
          "idempotent": { "type": "boolean" },
          "streaming": { "type": "boolean" },
          "rate_limit": { "type": ["integer", "null"] }
        }
      }
    },
    "transports": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["transport", "endpoint"],
        "properties": {
          "transport": {
            "type": "string",
            "enum": ["http2", "websocket", "stdio", "grpc"]
          },
          "endpoint": { "type": "string" },
          "features": {
            "type": "array",
            "items": { "type": "string" }
          }
        }
      }
    },
    "auth_methods": {
      "type": "array",
      "items": {
        "type": "string",
        "enum": ["oauth21_jwt", "mtls", "api_key", "did_auth", "anonymous"]
      }
    },
    "health_endpoint": {
      "type": ["string", "null"]
    },
    "did_document": {
      "type": ["object", "null"]
    },
    "metadata": {
      "type": "object"
    }
  }
}
```

### 16.3 State Transition Event Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://aurc.dev/schemas/state-event/v0.1.0.json",
  "title": "AURC State Transition Event",
  "type": "object",
  "required": ["agent_id", "from_state", "to_state", "event", "timestamp"],
  "properties": {
    "agent_id": {
      "type": "string",
      "pattern": "^aurc:"
    },
    "from_state": {
      "type": "string",
      "enum": ["created", "initializing", "idle", "running", "paused", "stopping", "stopped", "error", "recovering"]
    },
    "to_state": {
      "type": "string",
      "enum": ["created", "initializing", "idle", "running", "paused", "stopping", "stopped", "error", "recovering"]
    },
    "event": {
      "type": "string"
    },
    "timestamp": {
      "type": "string",
      "format": "date-time"
    },
    "trigger": {
      "type": "object",
      "properties": {
        "type": {
          "type": "string",
          "enum": ["api_call", "internal", "timer", "error", "human", "dependency"]
        },
        "source": { "type": "string" },
        "details": { "type": "object" }
      }
    },
    "context_snapshot": {
      "type": "object",
      "description": "Snapshot of agent context at time of transition"
    }
  }
}
```

---

## 17. Error Codes

### 17.1 Standard Error Codes

| Code | Name | Description (EN) | 描述 (ZH) |
|------|------|-----------------|----------|
| 1001 | INVALID_MESSAGE | Malformed AURC message | 消息格式错误 |
| 1002 | INVALID_ID | Invalid AURC ID format | AURC ID格式无效 |
| 1003 | UNKNOWN_AGENT | Agent not found in registry | 注册表中未找到代理 |
| 2001 | STATE_TRANSITION_ERROR | Invalid state transition | 无效的状态转换 |
| 2002 | RESOURCE_LIMIT_EXCEEDED | Resource limit exceeded | 超出资源限制 |
| 2003 | CONTEXT_OVERFLOW | Context size exceeds limit | 上下文大小超出限制 |
| 3001 | BRIDGE_ERROR | Protocol bridge translation failed | 协议桥转换失败 |
| 3002 | BRIDGE_NOT_FOUND | No bridge for target protocol | 未找到目标协议的桥接 |
| 3003 | PROTOCOL_MISMATCH | Incompatible protocol versions | 协议版本不兼容 |
| 4001 | PERMISSION_DENIED | Insufficient capabilities | 权限不足 |
| 4002 | CAPABILITY_EXPIRED | Capability token has expired | 能力令牌已过期 |
| 4003 | CAPABILITY_REVOKED | Capability has been revoked | 能力已被撤销 |
| 4004 | DELEGATION_TOO_DEEP | Delegation chain exceeds max depth | 委托链超出最大深度 |
| 5001 | TRANSPORT_ERROR | Transport-level failure | 传输层故障 |
| 5002 | CONNECTION_TIMEOUT | Connection establishment timed out | 连接建立超时 |
| 5003 | TRANSPORT_NEGOTIATION_FAILED | No common transport | 无共同支持的传输协议 |
| 6001 | RECOVERY_EXHAUSTED | All recovery strategies failed | 所有恢复策略均已失败 |
| 6002 | HUMAN_INTERVENTION_TIMEOUT | Human response timeout | 人工干预超时 |
| 7001 | REGISTRY_UNAVAILABLE | Registry service unreachable | 注册服务不可达 |
| 7002 | REGISTRATION_EXPIRED | Agent registration lease expired | 代理注册租约已过期 |

### 17.2 Error Message Format

```json
{
  "aurc_version": "0.1.0",
  "message_id": "err-001",
  "message_type": "error",
  "timestamp": "2026-06-24T10:30:00.000Z",
  "source": "aurc:system:runtime@0.1.0",
  "payload": {
    "error": {
      "code": 4001,
      "name": "PERMISSION_DENIED",
      "message": "Agent lacks capability 'file.write' on '/data/protected'",
      "message_zh": "代理缺少对'/data/protected'的'file.write'权限",
      "details": {
        "required_capability": "file.write",
        "resource": "/data/protected",
        "held_capabilities": ["file.read", "web.search"]
      },
      "retryable": false,
      "trace_id": "abc123"
    }
  }
}
```

---

## 18. Security Considerations

### 18.1 Threat Model

| Threat | Mitigation |
|--------|-----------|
| **Identity Spoofing** | AURC IDs are cryptographically signed; DID verification optional |
| **Message Tampering** | Message integrity via HMAC or digital signatures |
| **Replay Attacks** | Nonce + timestamp validation; idempotency keys |
| **Privilege Escalation** | Capability attenuation at every protocol boundary |
| **Confused Deputy** | Scoped capability delegation (see Section 10.3) |
| **Denial of Service** | Rate limiting, resource quotas, circuit breakers |
| **Data Exfiltration** | Permission scoping limits data access per agent |
| **Man-in-the-Middle** | mTLS or OAuth 2.1 with token binding |
| **Delegation Chain Abuse** | Max delegation depth + chain validation |

### 18.2 Security Recommendations

1. **Always use encryption in production**: HTTP/2 with TLS 1.3 minimum
2. **Prefer capability-based auth over API keys**: API keys are bearer tokens with no scoping
3. **Set conservative resource limits**: Default limits should be restrictive
4. **Enable audit logging**: All permission changes and delegation events must be logged
5. **Rotate capability tokens**: Set reasonable expiration times
6. **Validate delegation chains**: Every hop must be validated for depth and scope

---

## 19. 中文摘要 / Chinese Summary

### AURC协议概述

AURC（Agent Unified Runtime & Communication Protocol，代理统一运行时与通信协议）是一个元协议层，旨在桥接2026年AI代理生态中碎片化的协议标准（MCP、A2A、ACP、ANP）。

**核心创新**：
1. **统一桥接**：不替代现有协议，而是在它们之上提供统一的翻译和路由层
2. **运行时引擎**：首个提供标准化代理生命周期管理（启动/暂停/恢复/停止/错误恢复）的协议
3. **能力安全**：基于能力的授权模型，解决了MCP的混淆代理问题
4. **上下文关联**：跨协议的分布式追踪和权限传播

**八层架构**：
- 第1层：代理身份（DID兼容的AURC ID格式）
- 第2层：运行时引擎（9状态生命周期状态机）
- 第3层：统一消息总线（JSON规范格式 + MessagePack可选）
- 第4层：协议桥接（MCP/A2A/ACP适配器）
- 第5层：上下文关联（W3C追踪上下文 + 权限衰减）
- 第6层：传输层（HTTP/2、WebSocket、stdio、gRPC）
- 第7层：安全层（OAuth 2.1 + 基于能力的授权）
- 第8层：发现层（注册表 + DNS-SD + 能力目录）

**设计原则**：
- 协议无关：桥接而非替代
- 开发者优先：简单核心API，企业功能作为可选模块
- 渐进式复杂度：从零配置到完全控制
- 默认可观测：内置分布式追踪、健康检查和审计日志

**开源治理**：Apache 2.0许可证，RFC驱动的规范演进，技术指导委员会（TSC）管理。

---

## 20. References

### 20.1 Normative References

- [RFC 2119] Key words for use in RFCs (Bradner, 1997)
- [RFC 8141] Uniform Resource Names (URNs) (Saint-Andre & Klensin, 2017)
- [W3C DID] Decentralized Identifiers (DIDs) v1.0 (W3C, 2022)
- [W3C Trace Context] Trace Context (W3C, 2021)
- [OAuth 2.1] The OAuth 2.1 Authorization Framework (IETF, 2024)
- [JSON Schema] JSON Schema: A Media Type for Describing JSON Documents (IETF, 2024)
- [UUID v7] New UUID Formats (IETF, 2024)

### 20.2 Informative References

- [MCP] Model Context Protocol Specification (Anthropic, 2024-2026)
- [A2A] Agent-to-Agent Protocol Specification (Google, 2025-2026)
- [ACP] Agent Communication Protocol (IBM, 2025)
- [ANP] Agent Network Protocol (Community, 2025-2026)
- [OCapN] Object-Capability Network (Miller, 2006)

---

*End of AURC Protocol Specification v0.1.0-draft*

*Copyright 2026 GaiaAgent Contributors. Licensed under Apache License 2.0.*
