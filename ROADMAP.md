# GaiaAgent Roadmap / 路线图

> **[← Back to README](README.md)** | [Protocol Spec](PROTOCOL.md) | [Contributing](CONTRIBUTING.md)
>
> The living, public plan for GaiaAgent and the AURC protocol.
> GaiaAgent 与 AURC 协议的公开、持续演进计划。

---

## North Star / 北极星

> **Make AURC the shared substrate beneath every AI agent protocol — the way TCP/IP became the substrate beneath a hundred application protocols.**

A protocol becomes a standard when **two independent implementations** agree. GaiaAgent is the *reference* implementation; the roadmap is the path from "one implementation, alpha" to "spec frozen, multi-language, production-hardened, multi-vendor."

目标：让 AURC 成为所有 AI Agent 协议之下的共享基底——如同 TCP/IP 之于一百种应用协议。GaiaAgent 是参考实现，本路线图是从"单一实现、alpha"走向"规范冻结、多语言、生产级、多厂商"的路径。

---

## Status Legend / 状态图例

| Mark | Meaning / 含义 |
|:---:|---|
| ✅ | Shipped in `v0.1.0` (alpha — works end-to-end, APIs may still move) / 已发布（alpha，端到端可用，API 仍可能变动） |
| 🚧 | In progress / 进行中 |
| 🔜 | Planned, not started / 已规划，未开始 |
| 💡 | RFC open or wanted / RFC 讨论中或征集实现 |
| ❌ | Explicitly out of scope (see [Non-Goals](#non-goals--非目标)) / 明确不做 |

---

## Version Milestones / 版本里程碑

| Version | Theme / 主题 | Unlocks / 解锁能力 | Status |
|:---:|---|---|:---:|
| **v0.1** | Single-process reference impl / 单进程参考实现 | 3 bridges · 9-state lifecycle · CapABAC · 5 workflow patterns · CLI · Claude | ✅ Alpha |
| **v0.2** | Production-ready single-tenant / 单租户生产可用 | gRPC transport · distributed registry · OpenTelemetry · persistent audit | 🚧 Next |
| **v0.3** | Multi-tenant & federation / 多租户与联邦 | Federated discovery · tenant isolation · rate-limit policies · backpressure | 🔜 |
| **v0.4** | Polyglot SDKs / 多语言 SDK | TypeScript · Go · Rust client SDKs · spec conformance test suite | 🔜 |
| **v1.0** | Standard-grade / 标准级 | Second independent implementation · spec frozen · backward-compat guarantee · security audit | 🔜 |

> Version dates are deliberately not pinned — we ship when acceptance criteria are met, not when a calendar says so. Track live progress in [Discussions](https://github.com/gaiaagent/gaiaagent/discussions) and [Issues](https://github.com/gaiaagent/gaiaagent/issues).
>
> 版本日期有意不固定——达到验收标准才发布，而非按日历。进展见 Discussions 与 Issues。

---

## Workstreams / 工作流赛道

Work is organized into six tracks that move in parallel. Each item lists **what**, **why**, and **acceptance criteria**.

工作分为六个并行赛道。每项列出**做什么**、**为什么**、**验收标准**。

### 🧠 Track 1 — Runtime & Lifecycle / 运行时与生命周期

| Item | Status | Why |
|:---|:---:|---|
| 9-state lifecycle state machine / 9 态状态机 | ✅ | No protocol standardized agent lifecycle before AURC |
| Policy-based error recovery (5 strategies) / 错误恢复策略 | ✅ | Agents must self-heal, not just crash |
| 4-scope context store (session/agent/shared/global) / 多作用域上下文 | ✅ | Memory isolation across tasks and agents |
| Pause/resume via `asyncio.Event` / 暂停恢复 | ✅ | HITL gates and resource waits |
| **Durable lifecycle** (survive harness restart) / 持久化生命周期 | 🔜 | Long-running agents that outlive a process |
| **Checkpoint & rewind** / 检查点与回溯 | 💡 | Debug and replay multi-agent runs |
| **Resource quotas & backpressure** / 资源配额与背压 | 🔜 | Multi-tenant safety |

### 🌉 Track 2 — Interoperability / 互操作（桥接）

| Item | Status | Why |
|:---|:---:|---|
| MCP Bridge (JSON-RPC ↔ AURC) / MCP 桥接 | ✅ | Tools are the most-adopted layer |
| A2A Bridge (tasks/send ↔ AURC) / A2A 桥接 | ✅ | Agent-to-agent delegation |
| ACP Bridge (HTTP envelope ↔ AURC) / ACP 桥接 | ✅ | Lightweight REST messaging |
| Bidirectional context preservation (`correlation_id`, `bridge_chain`) / 跨协议上下文保留 | ✅ | Traceability across hops |
| **gRPC Bridge** | 🔜 | High-performance internal meshes |
| **GraphQL Bridge** | 💡 | Schema-first ecosystems |
| **NATS / Kafka / AMQP bridges** | 💡 | Event-driven agent backbones |
| **Bridge conformance test suite** / 桥接一致性测试集 | 🔜 | Third-party bridges must be provably correct |

### 🔒 Track 3 — Security & Governance / 安全与治理

| Item | Status | Why |
|:---|:---:|---|
| API Key + JWT + mTLS-ready auth / 多种认证 | ✅ | Dev to production flexibility |
| CapABAC authorization engine / CapABAC 授权 | ✅ | Fine-grained, constraint-based access |
| Delegation chain validation (scopes only narrow) / 委托链验证 | ✅ | Solves MCP's confused deputy |
| Append-only audit log / 只追加审计日志 | ✅ | Compliance and forensics |
| **Pluggable audit sinks** (S3, SIEM, opaque token) / 可插拔审计落地 | 🔜 | Enterprise compliance pipelines |
| **Per-tenant authz & rate limits** / 租户级授权与限流 | 🔜 | Multi-tenant isolation |
| **Signed delegation chains** (cryptographic) / 签名委托链 | 💡 | Non-repudiation across orgs |
| **Third-party security audit** / 第三方安全审计 | 🔜 | Trust before v1.0 |

### 📊 Track 4 — Observability & Operations / 可观测与运维

| Item | Status | Why |
|:---:|---:|---|
| Health dashboard (HTML + JSON) / 健康面板 | ✅ | Operator visibility |
| Router statistics & dead-letter queue / 路由统计与死信队列 | ✅ | Debug undeliverable messages |
| State-change listeners / 状态变化监听 | ✅ | Alerting and metrics export |
| HTTP/2 + WebSocket transports / HTTP 与 WebSocket 传输 | ✅ | Prod + real-time |
| **Prometheus metrics exporter** (`/metrics`) / Prometheus 指标导出 | ✅ | Scrape AURC with any Prometheus-compatible scraper |
| **Structured `bridge_chain` tracing** / 桥接链结构化追踪 | ✅ | Reconstruct a request's cross-protocol path by `correlation_id` |
| **OpenTelemetry tracing** / OpenTelemetry 追踪 | 🔜 | Ship spans to a distributed backend (trace recorder is the in-process base) |
| **gRPC transport** / gRPC 传输 | 🔜 | High-throughput internal deploys |

### 🌐 Track 5 — Ecosystem & SDKs / 生态与 SDK

| Item | Status | Why |
|:---:|---:|---|
| `@aurc_agent` / `@skill` Python decorators / Python 装饰器 | ✅ | 30-second agent definition |
| Claude integration (agentic loop, tool use) / Claude 集成 | ✅ | Reference LLM backend |
| `aurc` CLI (serve/validate/bridge test/registry export) / CLI | ✅ | DevX without writing code |
| End-to-end demo + multi-agent example / 端到端示例 | ✅ | Copy-paste starting points |
| **Pluggable LLM backends** (beyond Claude) / 可插拔 LLM 后端 | 🔜 | No vendor lock-in |
| **TypeScript SDK** | 🔜 | Node/Browser agent ecosystem |
| **Go SDK** | 🔜 | Infrastructure-side agents |
| **Rust SDK** | 🔜 | Embedded / edge agents |
| **Bridge & plugin registry** / 桥接与插件市场 | 💡 | Discoverable community extensions |

### 📜 Track 6 — Standardization / 标准化

| Item | Status | Why |
|:---:|---:|---|
| AURC v0.1 spec (PROTOCOL.md, CC BY-SA 4.0) / 规范 v0.1 | ✅ | Frozen reference for implementers |
| AURC-RFC process / RFC 流程 | ✅ | Governed protocol evolution |
| **Conformance test suite** / 一致性测试集 | 🔜 | "AURC-compatible" must mean something |
| **Second independent implementation** / 第二个独立实现 | 🔜 | The bar to call AURC a true standard |
| **W3C-style trace-context interop** / 跟踪上下文互操作 | 💡 | Align with broader tracing standards |
| **Spec v1.0 freeze + compat guarantee** / 规范 v1.0 冻结 | 🔜 | Stability for production adopters |

---

## Recently Shipped / 近期已完成 (v0.1.0 alpha)

A credibility-oriented snapshot of what already runs end-to-end today (`python main.py` exercises all of it):

- ✅ 8-layer stack: L0 Transport → L7 Discovery, each layer independently testable
- ✅ `AURCId` URN identity + `AgentDescriptor` identity document
- ✅ 9-state lifecycle engine with 5-strategy error recovery
- ✅ Unified Message Bus: `MessageRouter` (direct/bridge/broadcast/dead-letter), `SessionManager`, JSON/NDJSON codecs
- ✅ Bidirectional bridges for **MCP, A2A, ACP** with capability mapping
- ✅ HTTP/2 + WebSocket transports
- ✅ CapABAC: API Key/JWT auth, authorization engine, delegation-chain validation, append-only audit log
- ✅ `LocalRegistry` with capability/tag/protocol matching
- ✅ 5 orchestration patterns + `DynamicWorkflowEngine`
- ✅ Claude integration: `ClaudeLLM`, agentic loop, tool use, `ClaudeAgent` base
- ✅ `aurc` CLI + health dashboard
- ✅ Prometheus metrics exporter (`/metrics`) + structured `bridge_chain` tracing

---

## Non-Goals / 非目标

Stating what we will *not* build is as important as what we will. These are deliberate:

明确"不做什么"与"做什么"同等重要。以下为刻意排除项：

| Non-Goal | Reason / 理由 |
|:---|:---|
| ❌ **A competing agent protocol** / 又一个竞争协议 | AURC *bridges* MCP/A2A/ACP, it does not replace them. "Bridge First, Don't Replace." |
| ❌ **An LLM provider / model training** / 自研大模型 | Claude is one pluggable backend. GaiaAgent is protocol-agnostic about the model. |
| ❌ **A closed/SaaS-only runtime** / 闭源 SaaS 运行时 | Reference impl is AGPL-3.0; the spec is CC BY-SA 4.0. Open by construction. |
| ❌ **Lock-in to one language** / 绑定单一语言 | Python is the reference; TS/Go/Rust SDKs are on the roadmap precisely to avoid this. |
| ❌ **Blockchain/DID identity dependency** / 区块链/DID 依赖 | AURC IDs are simple URNs — no ledger, no key-recovery ceremony required to start. |
| ❌ **Breaking changes after v1.0** / v1.0 后破坏性变更 | Post-1.0, backward compatibility is a hard contract, governed by RFC. |

---

## How to Influence / 如何参与推动

- **Pick a `💡` or `🔜` item** — these are the open frontier. Comment in [Discussions](https://github.com/gaiaagent/gaiaagent/discussions) to claim it.
- **Propose a new bridge** (gRPC, GraphQL, NATS, Kafka…) — see the [Bridge Developer Guide](docs/architecture/bridge-guide.md).
- **Change the protocol** — anything normative goes through the [AURC-RFC process](CONTRIBUTING.md#protocol-changes-aurc-rfc).
- **Build the second implementation** — the single highest-leverage contribution toward AURC becoming a standard.

### Good First Issues / 适合入手

- A `map_capabilities` round-trip test for the ACP bridge
- A `SlackBridge` reference implementation (see [Bridges Guide](docs/guides/bridges.md))
- An OpenTelemetry exporter layered on `BridgeTraceRecorder` (Track 4)
- A TypeScript client for the AURC HTTP transport

---

*This roadmap is a living document. Edits are welcome via PR — label it `roadmap` so we can discuss scope before committing.*
