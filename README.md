<p align="center">
  <img src="https://raw.githubusercontent.com/gaiaagent/gaiaagent/main/docs/assets/logo.png" alt="GaiaAgent" width="120" />
</p>

<h1 align="center">GaiaAgent</h1>

<p align="center">
  <strong>The Universal Protocol Layer for AI Agent Interoperability</strong><br/>
  <em>The unified runtime layer bridging all AI agent protocols</em>
</p>

<p align="center">
  <a href="https://github.com/gaiaagent/gaiaagent/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/gaiaagent/gaiaagent/ci.yml?style=flat-square&label=CI" alt="CI" /></a>
  <a href="https://pypi.org/project/gaiaagent/"><img src="https://img.shields.io/pypi/v/gaiaagent?style=flat-square&color=blue" alt="PyPI" /></a>
  <a href="https://pypi.org/project/gaiaagent/"><img src="https://img.shields.io/pypi/pyversions/gaiaagent?style=flat-square&color=blue" alt="Python" /></a>
  <a href="https://github.com/gaiaagent/gaiaagent/blob/main/LICENSE"><img src="https://img.shields.io/github/license/gaiaagent/gaiaagent?style=flat-square&color=blue" alt="License" /></a>
  <a href="https://github.com/gaiaagent/gaiaagent/stargazers"><img src="https://img.shields.io/github/stars/gaiaagent/gaiaagent?style=flat-square" alt="Stars" /></a>
  <a href="https://discord.gg/gaiaagent"><img src="https://img.shields.io/badge/Discord-join-7289DA?style=flat-square&logo=discord" alt="Discord" /></a>
</p>

<p align="center">
  <em>Status: <strong>Alpha (v0.1.0)</strong> — spec frozen, reference implementation shipping, API may still move. Not production-hardened yet.</em>
</p>

> 🌐 [中文版](README.zh.md)

---

## The 30-Second Pitch

> **MCP gave agents tools. A2A gave them each other. ACP gave them a mailbox. Nobody gave them a runtime.**
>
> GaiaAgent is the **connective tissue** the agent era is missing: one layer that bridges every protocol, manages agent lifecycles, enforces security across delegation chains, and orchestrates multi-agent workflows — without asking you to abandon a single line of MCP or A2A code you've already written.

**One agent. One identity. Any protocol. Bridges, not walls.**

---

## Why Now

2025–2026 produced a Cambrian explosion of agent protocols — **MCP** (Anthropic), **A2A** (Google), **ACP** (IBM), **ANP** — each brilliant, each solving exactly one slice of the stack. The result: an ecosystem where an agent that owns the best tools (MCP) **cannot delegate** to the best specialist (A2A), and neither can prove *who authorized what* across the hop.

We don't need protocol **number five**. We need the **layer beneath all of them** — the way TCP/IP became the shared substrate beneath a hundred application protocols. AURC is that substrate for agents: a runtime, a security model, and a bus that the existing protocols *plug into* rather than compete with.

---

## At a Glance

| | |
|:---|:---|
| **8-layer stack** | L0 Transport → L7 Discovery, OSI-for-agents, each layer independently testable |
| **3 protocol bridges** | MCP · A2A · ACP — bidirectional, context-preserving, capability-mapped |
| **9-state lifecycle** | The first standardized agent state machine: register → ready → run → recover → complete |
| **CapABAC security** | Capability + attribute-based authz, delegation chains that *only narrow*, never widen |
| **5 orchestration patterns** | Chain · Route · Parallel · Orchestrator-Workers · Evaluator-Optimizer |
| **4 context scopes** | session / agent / shared / global, with cross-protocol correlation IDs |
| **Claude-native** | Agentic loop backed by the `claude` CLI; AURC `@skill`s exposed to the loop via a built-in MCP server (see [LOOP_ROADMAP.md](LOOP_ROADMAP.md)) |
| **Transports** | HTTP/2 · WebSocket · stdio (gRPC planned) |

---

## The Problem

