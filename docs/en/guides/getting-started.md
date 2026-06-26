# Getting Started with GaiaAgent

> One document that explains what GaiaAgent is, why it exists, how to use it, and how to build your own agent.
>
> Language: [中文](../../zh/guides/getting-started.md) | [English](getting-started.md) | [5-min walkthrough](quickstart.md) | [Architecture](../architecture/overview.md) | [API reference](../api-reference.md)

## What is GaiaAgent?

GaiaAgent implements **AURC (Agent Unified Runtime & Communication)**, a bridging protocol layer that sits above MCP, A2A, and ACP. It addresses a real pain point: today an agent built for MCP cannot delegate to an A2A agent, an A2A agent cannot call MCP tools, and none of the three manages agent **lifecycle**.

AURC unifies all three into one canonical message format (`AURCMessage`) and fills the missing gaps:

1. **Lifecycle state machine**: 9 states (REGISTERING -> READY -> RUNNING -> PAUSED -> COMPLETED / FAILED / STOPPED, plus RECOVERING), with error recovery, backoff retry, and graceful shutdown.
2. **Protocol bridges**: MCP / A2A / ACP messages translate to/from the canonical format, so a single audit trail spans every protocol boundary.
3. **Observability**: tamper-evident audit log, a live HTML health dashboard, Prometheus metrics, and cross-protocol bridge-chain tracing.
4. **Security**: capability-based access control (CapABAC), scope-narrowing delegation chains to prevent the confused-deputy problem, and token references instead of raw tokens in messages.

In one line: **GaiaAgent is the protocol layer that makes agents from different frameworks interoperate, not yet another agent framework.**

## Installation

Requires Python 3.10+. Use `uv` or `pip`:

```bash
pip install "gaiaagent[http]"
# or
uv add "gaiaagent[http]"
```

The `[http]` extra installs the HTTP transport layer (needed for the dashboard and /metrics endpoint).

## 60-second tour: zero-config demo

The fastest way to understand AURC is the official demo - **no API key, no configuration**:

```bash
gaiaagent demo
```

It spins up 3 agents (researcher, analyst, writer), runs a chained workflow (research -> analyze -> write), crosses MCP -> A2A -> ACP protocol boundaries, and opens a live dashboard in your browser. All LLM responses come from built-in stubs, so it always runs.

## Plug in a real LLM

Want the demo to call a real model? Add `--api-key`:

```bash
# OpenAI (default)
gaiaagent demo --api-key sk-xxxx

# Anthropic
gaiaagent demo --api-key sk-ant-xxxx --llm-provider anthropic

# Pick a model
gaiaagent demo --api-key sk-xxxx --model gpt-4o
```

Internally it uses a zero-dependency `urllib` client (OpenAI / Anthropic compatible). Without a key, or if the call fails, it silently falls back to the stub responses, so the demo never breaks on network issues.

## Scaffold a project in one command

`gaiaagent init` generates a runnable agent scaffold:

```bash
gaiaagent init myproject
cd myproject
python agent.py
```

The generated `agent.py` is already a minimal AURC agent with lifecycle, registration, and callable skills - edit it into your first agent.

## Write your first agent

The scaffold looks like this (hand-writing it is identical):

```python
from typing import Any
from gaiaagent.sdk.decorators import aurc_agent, skill

@aurc_agent(
    id="aurc:myproject/translator:v1.0",
    display_name="Translator Agent",
    description="Translate text between languages",
    protocols=["mcp/2025-06-18"],
    tags=["translation", "nlp"],
)
class TranslatorAgent:

    @skill("translate", description="Translate text to a target language")
    async def translate(self, text: str, target_lang: str = "en") -> dict[str, Any]:
        return {"original": text, "translated": f"[{target_lang}] {text}"}

if __name__ == "__main__":
    import asyncio
    from gaiaagent import RuntimeHarness

    async def main() -> None:
        harness = RuntimeHarness()
        agent = TranslatorAgent()
        await harness.register(agent.aurc_descriptor)
        await harness.start(agent.aurc_descriptor.aurc_id)
        print(await agent.translate("Hello", "zh"))
        await harness.complete(agent.aurc_descriptor.aurc_id)

    asyncio.run(main())
```

