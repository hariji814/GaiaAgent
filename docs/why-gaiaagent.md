# Why GaiaAgent?

## The Problem

AI agent frameworks are proliferating. MCP, A2A, and ACP each solve part
of the communication puzzle — but they don't talk to each other, and none
of them manages agent **lifecycle**.

| Protocol | Tool Calling | Agent-to-Agent | Lifecycle | Cross-Protocol |
|----------|:---:|:---:|:---:|:---:|
| MCP | Yes | No | No | No |
| A2A | No | Yes | No | No |
| ACP | Partial | Partial | No | No |
| **AURC** | **Yes** | **Yes** | **Yes** | **Yes** |

If you build an agent for MCP, it can't delegate to an A2A agent. If you
build for A2A, you can't call MCP tools. And none of them can pause,
resume, recover, or gracefully shut down an agent.

## The Solution: AURC

**AURC (Agent Unified Runtime & Communication)** is a bridging protocol
that sits above MCP, A2A, and ACP. It provides:

### 1. Lifecycle Management (the core innovation)

A 9-state state machine: REGISTERING -> READY -> RUNNING -> PAUSED ->
COMPLETED/FAILED/STOPPED, with error recovery (RECOVERING), retry with
backoff, and graceful shutdown.

Neither MCP, A2A, nor ACP has this. This is what makes AURC a *runtime*
protocol, not just a *communication* protocol.

### 2. Protocol Bridges

MCP, A2A, and ACP messages are all translated to/from a canonical
AURCMessage format. This means:
- An MCP agent can call an A2A agent through AURC
- An A2A agent can invoke ACP tasks through AURC
- A single audit trail spans all protocol boundaries

### 3. Observability

- **Audit log**: tamper-evident event trail
- **Health dashboard**: live HTML dashboard with agent states, metrics,
  and audit events
- **Prometheus metrics**: standard /metrics endpoint for scraping
- **Bridge-chain tracing**: see the full path of a message across protocols

### 4. Security

- **CapABAC**: capability-based access control
- **Delegation chains**: scope narrowing validation prevents the
  confused deputy problem
- **Token references**: messages carry token references, not raw tokens

## Why Apache-2.0?

We chose Apache-2.0 (migrated from AGPL-3.0) because:
- **Permissive**: companies can adopt AURC without legal concerns
- **Compatible**: works with proprietary and GPL-licensed projects alike
- **Standard**: widely understood and trusted in the industry
- **Adoption-friendly**: removes the biggest barrier to protocol adoption

## Try It

\`\`\`bash
pip install gaiaagent[http]
gaiaagent demo
\`\`\`

No API key, no configuration, no external services. The demo spins up
3 agents, runs a cross-protocol chain, and opens a live dashboard.

## Comparison

| Feature | GaiaAgent (AURC) | LangGraph | CrewAI | AutoGen |
|---------|:---:|:---:|:---:|:---:|
| Protocol standard | Yes (AURC v0.1) | No | No | No |
| Cross-protocol bridging | MCP+A2A+ACP | No | No | No |
| Agent lifecycle state machine | 9 states | No | No | No |
| Health monitoring + dashboard | Yes | No | No | No |
| Prometheus metrics | Yes | No | No | No |
| Audit trail | Yes | No | No | No |
| License | Apache-2.0 | MIT | MIT | MIT |

GaiaAgent is not a competitor to LangGraph or CrewAI — it is the
**protocol layer** that makes agents from different frameworks
interoperable.