The AI agent ecosystem in 2026 is **fragmented into incompatible protocol islands**:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│   MCP (Anthropic)       A2A (Google)        ACP (IBM)       ANP         │
│   ┌───────────┐        ┌───────────┐       ┌───────────┐   ┌───────┐   │
│   │ Agent↔Tool│        │ Agent↔Agent│      │ REST Msg  │   │Identity│  │
│   │           │   ✗    │           │  ✗    │           │ ✗ │       │  │
│   │ No A2A    │        │ No Tools  │       │ Minimal   │   │No Msg │  │
│   │ No Runtime│        │ No Bridge │       │ No Runtime│   │No Run │  │
│   └───────────┘        └───────────┘       └───────────┘   └───────┘  │
│                                                                         │
│   Each protocol solves ONE layer. None bridge them all.                 │
│   No unified lifecycle. No cross-protocol security. No context flow.    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

An agent using MCP for tools **cannot seamlessly delegate to an A2A agent**. Neither protocol manages agent state, error recovery, or context persistence across boundaries. **The industry needs a connective tissue — not another competing protocol.**

---

## GaiaAgent: The Solution

GaiaAgent implements **AURC** (Agent Unified Runtime & Communication) — a **meta-protocol** that doesn't replace MCP, A2A, or ACP. It **connects them**.

```
┌──────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│                    Your Application                                      │
│                                                                          │
│         @aurc_agent    @skill    ClaudeAgent    WorkflowEngine           │
│                                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│                         G A I A A G E N T                                │
│                                                                          │
│   ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  ┌────────────┐ │
│   │   Runtime    │  │   Unified    │  │   Protocol    │  │  Security  │ │
│   │   Harness    │  │  Message Bus │  │   Bridges     │  │   Layer    │ │
│   │              │  │              │  │               │  │            │ │
│   │ • Lifecycle  │  │ • Router     │  │ ┌───┐ ┌───┐  │  │ • CapABAC  │ │
│   │ • State      │  │ • Session    │  │ │MCP│ │A2A│  │  │ • Delegation│ │
│   │ • Health     │  │ • Codec      │  │ └───┘ └───┘  │  │ • Audit    │ │
│   │ • Recovery   │  │ • WebSocket  │  │ ┌───┐ ┌───┐  │  │ • Auth     │ │
│   │ • Context    │  │              │  │ │ACP│ │Custom│ │  │            │ │
│   │ • HITL       │  │              │  │ └───┘ └───┘  │  │            │ │
│   └─────────────┘  └──────────────┘  └───────────────┘  └────────────┘ │
│                                                                          │
│   ┌──────────────────────┐  ┌─────────────────────────────────────────┐ │
│   │  Workflow Engine     │  │  Claude Integration                     │ │
│   │  5 Orchestration     │  │  ClaudeLLM + Agentic Loop              │ │
│   │  Patterns            │  │  + Tool Use + Dynamic Workflows        │ │
│   └──────────────────────┘  └─────────────────────────────────────────┘ │
│                                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   MCP Servers       A2A Agents       ACP Services     Future Protocols  │
│   (Tools)           (Agent-to-Agent) (Lightweight)    (gRPC, Custom)    │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**One agent. One identity. Any protocol.**

---

## Why GaiaAgent?

| What Others Lack | GaiaAgent Delivers |
|:---|:---|
| **No lifecycle management** in any protocol | **9-state lifecycle engine** with automatic error recovery, pause/resume, and graceful shutdown |
| **Protocol silos** — agents locked to one protocol | **Protocol bridges** that translate MCP ↔ A2A ↔ ACP ↔ AURC seamlessly |
| **No security model** (MCP's confused deputy problem) | **CapABAC authorization** — capability-based + attribute-based, with delegation chain validation |
| **No cross-protocol context** | **4-scope context system** (session / agent / shared / global) with correlation tracking |
| **No human-in-the-loop** standard | **Standardized HITL protocol** with approval gates, options, and timeout handling |
| **No observability** | **Built-in audit logging**, health monitoring, and router statistics |
| **No orchestration patterns** | **5 canonical patterns** powered by Claude: Chain, Route, Parallel, Orchestrator-Workers, Eval-Optimize |

---

## Quick Start

### Installation

```bash
pip install gaiaagent

# Pick only what you need
pip install gaiaagent[http]        # HTTP/2 transport
pip install gaiaagent[websocket]   # real-time bidirectional transport
pip install gaiaagent[claude]      # Claude integration