Key points:

- `@aurc_agent` auto-generates `agent.aurc_descriptor` (an AgentDescriptor) declaring identity, capabilities, and protocol support.
- `@skill` registers a method as a routable, callable skill.
- Lifecycle is driven by `RuntimeHarness`: `register` -> `start` -> (run) -> `complete`.

## Bridge protocols

Bridges translate external-protocol messages into the canonical `AURCMessage` and back:

```python
from gaiaagent.bridges.base import MCPBridge

mcp_bridge = MCPBridge()

mcp_request = {
    "jsonrpc": "2.0",
    "id": "req-1",
    "method": "tools/call",
    "params": {"name": "web-search", "arguments": {"query": "AI protocols"}},
}

aurc_message = await mcp_bridge.translate_to_aurc(mcp_request)
print(aurc_message.body.skill)   # "web-search"

# Reverse: AURC -> MCP
external = await mcp_bridge.translate_from_aurc(aurc_message)
```

There is one bridge per protocol: `MCPBridge`, `A2ABridge` (`gaiaagent.bridges.a2a`), `ACPBridge` (`gaiaagent.bridges.acp`). Once registered on the router, messages addressed to `mcp:...` / `a2a:...` / `acp:...` prefixes are automatically forwarded through the matching bridge.

## Message routing

`MessageRouter` delivers each message to the right handler or bridge forwarder:

```python
from gaiaagent.bus.router import MessageRouter
from gaiaagent.core.message import AURCMessage, MessageBody
from gaiaagent.core.types import MessageDirection

router = MessageRouter()

async def handle(msg: AURCMessage):
    return {"status": "ok", "skill": msg.body.skill}

router.register_handler("aurc:myproject/translator:v1.0", handle)

# Send a direct message
msg = AURCMessage(
    source="aurc:myproject/orchestrator:v1.0",
    target="aurc:myproject/translator:v1.0",
    type=MessageDirection.REQUEST,
    body=MessageBody(method="invoke", skill="translate", params={"text": "Hello"}),
)
result = await router.route(msg)
print(router.stats.direct)   # 1
```

Routing supports direct, bridged, broadcast (subscription groups), wildcard, TTL hop limits, and a dead-letter queue.

## Observability

```python
from gaiaagent.observability.dashboard import HealthDashboard, DashboardAPI
from gaiaagent.security.audit import AuditLog

audit = AuditLog(max_entries=10_000)
dashboard = HealthDashboard(harness, audit=audit, router=router)
api = DashboardAPI(dashboard)

print(dashboard.get_system_health())      # system-level health
print(await harness.health_check_all())   # per-agent health reports
```

`gaiaagent demo` serves the dashboard over HTTP: `/dashboard` (HTML), `/health` (JSON), `/metrics` (Prometheus text format).

## Next steps

- [5-min walkthrough](quickstart.md): full snippets including authorization
- [Architecture overview](../architecture/overview.md): core abstractions and data flow
- [Bridge guide](../architecture/bridge-guide.md): how to write your own protocol bridge
- [Workflows](workflows.md): PromptChain / parallel fan-out / orchestrator-workers
- [Deployment](deployment.md): HTTP transport and production deployment
- [API reference](../api-reference.md)

## Why Apache-2.0?

AURC started as AGPL-3.0. To make the protocol genuinely adoptable we migrated to **Apache-2.0** - permissive enough for enterprises to adopt without legal hesitation, compatible with both proprietary and GPL-licensed projects, and one of the best-understood and most-trusted open-source licenses. See [Why GaiaAgent](../../why-gaiaagent.md).
