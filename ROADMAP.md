# GaiaAgent Roadmap

> 🌐 [中文版](ROADMAP.zh.md)
> **[← Back to README](README.md)** | [Protocol Spec](PROTOCOL.md) | [Contributing](CONTRIBUTING.md)
>
> The living, public plan for GaiaAgent and the AURC protocol.

---

## North Star

> **Make AURC the shared substrate beneath every AI agent protocol — the way TCP/IP became the substrate beneath a hundred application protocols.**

A protocol becomes a standard when **two independent implementations** agree. GaiaAgent is the *reference* implementation; the roadmap is the path from "one implementation, alpha" to "spec frozen, multi-language, production-hardened, multi-vendor."

---

## Status Legend

| Mark | Meaning |
|:---:|---|
| ✅ | Shipped in `v0.1.0` (alpha — works end-to-end, APIs may still move) |
| 🚧 | In progress |
| 🔜 | Planned, not started |
| 💡 | RFC open or wanted |
| ❌ | Explicitly out of scope (see [Non-Goals](#non-goals)) |

---

## Version Milestones

| Version | Theme | Unlocks | Status |
|:---:|---|---|:---:|
| **v0.1** | Single-process reference impl | 3 bridges · 9-state lifecycle · CapABAC · 5 workflow patterns · CLI · Claude | ✅ Alpha |
| **v0.2** | Production-ready single-tenant | gRPC transport · distributed registry · OpenTelemetry · persistent audit | 🚧 Next |
| **v0.3** | Multi-tenant & federation | Federated discovery · tenant isolation · rate-limit policies · backpressure | 🔜 |
| **v0.4** | Polyglot SDKs | TypeScript · Go · Rust client SDKs · spec conformance test suite (shipped, see track 6) | 🚧 |
| **v1.0** | Standard-grade | Second independent implementation · spec frozen · backward-compat guarantee · security audit | 🔜 |

> Version dates are deliberately not pinned — we ship when acceptance criteria are met, not when a calendar says so. Track live progress in [Discussions](https://github.com/gaiaagent/gaiaagent/discussions) and [Issues](https://github.com/gaiaagent/gaiaagent/issues).

---

## Workstreams

Work is organized into six tracks that move in parallel. Each item lists **what**, **why**, and **acceptance criteria**.

### 🧠 Track 1 — Runtime & Lifecycle

| Item | Status | Why |
|:---|:---:|---|
| 9-state lifecycle state machine | ✅ | No protocol standardized agent lifecycle before AURC |
| Policy-based error recovery (6 strategies) | ✅ | Agents must self-heal, not just crash |
| 4-scope context store (session/agent/shared/global) | ✅ | Memory isolation across tasks and agents |
| Pause/resume via `asyncio.Event` | ✅ | HITL gates and resource waits |
| **Durable lifecycle** (survive harness restart) | 🔜 | Long-running agents that outlive a process |
| **Checkpoint & rewind** | 💡 | Debug and replay multi-agent runs |
| **Resource quotas & backpressure** | 🔜 | Multi-tenant safety |

### 🌉 Track 2 — Interoperability

| Item | Status | Why |
|:---|:---:|---|
| MCP Bridge (JSON-RPC ↔ AURC) | ✅ | Tools are the most-adopted layer |
| A2A Bridge (tasks/send ↔ AURC) | ✅ | Agent-to-agent delegation |
| ACP Bridge (HTTP envelope ↔ AURC) | ✅ | Lightweight REST messaging |
| Bidirectional context preservation (`correlation_id`, `bridge_chain`) | ✅ | Traceability across hops |
| Messaging-channel bridges (Slack / Telegram / Discord) + channel e2e demo | ✅ | Chat surfaces as first-class AURC channels |
| **gRPC Bridge** | 🔜 | High-performance internal meshes |
| **GraphQL Bridge** | 💡 | Schema-first ecosystems |
| **NATS / Kafka / AMQP bridges** | 💡 | Event-driven agent backbones |
| **Bridge conformance test suite** | 🔜 | Third-party bridges must be provably correct |

### 🔒 Track 3 — Security & Governance

| Item | Status | Why |
|:---|:---:|---|
| API Key + JWT + mTLS-ready auth | ✅ | Dev to production flexibility |
| CapABAC authorization engine | ✅ | Fine-grained, constraint-based access |
| Delegation chain validation (scopes only narrow) | ✅ | Solves MCP's confused deputy |
| Append-only audit log | ✅ | Compliance and forensics |
| **Pluggable audit sinks** (S3, SIEM, opaque token) | 🔜 | Enterprise compliance pipelines |
| **Per-tenant authz & rate limits** | 🔜 | Multi-tenant isolation |
| **Signed delegation chains** (cryptographic) | 💡 | Non-repudiation across orgs |
| **Third-party security audit** | 🔜 | Trust before v1.0 |

### 📊 Track 4 — Observability & Operations

| Item | Status | Why |
|:---:|:---:|---|
| Health dashboard (HTML + JSON) | ✅ | Operator visibility |
| Router statistics & dead-letter queue | ✅ | Debug undeliverable messages |
| State-change listeners | ✅ | Alerting and metrics export |
| HTTP/2 + WebSocket transports | ✅ | Prod + real-time |
| **Prometheus metrics exporter** (`/metrics`) | ✅ | Scrape AURC with any Prometheus-compatible scraper |
| **Structured `bridge_chain` tracing** | ✅ | Reconstruct a request's cross-protocol path by `correlation_id` |
| **OpenTelemetry tracing** | 🔜 | Ship spans to a distributed backend (trace recorder is the in-process base) |
| **gRPC transport** | 🔜 | High-throughput internal deploys |

### 🌐 Track 5 — Ecosystem & SDKs

| Item | Status | Why |
|:---:|:---:|---|
| `@aurc_agent` / `@skill` Python decorators | ✅ | 30-second agent definition |
| Claude integration (agentic loop, tool use) | ✅ | Reference LLM backend |
| `claude` CLI as loop backend (`agentic_loop` delegates to `claude -p --output-format stream-json`, safe subprocess, defensive parsing) | ✅ | Loop Roadmap Step 2 — see [LOOP_ROADMAP.md](LOOP_ROADMAP.md) |
| AURC MCP server (`gaiaagent.mcp` — expose `@skill` agents as MCP tools for the CLI) | ✅ | Loop Roadmap Step 1 keystone — bus routing at the protocol level |
| `aurc` CLI (serve/validate/bridge test/registry export) | ✅ | DevX without writing code |
| End-to-end demo + multi-agent example | ✅ | Copy-paste starting points |
| **Pluggable LLM backends** (beyond Claude) | 🔜 | No vendor lock-in |
| **TypeScript SDK** | 🔜 | Node/Browser agent ecosystem |
| **Go SDK** | 🔜 | Infrastructure-side agents |
| **Rust SDK** | 🔜 | Embedded / edge agents |
| **Bridge & plugin registry** | 💡 | Discoverable community extensions |

### 📜 Track 6 — Standardization

| Item | Status | Why |
|:---:|:---:|---|
| AURC v0.1 spec (PROTOCOL.md, CC BY-SA 4.0) | ✅ | Frozen reference for implementers |
| AURC-RFC process | ✅ | Governed protocol evolution |
| **Conformance test suite** | 🚧 | "AURC-compatible" now has a defined meaning (`gaiaagent.conformance`: structural + semantic layers, `aurc conformance` CLI); third parties can self-prove compliance |
| **Second independent implementation** | 🔜 | The bar to call AURC a true standard |
| **W3C-style trace-context interop** | 💡 | Align with broader tracing standards |
| **Spec v1.0 freeze + compat guarantee** | 🔜 | Stability for production adopters |

---

## Recently Shipped (v0.1.0 alpha)

A credibility-oriented snapshot of what already runs end-to-end today (`python main.py` exercises all of it):

- ✅ 8-layer stack: L0 Transport → L7 Discovery, each layer independently testable
- ✅ `AURCId` URN identity + `AgentDescriptor` identity document
- ✅ 9-state lifecycle engine with 6-strategy error recovery
- ✅ Unified Message Bus: `MessageRouter` (direct/bridge/broadcast/dead-letter), `SessionManager`, JSON/NDJSON codecs
- ✅ Bidirectional bridges for **MCP, A2A, ACP, Slack, Telegram, Discord** with capability mapping + channel senders
- ✅ HTTP/2 + WebSocket transports
- ✅ CapABAC: API Key/JWT auth, authorization engine, delegation-chain validation, append-only audit log
- ✅ `LocalRegistry` with capability/tag/protocol matching
- ✅ 5 orchestration patterns + `DynamicWorkflowEngine`
- ✅ Claude integration: `ClaudeLLM`, agentic loop, tool use, `ClaudeAgent` base
- ✅ `aurc` CLI + health dashboard
- ✅ Prometheus metrics exporter (`/metrics`) + structured `bridge_chain` tracing

---

## Non-Goals

Stating what we will *not* build is as important as what we will. These are deliberate:

| Non-Goal | Reason |
|:---|:---|
| ❌ **A competing agent protocol** | AURC *bridges* MCP/A2A/ACP, it does not replace them. "Bridge First, Don't Replace." |
| ❌ **An LLM provider / model training** | Claude is one pluggable backend. GaiaAgent is protocol-agnostic about the model. |
| ❌ **A closed/SaaS-only runtime** | Reference impl is Apache-2.0; the spec is CC BY-SA 4.0. Open by construction. |
| ❌ **Lock-in to one language** | Python is the reference; TS/Go/Rust SDKs are on the roadmap precisely to avoid this. |
| ❌ **Blockchain/DID identity dependency** | AURC IDs are simple URNs — no ledger, no key-recovery ceremony required to start. |
| ❌ **Breaking changes after v1.0** | Post-1.0, backward compatibility is a hard contract, governed by RFC. |

---

## How to Influence

- **Pick a `💡` or `🔜` item** — these are the open frontier. Comment in [Discussions](https://github.com/gaiaagent/gaiaagent/discussions) to claim it.
- **Propose a new bridge** (gRPC, GraphQL, NATS, Kafka…) — see the [Bridge Developer Guide](docs/en/architecture/bridge-guide.md).
- **Change the protocol** — anything normative goes through the [AURC-RFC process](CONTRIBUTING.md#protocol-changes).
- **Build the second implementation** — the single highest-leverage contribution toward AURC becoming a standard.

### Good First Issues

- A `map_capabilities` round-trip test for the ACP bridge
- ✅ A `SlackBridge` + `TelegramBridge` + `DiscordBridge` reference implementation (see [Bridges Guide](docs/en/guides/bridges.md))
- An OpenTelemetry exporter layered on `BridgeTraceRecorder` (Track 4)
- A TypeScript client for the AURC HTTP transport

---

*This roadmap is a living document. Edits are welcome via PR — label it `roadmap` so we can discuss scope before committing.*