# Or install everything
pip install gaiaagent[all]
```

### See It in Action (30 Seconds, No API Key)

```bash
# Install with HTTP transport support
pip install gaiaagent[http]

# Run the built-in demo: 3 agents, cross-protocol chain, live dashboard
gaiaagent demo
```

This spins up 3 demo agents (Researcher, Analyst, Writer) in a PromptChain
workflow, routes messages across MCP -> A2A -> ACP protocol boundaries,
opens a live health dashboard in your browser, and requires zero
configuration or API keys. It is the fastest way to see what AURC does.

### Define an Agent in 30 Seconds

```python
from gaiaagent.sdk.decorators import aurc_agent, skill

@aurc_agent(
    id="aurc:myproject/researcher:v1.0",
    display_name="Research Agent",
    description="Deep research with multi-source analysis",
    protocols=["mcp/2025-06-18", "a2a/1.0"],
    tags=["research", "analysis"],
)
class ResearchAgent:

    @skill("deep-research", description="Multi-source research and synthesis")
    async def research(self, query: str, depth: str = "medium") -> dict:
        return {
            "report": f"Research report for: {query}",
            "confidence": 0.85,
            "sources": ["arxiv", "web"],
        }

    @skill("summarize", description="Summarize research findings")
    async def summarize(self, text: str, max_length: int = 500) -> dict:
        return {"summary": text[:max_length]}
```

### Launch the Runtime

```python
import asyncio
from gaiaagent import RuntimeHarness

async def main():
    harness = RuntimeHarness()

    agent = ResearchAgent()
    await harness.register(agent.aurc_descriptor)
    await harness.start("aurc:myproject/researcher:v1.0")

    # Full lifecycle management
    health = await harness.health_check("aurc:myproject/researcher:v1.0")
    print(f"Status: {health.status.value}")  # "healthy"

asyncio.run(main())
```

### Bridge Any Protocol

```python
from gaiaagent.bridges.base import MCPBridge, BridgeRegistry
from gaiaagent.bridges.a2a import A2ABridge
from gaiaagent.bridges.acp import ACPBridge

bridges = BridgeRegistry()
bridges.register(MCPBridge())    # MCP tools/call ↔ AURC request
bridges.register(A2ABridge())    # A2A tasks/send ↔ AURC delegation
bridges.register(ACPBridge())    # ACP invoke ↔ AURC delegation

# Translate any protocol message to AURC's canonical format
aurc_msg = await bridges.get("mcp").translate_to_aurc(mcp_tool_call)
```

### Orchestrate with 5 Patterns

```python
from gaiaagent.workflows.orchestrator import DynamicWorkflowEngine

engine = DynamicWorkflowEngine()

# 1. Prompt Chain — sequential pipeline
result = await engine.chain([translate, summarize, format_output], initial_input="Hello")

# 2. Intelligent Routing — classifier picks the best handler
result = await engine.route(input_data=request, routes={"code": handle_code, "research": handle_research})

# 3. Parallel Fan-Out — concurrent execution + aggregation
result = await engine.parallel([search_arxiv, search_web, search_patents], input_data="AI agents")

# 4. Orchestrator-Workers — Claude dynamically decomposes tasks
result = await engine.orchestrate(orchestrator=claude_decomposer, workers={"research": researcher, "code": coder})

