# AURC Architecture Overview / 架构概览

> **[← Back to README](../../README.md)** | [Protocol Spec](../../PROTOCOL.md) | [Deep Dive](../architecture.md) | [API Reference](../api-reference.md)
>
> Developer-friendly summary of the AURC protocol architecture.
> For the full specification, see [PROTOCOL.md](../../PROTOCOL.md).

## System Map / 系统全景

```
                    ┌──────────────────────────────────┐
                    │       Your Application            │
                    │                                   │
                    │  @aurc_agent   @skill             │
                    │  (declarative agent definition)   │
                    └────────────┬─────────────────────┘
                                 │
              ┌──────────────────▼──────────────────────┐
              │          AURC Runtime Harness            │
              │                                         │
              │  ┌─────────┐  ┌───────┐  ┌──────────┐  │
              │  │Lifecycle│  │Health │  │ Context  │  │
              │  │  State  │  │Monitor│  │  Memory  │  │
              │  │ Machine │  │       │  │          │  │
              │  └─────────┘  └───────┘  └──────────┘  │
              │                                         │
              │  ┌─────────────────────────────────┐    │
              │  │      Unified Message Bus         │    │
              │  │  Router + Session + Codec        │    │
              │  └──────────────┬──────────────────┘    │
              │                 │                        │
              │  ┌──────────────▼──────────────────┐    │
              │  │       Protocol Bridges           │    │
              │  │  ┌─────┐ ┌─────┐ ┌─────┐       │    │
              │  │  │ MCP │ │ A2A │ │Custom│      │    │
              │  │  └─────┘ └─────┘ └─────┘       │    │
              │  └─────────────────────────────────┘    │
              │                                         │
              │  ┌─────────────────────────────────┐    │
              │  │        Security Layer            │    │
              │  │  Auth + CapABAC + Delegation    │    │
              │  │  + Audit Log                     │    │
              │  └─────────────────────────────────┘    │
              │                                         │
              │  ┌─────────────────────────────────┐    │
              │  │    Workflow Orchestration         │    │
              │  │  Chain | Route | Parallel |       │    │
              │  │  Orch-Workers | Eval-Optimize     │    │
              │  └─────────────────────────────────┘    │
              │                                         │
              │  ┌─────────────────────────────────┐    │
              │  │    Claude Integration             │    │
              │  │  ClaudeLLM + Agentic Loop         │    │
              │  └─────────────────────────────────┘    │
              └─────────────────────────────────────────┘
```

## Module Dependency Graph / 模块依赖图

```
sdk/decorators ──→ core/identity
                      ↓
core/types ←── core/message ←── core/capability
    ↓                ↓
harness/lifecycle ←── bus/router ←── bus/session
    ↓                ↓
harness/context   bus/codec
    ↓                ↓
security/* ───── bridges/base
    ↓                ↓
security/audit    bridges/a2a
                     ↓
integrations/claude ←→ workflows/orchestrator
                     ↓
transport/http   registry/local
```

## Data Flow Examples / 数据流示例

### Intra-Harness Message (同 Harness 内消息)

```
Agent A ──→ MessageRouter ──→ Agent B
              (direct)
```

### Cross-Protocol Message (跨协议消息)

```
Agent A ──→ MessageRouter ──→ MCPBridge ──→ External MCP Server
              (bridge)        (translate)
```

### Multi-Agent Workflow (多 Agent 工作流)

```
User ──→ Orchestrator ──→ ClaudeLLM (decompose)
                │
                ├──→ Worker A (via Router, direct)
                ├──→ Worker B (via MCPBridge)
                └──→ Worker C (via A2ABridge)
                │
                └──→ Synthesizer ──→ User
```

## Key Design Decisions / 关键设计决策

| Decision | Choice | Rationale |
|----------|--------|-----------|
| ID Format | URN (`aurc:ns/name:ver`) | Simple, no blockchain dependency |
| Message Format | JSON | Human-readable, broad ecosystem |
| Bridge Pattern | Structural typing (`Protocol`) | No inheritance coupling |
| State Machine | Explicit transitions | Prevents invalid states at runtime |
| Security | CapABAC (hybrid) | Combines capability + attribute models |
| Context Scopes | 4-tier (session/agent/shared/global) | Matches common isolation needs |
| Error Recovery | Policy-based strategies | Configurable per-agent |
| Auth | Multi-method (API Key + JWT) | Flexible for dev and production |

## Extension Points / 扩展点

1. **Custom Bridges**: Implement `ProtocolBridge` for proprietary protocols
2. **Custom Recovery Strategies**: Add to `RecoveryPolicy.strategies`
3. **Custom Transports**: Implement HTTP, WebSocket, gRPC, or stdio
4. **Custom Workflow Patterns**: Compose the 5 built-in patterns
5. **Custom LLM Providers**: Replace `ClaudeLLM` with any LLM backend
