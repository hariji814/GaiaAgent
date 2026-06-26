# GaiaAgent: The Missing Protocol Layer for AI Agents

> MCP, A2A, ACP each solved part of the puzzle. None of them let agents
> *across* frameworks talk to each other - and none managed agent
> lifecycle. GaiaAgent (AURC) is the layer that fixes both, and you can
> try it in 60 seconds.

*Posted 2026-06-26. AURC v0.1.0, Apache-2.0.*

## The 60-second pitch

```bash
pip install "gaiaagent[http]"
gaiaagent demo
```

No API key. No config. No external services. The demo spins up three
agents (a researcher, an analyst, a writer), runs a chained workflow
across MCP -> A2A -> ACP protocol boundaries, and opens a live health
dashboard in your browser. If you want real intelligence instead of
stubs, add one flag:

```bash
gaiaagent demo --api-key sk-xxxx   # OpenAI or Anthropic
```

That is the whole "is it real?" test - and it passes.

## Why this layer has to exist

Every week brings a new agent framework. They are not short on
cleverness; they are short on **interoperability**. The three
protocol-style efforts that matter today - MCP (tool calling), A2A
(agent-to-agent), ACP (async task dispatch) - each own a piece of the
problem and politely ignore the rest:

| Protocol        | Tool calling | Agent-to-agent | Lifecycle | Cross-protocol |
|-----------------|:---:|:---:|:---:|:---:|
| MCP             | yes | no  | no  | no  |
| A2A             | no  | yes | no  | no  |
| ACP             | partial | partial | no | no  |
| **AURC**        | **yes** | **yes** | **yes** | **yes** |

Build an agent for MCP and it cannot delegate to an A2A agent. Build for
A2A and you cannot call MCP tools. And not one of them can pause,
resume, recover, or gracefully shut an agent down. That last gap is the
telling one: a protocol that cannot manage lifecycle is a *communication*
protocol, not a *runtime* protocol. Agents that run in production need a
runtime.

AURC is that runtime layer. It sits above all three, translates their
messages into one canonical `AURCMessage`, and adds the parts they
collectively lack.

## What you actually get

1. **A 9-state lifecycle state machine.** REGISTERING -> READY ->
   RUNNING -> PAUSED -> COMPLETED / FAILED / STOPPED, with a RECOVERING
   transition, backoff retry, and graceful shutdown. This is the core
   innovation - the thing that makes AURC a runtime, not just a wire
   format.

2. **Real, bidirectional protocol bridges.** `MCPBridge`,
   `A2ABridge`, and `ACPBridge` translate to and from the canonical
   message. An MCP agent can delegate to an A2A agent through AURC; an
   A2A agent can invoke an ACP task through AURC. One audit trail spans
   every hop.

3. **Observability built in.** A tamper-evident audit log, a live HTML
   health dashboard, Prometheus `/metrics`, and bridge-chain tracing so
   you can see the full path of a message as it crosses protocols.

4. **Security that respects delegation.** Capability-based access
   control, scope-narrowing delegation chains (the confused-deputy
   problem becomes structurally impossible), and token references in
   messages instead of raw tokens.

## Not a framework war

GaiaAgent is not competing with LangGraph, CrewAI, or AutoGen. It is the
protocol layer that lets an agent from *any* of them interoperate with
agents from the others. The comparison is almost a category error, but
since people ask:

| Feature                              | GaiaAgent (AURC) | LangGraph | CrewAI | AutoGen |
|--------------------------------------|:---:|:---:|:---:|:---:|
| Protocol standard                    | yes (AURC v0.1) | no | no | no |
| Cross-protocol bridging (MCP+A2A+ACP)| yes | no | no | no |
| Agent lifecycle state machine        | 9 states | no | no | no |
| Health monitoring + dashboard        | yes | no | no | no |
| Prometheus metrics                   | yes | no | no | no |
| Audit trail                          | yes | no | no | no |

If you are happy inside one framework, stay there. AURC earns its keep
the moment you need agents from different worlds to collaborate under
one audited, observable runtime.

## From AGPL to Apache-2.0

A protocol is only a standard if people can adopt it. AURC's earliest
draft was AGPL-3.0 - a fine license for an application, but a poor one
for a *protocol* you want the whole ecosystem to depend on. The
copyleft reach-through made legal teams flinch, and a protocol that
makes legal teams flinch does not get adopted.

So we migrated to **Apache-2.0**: permissive, patent-granted, compatible
with both proprietary and GPL-licensed code, and one of the most
understood licenses in the industry. The single biggest barrier to
adoption - "can we legally depend on this?" - is now a non-question.

## Try it, then build on it

```bash
pip install "gaiaagent[http]"
gaiaagent demo                      # zero-config, stub LLM
gaiaagent demo --api-key sk-xxxx    # real LLM
gaiaagent init myproject && cd myproject && python agent.py
```

The full walk-through lives in the
[getting-started guide](../zh/guides/getting-started.md) (also in
[English](../en/guides/getting-started.md)). The technical case - the
problem, the comparison, why Apache-2.0 - is in
[Why GaiaAgent](../why-gaiaagent.md).

AURC is at v0.1.0 (Alpha): the lifecycle machine, the three bridges, the
router, the audit trail, and the dashboard are real and tested, not
stubs. What is intentionally honest is the version number - the protocol
surface will keep moving until the ecosystem tells us where the seams
are. Try the demo, scaffold an agent, and tell us what breaks.

---

*GaiaAgent is Apache-2.0 licensed. Issues and contributions welcome.*