# 5. Evaluator-Optimizer — iterative refinement loop
result = await engine.optimize(generator=draft, evaluator=quality_check, quality_threshold=0.9)
```

---

## Architecture: The 8-Layer Protocol Stack

GaiaAgent introduces the first complete **8-layer protocol stack** for AI agent communication — inspired by the OSI model but purpose-built for the agent era.

```
 ┌─────────────────────────────────────────────────────────────────────────┐
 │                                                                         │
 │  L7  DISCOVERY        Agent registry · capability matching              │
 │       health-based routing · mDNS · federation                          │
 │  ─────────────────────────────────────────────────────────────────────  │
 │  L6  SECURITY         CapABAC auth · delegation chains                  │
 │       audit logging · permission attenuation                            │
 │  ─────────────────────────────────────────────────────────────────────  │
 │  L5  CONTEXT          Cross-protocol context tracking                   │
 │       permission propagation · W3C trace context                        │
 │  ─────────────────────────────────────────────────────────────────────  │
 │  L4  BRIDGES          MCP Bridge · A2A Bridge · ACP Bridge              │
 │       Custom Bridge · capability mapping                                │
 │  ─────────────────────────────────────────────────────────────────────  │
 │  L3  MESSAGE BUS      Canonical JSON format · routing · session mgmt   │
 │       NDJSON streaming · message framing                                │
 │  ─────────────────────────────────────────────────────────────────────  │
 │  L2  HARNESS          Lifecycle state machine · health monitoring       │
 │       context/memory · error recovery · HITL                            │
 │  ─────────────────────────────────────────────────────────────────────  │
 │  L1  IDENTITY         AURC ID (URN) · capability declaration            │
 │       Agent Descriptor · protocol binding                               │
 │  ─────────────────────────────────────────────────────────────────────  │
 │  L0  TRANSPORT        HTTP/2 · WebSocket · stdio · gRPC                 │
 │       transport negotiation · TLS                                        │
 │                                                                         │
 └─────────────────────────────────────────────────────────────────────────┘
```

### The Runtime Harness — Core Innovation

**No existing protocol provides agent lifecycle management.** GaiaAgent's Runtime Harness is the first standardized agent lifecycle engine with a 9-state machine:

```
                    ┌──────────────────────────────────┐
                    │                                  │
                    ▼                                  │
              ┌──────────────┐                        │
              │ REGISTERING  │────────────────┐       │
              └──────────────┘                │       │
                    │                         │       │
               registered                     │       │
                    │                         │       │
                    ▼                         ▼       │
              ┌──────────┐              ┌──────────┐  │
        ┌────▶│  READY   │              │  FAILED  │  │
        │     └────┬─────┘              └──────────┘  │
        │          │                                   │
        │     start│                                   │
        │          ▼                                   │
        │   ┌──────────────┐    error    ┌──────────┐ │
        │   │   RUNNING    │────────────▶│ FAILING  │─┘
        │   └──┬──┬────┬───┘             └────┬─────┘
        │      │  │    │                      │
  pause()│  complete  │  error          recover│
        │      │  │    │                      │
        │      │  │    │                      ▼
        │      │  │    │              ┌──────────────┐
        │      │  │    │              │  RECOVERING  │
        │      │  │    │              └──────┬───────┘
        │      ▼  │    ▼                     │
        │  ┌──────────┐ ┌──────────┐    recovered
        │  │COMPLETED │ │ PAUSED   │         │
        │  └──────────┘ └────┬─────┘         │
        │                     │               │
        │               resume│               │
        │                     └───────────────┘
        │
        └──── (back to READY for next task)
```

### Error Recovery That Actually Works

| Trigger | Strategy | Behavior |
|:---|:---|:---|
| `timeout` | Retry with Backoff | Exponential backoff: 1s → 5s → 15s |
| `tool_error` | Alternative Tool | Try a different tool/skill |
| `context_overflow` | Compact & Retry | Summarize oldest context and retry |
| `auth_expired` | Refresh & Retry | Refresh credentials and retry |
| `unrecoverable` | Escalate to Human | HITL intervention with full context |

---

## Security: Solving MCP's Confused Deputy Problem

MCP has a fundamental security flaw: **servers act on behalf of users but cannot distinguish or enforce what users are authorized to do.** GaiaAgent solves this with **CapABAC** — a hybrid authorization model combining Capability-Based Security with Attribute-Based Access Control.

```
┌──────────────────────────────────────────────────────────────────────┐
│                                                                      │
│  User [read, write, admin]                                           │
│    │                                                                 │
│    │  Delegation Hop 1                                               │
│    ▼                                                                 │
│  Orchestrator [read, write]          ← narrowed ✓                   │
│    │                                                                 │
│    │  Delegation Hop 2                                               │
│    ▼                                                                 │
│  Researcher [read]                   ← narrowed ✓                   │
│    │                                                                 │
│    │  Delegation Hop 3                                               │
│    ▼                                                                 │
│  MCP Tool [read, execute]            ← WIDENED ✗ REJECTED!         │
│                                                                      │
│  Rules:                                                              │
│  • Scopes only narrow, never widen                                   │
│  • No circular delegations                                           │
│  • Timestamps must be monotonically ordered                          │
│  • Max delegation depth enforced                                      │
│  • Every hop is cryptographically auditable                          │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

**Multi-layer security stack:**

| Layer | Mechanism | Purpose |
|:---|:---|:---|
| Authentication | API Key · JWT · OAuth 2.1 · mTLS | Verify agent identity |
| Authorization | CapABAC Engine | Fine-grained, constraint-based access control |
| Delegation | Chain Validation | Prevent permission escalation across hops |
| Audit | Immutable Log | Record every security event for compliance |

---

## Cross-Protocol Communication

GaiaAgent's bridges translate between protocol semantics while preserving context, permissions, and traceability:

### Scenario: Multi-Protocol Mixed Workflow

```
                              ┌───────────────┐
                              │  User Request  │
                              └───────┬───────┘
                                      │
                                      ▼
                         ┌────────────────────────┐
                         │   AURC Orchestrator     │
                         │   (Claude-powered)      │
                         └────┬──────┬──────┬──────┘
                              │      │      │
                    ┌─────────┘      │      └──────────┐
                    ▼                ▼                  ▼
          ┌──────────────┐ ┌──────────────┐  ┌──────────────┐
          │  AURC Agent  │ │  MCP Server  │  │  A2A Agent   │
          │  (native)    │ │  (via Bridge)│  │  (via Bridge)│
          │              │ │              │  │              │
          │  Direct      │ │  tools/call  │  │  tasks/send  │
          │  Communication│ │  ← translated│  │  ← translated│
          └──────┬───────┘ └──────┬───────┘  └──────┬───────┘
                 │                │                  │
                 └────────────────┼──────────────────┘
                                  │
                          correlation_id
                          delegation_chain
                                  │
                                  ▼
                         ┌────────────────────────┐
                         │  Results Aggregated     │
                         │  All steps traced       │
                         │  Permissions unified     │
                         └────────────────────────┘
```

---

## Protocol Comparison

How AURC compares to existing protocols — not as a competitor, but as the **connective layer** they all need:

| Capability | MCP | A2A | ACP | ANP | **GaiaAgent/AURC** |
|:---|:---:|:---:|:---:|:---:|:---:|
| Agent Identity | ✗ | Agent Card | ✗ | DID | **AURC ID (URN)** |
| Tool Invocation | ✓ | ✗ | ✓ | ✗ | **via Bridge** |
| Agent-to-Agent | ✗ | ✓ | ✓ | ✓ | **via Bridge** |
| **Runtime Lifecycle** | ✗ | Task only | ✗ | ✗ | **✓ (9-state engine)** |
| **Context/Memory** | Resources | ✗ | ✗ | ✗ | **✓ (4-scope system)** |
| **Cross-Protocol** | ✗ | ✗ | ✗ | ✗ | **✓ (core feature)** |
| **Permission Enforcement** | ✗ | ✗ | ✗ | ✗ | **✓ (CapABAC)** |
| **Delegation Audit** | ✗ | ✗ | ✗ | ✗ | **✓ (chain validation)** |
| **Error Recovery** | ✗ | ✗ | ✗ | ✗ | **✓ (5 strategies)** |
| **Human-in-the-Loop** | ✗ | Basic | ✗ | ✗ | **✓ (standardized)** |
| **Workflow Patterns** | ✗ | ✗ | ✗ | ✗ | **✓ (5 patterns + Claude)** |

---

## Project Structure

```
gaiaagent/
├── core/                   # Foundation types, identity, messages, capabilities
│   ├── identity.py         #   AURC ID format, Agent Descriptor
│   ├── message.py          #   Canonical message format
│   ├── capability.py       #   Capability matching engine
│   └── types.py            #   State machine types, recovery policies
│
├── sdk/                    # Developer-facing SDK
│   └── decorators.py       #   @aurc_agent, @skill decorators
│
├── harness/                # Runtime Harness (L2)
│   ├── lifecycle.py        #   9-state lifecycle engine
│   └── context.py          #   Multi-scope context store
│
├── bus/                    # Unified Message Bus (L3)
│   ├── router.py           #   Message routing + statistics
│   ├── session.py          #   Session/conversation management
│   └── codec.py            #   JSON/NDJSON/MessagePack codecs
│
├── bridges/                # Protocol Bridges (L4)
│   ├── base.py             #   Bridge interface + MCP Bridge
│   ├── a2a.py              #   A2A Bridge
│   └── acp.py              #   ACP Bridge
│
├── security/               # Security Layer (L6)
│   ├── auth.py             #   API Key + JWT Authentication
│   ├── authz.py            #   CapABAC Authorization Engine
│   ├── delegation.py       #   Delegation chain validation
│   └── audit.py            #   Immutable audit log
│
├── registry/               # Discovery (L7)
│   └── local.py            #   Local agent registry + capability matching
│
├── transport/              # Transport (L0)
│   ├── http.py             #   HTTP/2 transport server + client
│   └── websocket.py        #   WebSocket transport
│
├── workflows/              # Orchestration Patterns
│   └── orchestrator.py     #   5 patterns + DynamicWorkflowEngine
│
├── integrations/           # LLM Integrations
│   ├── claude.py           #   Claude LLM + Agentic Loop + Tool Use
│   └── claude_cli.py       #   `claude` CLI backend (Loop Roadmap Step 2)
│
├── mcp/                    # AURC MCP server (Loop Roadmap Step 1 keystone)
│   └── server.py           #   Expose @skill agents as MCP tools for the CLI
│
├── observability/          # Monitoring & tracing
│   ├── dashboard.py        #   Health dashboard (HTML + JSON + ASGI API)
│   ├── metrics.py          #   Prometheus /metrics exporter
│   └── tracing.py          #   Bridge-chain trace recorder (correlation by ID)
│
└── cli.py                  # `aurc` CLI tool
```

---

## Development

```bash
# Clone the repository
git clone https://github.com/gaiaagent/gaiaagent
cd gaiaagent

# Install with all development dependencies
pip install -e ".[all]"

# Run the full end-to-end demo (showcases all 13 components)
python main.py

# Run tests
pytest

# Run with coverage report
pytest --cov=src/gaiaagent --cov-report=term-missing

# Type check (strict mode)
mypy src/

# Lint
ruff check src/ tests/

# Or use make for convenience
make all      # lint + type-check + test
make demo     # run the end-to-end demo
make serve    # start server with dashboard
```

### Docker

```bash
# Build and run
docker compose up -d

# Or build standalone
docker build -t gaiaagent .
docker run -p 8080:8080 gaiaagent
```

---

## Roadmap

> GaiaAgent is **v0.1.0 alpha**: the spec is frozen and the reference implementation ships the layers below, but APIs are still settling and production hardening is ongoing. The full, living plan lives in **[ROADMAP.md](ROADMAP.md)** — north star, six workstreams, version milestones, acceptance criteria, and explicit non-goals.

| Version | Theme | Status |
|:---:|:---|:---:|
| **v0.1** | Single-process reference impl (3 bridges · 9-state lifecycle · CapABAC · 5 patterns · CLI · Claude) | ✅ Alpha |
| **v0.2** | Production-ready single-tenant (gRPC · distributed registry · OpenTelemetry · persistent audit) | 🚧 Next |
| **v0.3** | Multi-tenant & federation | 🔜 |
| **v0.4** | Polyglot SDKs (TypeScript · Go · Rust) + conformance suite | 🔜 |
| **v1.0** | Standard-grade: second independent implementation · spec frozen · security audit | 🔜 |

**What "alpha" means here:** the modules exist, are unit-tested (352 passing), and run end-to-end in `python main.py` — but edge cases, perf, and the *second independent implementation* (the bar to call AURC a true standard) are still ahead. See [PROTOCOL.md](PROTOCOL.md) for the frozen spec, [ROADMAP.md](ROADMAP.md) for what's next.

> 📌 **Highest-leverage contribution:** build the second independent implementation of AURC — that single act graduates the protocol from "our spec" to "a standard."

---

## Documentation

| Document | Description |
|:---|:---|
| [ROADMAP.md](ROADMAP.md) | **Living roadmap** — north star, six workstreams, milestones, non-goals |
| [PROTOCOL.md](PROTOCOL.md) | **Full AURC protocol specification** — the canonical reference |
| [LOOP_ROADMAP.md](LOOP_ROADMAP.md) | **GaiaAgent × Anthropic agentic loop** — integrating the Claude Agent SDK as the inner execution engine |
| [Architecture Overview](docs/en/architecture/overview.md) | System map, module dependencies, design decisions |
| [Security Model](docs/en/architecture/security-model.md) | Threat model, CapABAC deep-dive, delegation rules |
| [Bridge Developer Guide](docs/en/architecture/bridge-guide.md) | How to write custom protocol bridges |
| [Quick Start](docs/en/guides/quickstart.md) | 5-minute tutorial for your first agent |
| [Workflow Patterns](docs/en/guides/workflows.md) | 5 orchestration patterns + Claude integration |
| [Deployment Guide](docs/en/guides/deployment.md) | Local, Docker, and production deployment |
| [API Reference](docs/en/api-reference.md) | Complete API documentation |

---

## Who Is This For?

- **AI Platform Engineers** building multi-agent systems that need to communicate across protocol boundaries
- **Enterprise Architects** who need governed, auditable agent interactions with proper security
- **Framework Authors** building agent frameworks who want interoperability without lock-in
- **Researchers** exploring agent coordination, delegation, and emergent multi-agent behaviors
- **Anyone** who's tired of choosing between MCP, A2A, and ACP — use all of them through GaiaAgent

---

## Adopters & Ecosystem

> A protocol only becomes a standard when **two independent implementations** agree. GaiaAgent is the reference implementation of AURC — the second is yours.

**Using GaiaAgent or implementing AURC?** Open a PR adding yourself below, or tell us in [Discussions](https://github.com/gaiaagent/gaiaagent/discussions). We spotlight bridges, registries, and language ports the community builds.

| Project | Layer | Link |
|:---|:---|:---|
| _Be the first listed here._ | _Bridge / Registry / SDK / App_ | _—_ |

**Wanted:** gRPC · GraphQL · NATS · Kafka bridges · TypeScript/Go/Rust ports · distributed registry backends. Each is a great [good first issue](https://github.com/gaiaagent/gaiaagent/contribute) and a path to maintainer status.

---

## Contributing

GaiaAgent is built by a growing community of developers, researchers, and AI enthusiasts. We welcome contributions of all kinds:

- 🐛 **Bug reports** — found something broken? [Open an issue](https://github.com/gaiaagent/gaiaagent/issues)
- 💡 **Feature ideas** — have a protocol we should bridge? [Start a discussion](https://github.com/gaiaagent/gaiaagent/discussions)
- 🔧 **Code contributions** — see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines
- 📝 **Protocol changes** — require an [AURC-RFC](CONTRIBUTING.md#protocol-changes)

```bash
# Quick development setup
git clone https://github.com/gaiaagent/gaiaagent
cd gaiaagent
pip install -e ".[dev]"
pytest  # verify everything works
```

---

## Philosophy

> **"Bridge First, Don't Replace"**
>
> We don't believe the AI agent ecosystem needs another competing protocol.
> It needs a **connective layer** — one that respects existing investments in MCP, A2A, and ACP
> while providing the runtime, security, and orchestration capabilities that none of them offer alone.
>
> GaiaAgent is that layer.

---

## License

| Component | License |
|:---|:---|
| **Code** | [Apache-2.0](LICENSE) |
| **Protocol Specification** | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) |

---

<p align="center">
  <strong>If GaiaAgent resonates with your vision for the future of AI agents, give us a ⭐</strong><br/>
  <em>Every star helps the community grow.</em>
</p>

<p align="center">
  <a href="https://github.com/gaiaagent/gaiaagent">GitHub</a> ·
  <a href="https://gaiaagent.dev/docs">Documentation</a> ·
  <a href="https://discord.gg/gaiaagent">Discord</a> ·
  <a href="https://pypi.org/project/gaiaagent/">PyPI</a>
</p>
