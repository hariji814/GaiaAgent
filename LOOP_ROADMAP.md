# Loop Roadmap — GaiaAgent × CLI Agentic Loops

> 🌐 [中文版](LOOP_ROADMAP.zh.md)
> **[← Back to README](README.md)** | [Roadmap](ROADMAP.md) | [Protocol Spec](PROTOCOL.md)
>
> Guidance document for using the **Claude Code CLI** (`claude`) — the reference agentic loop — as the inner execution engine inside the AURC runtime. No Python SDK dependency; the CLI everyone already has is the engine.

---

## Status

| | |
|:---|:---|
| **Current state** | ✅ **Shipped.** `ClaudeLLM.agentic_loop` delegates to the `claude` CLI (`claude -p --output-format stream-json`) when on PATH, with a safe subprocess wrapper (concurrent stdout/stderr drain, timeout, kill-on-cancel) and defensive stream-json parsing. Falls back to the built-in `anthropic`-based loop otherwise. ✅ **MCP server shipped** (`gaiaagent.mcp.server`) — exposes AURC `@skill` agents as MCP tools so CLI tool calls enter the bus at the protocol level. ✅ **Step 3 governance wiring shipped**: lifecycle integration (`RuntimeHarness.run_with_lifecycle` drives the loop through the 9-state state machine with error recovery/retry), CapABAC gating (`AURCMCPStdioServer` authorizes `tools/call` via `AuthorizationEngine` before routing), OTel trace export (`OTelSpanExporter` maps `TraceSpan` → OpenTelemetry spans with graceful degradation), and `LoopBackend` Protocol (formal contract for CLI backends). 352 tests passing. The `codex` CLI (`codex exec --json`) is now a second reference backend via the same adapter shape; the `backend` parameter (`claude` / `codex` / `auto`) makes the pluggable seam real, not aspirational. |
| **Honest assessment** | The README claim "Claude-native" is now substantive for the *loop delegation*, *MCP exposure* of skills, and the *governance layer* around the loop. **Now wired**: the `backend` parameter on `ClaudeLLM` makes the pluggable loop seam real — `claude` and `codex` CLI backends are interchangeable, `auto` picks the first on PATH. `RuntimeHarness.run_with_lifecycle` drives the CLI loop through the full 9-state lifecycle (start → RUNNING → complete or report_error → recovery → retry), and `ClaudeLLM.run_managed_loop` is the end-to-end integration point. CapABAC `AuthorizationEngine` gates `tools/call` inside the MCP server. `OTelSpanExporter` exports `TraceSpan`s to OpenTelemetry (graceful no-op when OTel absent). `LoopBackend` Protocol formalizes the backend contract. **Not yet wired**: session/resume tied to `ContextStore`, CLI-native tools as AURC skills (reverse direction of Step 1). The concept-mapping table marks each row's status. |
| **Dependency status** | **No new Python dependency.** The `claude` and `codex` CLIs are external runtime requirements, detected on PATH at runtime. `pyproject.toml`'s `claude` extra keeps `anthropic>=0.40` for the fallback path. |

> This is a **living** document; status reflects the code at HEAD. The CLI's `stream-json` event schema is parsed defensively (`.get()` throughout, `isinstance` guards, empty-stream → error not silent success).

---

## Why

2025–2026 produced the **agentic loop** as the canonical execution pattern: a model autonomously decides "which tool next," executes it, feeds the result back, and continues until done. The **Claude Code CLI** is the production-grade, reference incarnation of that loop — the same engine this project's users already run — with streaming, extended thinking, subagents, hooks, permission modes, and native MCP support.

GaiaAgent/AURC is a **different layer**: it does not decide "which tool next" — it manages agent identity, lifecycle, cross-protocol bridging (MCP/A2A/ACP), security/delegation, and orchestration. None of those exist inside the loop.

These two are **complementary, not competing**:

| | Responsibility | Layer |
|:---|:---|:---|
| **Claude Code CLI agentic loop** | The inner "what tool next" execution loop for one agent | Inner / execution engine |
| **GaiaAgent / AURC** | Identity, lifecycle, cross-protocol bridges, security, orchestration around that loop | Outer / runtime & protocol |

The combination: **the AURC runtime wraps the CLI loop**. Inside the `RUNNING` state, `claude -p` drives reasoning; the CLI's tool calls (native or via `--mcp-config`) flow through AURC's MCPBridge → MessageRouter → skills, with delegation chains, CapABAC authorization, and audit logging applied automatically, without the loop knowing protocols exist.

---

## Architecture: Outer AURC, Inner CLI Loop

```
AURC Runtime Harness (9-state lifecycle, CapABAC, bridges, audit)
│  RUNNING state hands control to ──┐
└──────────────────────────────────►│
                                    ▼
              claude -p "<prompt>" --output-format stream-json   ← reference loop
              (--model --max-turns --system-prompt --permission-mode
               --allowed-tools --mcp-config …)
                         │  NDJSON event stream
                         ▼
              claude_cli.py adapter parses events → ClaudeResponse
                         │
              tool_use events ──► _execute_tool()   ← single seam (Step 3 overrides)
                         │
              ┌──────────┴──────────┐          ┌──────────────────────┐
              ▼                     ▼          │  AURC message bus     │
         native CLI tools      AURCMessage ◄───┤  MessageRouter.route  │
         (Read/Bash/…, or      method=invoke   │  mcp:/a2a:/acp: prefix│
         via --mcp-config)     target=mcp:...  │  → bridge forwarder   │
                                              └──────────────────────┘
                         │
              correlation_id + bridge_chain + delegation_chain propagate
```

---

## Concept Mapping — Claude Code CLI → AURC

This is the *target* design contract. The **Status** column says what is wired today
vs. planned — see the honesty note above. Only the skill→tool and `--mcp-config`
rows are implemented; the rest are Step 3+ work.

| Claude Code CLI | AURC counterpart | How they combine | Status |
|:---|:---|:---|:---:|
| `--resume <session>` / session ID | 4-scope `ContextStore` | CLI session id stored in AURC session scope; cross-protocol agents resume the same loop. | 🔜 |
| subagents (`.claude/agents`) | AURC delegation hop | Spawning a CLI subagent = one delegation hop; CapABAC enforces scopes only narrow. | 🔜 |
| `--permission-mode` | CapABAC `AuthorizationEngine.authorize` | Permission mode maps to a CapABAC policy; denied tool → `is_error` fed back. `AURCMCPStdioServer` now gates `tools/call` via `authz_engine`. | ✅ |
| hooks (`settings.json` Pre/PostToolUse) | state-change listeners + HITL gate | CLI hooks bridge to AURC HITL, audit, metrics. | 🔜 |
| `--output-format json` + schema | `SkillDeclaration.output_schema` | CLI structured output aligns with AURC skill return schema. | 🔜 |
| `--allowed-tools` / native tools | `ClaudeTool` ← `@skill` methods | `ClaudeTool.from_aurc_skill` exposes AURC skills as tool defs; `--allowed-tools` is plumbed end-to-end. | ✅ |
| `--mcp-config` | L4 MCP Bridge + `gaiaagent.mcp.server` | Point the CLI at an AURC MCP server; `tools/call` enters the bus via `MCPBridge` → `MessageRouter`. | ✅ |

---

## Verified Seam Points in the Codebase

These were confirmed by reading the code (not assumed). They are the attachment points for the integration:

- **The loop being replaced**: `ClaudeLLM.agentic_loop` — `src/gaiaagent/integrations/claude.py:258-352`.
- **The single "execute tool by name" site**: `tool_map.get(block.name)` → `await tool.handler(**block.input)` — `claude.py:286-316`. This becomes `_execute_tool()`.
- **Skill→tool conversion**: `ClaudeTool.from_aurc_skill` reads `SkillDeclaration.skill_id/.description/.name/.input_schema.properties/.input_schema.required` — `claude.py:99-114`; `SkillDeclaration` defined at `src/gaiaagent/core/identity.py:122-132`.
- **Agent tool exposure**: `ClaudeAgent.get_claude_tools()` — `claude.py:475-487` (iterates `aurc_descriptor.capabilities.provides`).
- **Bus routing by protocol prefix**: `MessageRouter.route` — `src/gaiaagent/bus/router.py:128`; `mcp:`/`a2a:`/`acp:` targets trigger `bridge_forwarder` at `router.py:166-175`; direct targets hit registered handlers at `router.py:152-163`.
- **Per-call authorization**: `AuthorizationEngine.authorize(agent_id, resource_type, action, attributes) -> AuthzResult` — `src/gaiaagent/security/authz.py:194`.
- **Delegation hop recording**: `DelegationBuilder.add_hop(from_agent, to_agent, scopes)` then attach `build()` to `message.security.delegation_chain` — `src/gaiaagent/security/delegation.py:189-194`.
- **Context store API**: `ContextStore.save/load/delete/list_keys/clear_scope` with `ContextScope` enum — `src/gaiaagent/harness/context.py:58-249`.
- **Lifecycle**: `RuntimeHarness.start` moves `READY → RUNNING` and returns — `src/gaiaagent/harness/lifecycle.py:274-299`. The harness does **not** dispatch skill calls itself; skill execution is driven by the workflow layer or the loop.

---

## Three-Step Roadmap

Steps 1 and 2 are shipped. Step 3 (the remaining governance wiring) is reframed:
the original "override `_execute_tool` to route via the bus" plan was **dropped**
— that seam is dead on the CLI path (the subprocess runs its own tools). Bus
routing on the CLI path is done at the MCP layer (Step 1), not by overriding
`_execute_tool`. Step 3 is now the *remaining* AURC-governance wiring around the
loop.

### Step 1 — AURC MCP Server (bus routing)  ✅

Expose AURC `@skill` agents as MCP tools the `claude` CLI calls via `--mcp-config`.
Implemented as `gaiaagent.mcp.server.AURCMCPStdioServer` (stdio JSON-RPC):
`tools/list` enumerates `aurc_descriptor.capabilities.provides`; `tools/call`
goes through `MCPBridge.translate_to_aurc` (mints `correlation_id` +
`bridge_chain`) → `MessageRouter.route` → the skill. Run with
`python -m gaiaagent.mcp --agent myproj:Agent`. The subprocess boundary becomes
irrelevant — the bus crossing is protocol-level, which is what AURC's L4 bridges
were built for.

The reverse direction (CLI-native tools as AURC skills for non-Claude agents) is
still 🔜.

**Acceptance (met):** the CLI, launched with `--mcp-config` pointing at an AURC
MCP server, calls an AURC `@skill` and receives its result; `correlation_id` +
`bridge_chain` are set by the bridge and recorded by `BridgeTraceRecorder`.
Covered by `tests/test_mcp_server.py`.

### Step 2 — CLI as the Loop Engine  ✅

`ClaudeLLM.agentic_loop` delegates to `claude -p … --output-format stream-json`
when the CLI is on PATH and no caller-supplied Python tool handlers need to run
in-process; otherwise falls back to the built-in loop. Public API unchanged.
Subprocess safety: `communicate()` (concurrent drain, no deadlock), optional
`timeout`, `try/finally` kill on timeout/cancel (no orphaned `claude` with a
leaked `ANTHROPIC_API_KEY`). Defensive parsing: empty stream → `stop_reason="error"`
(not silent success), `isinstance` guards, correct `stop_reason` precedence.
`stop_reason → RecoveryAction` mapping + optional `usage → BridgeTraceRecorder`
tracing wired. Covered by `tests/test_claude_integration.py::TestClaudeCLIBackend`.

**Codex CLI backend (parity):** `gaiaagent.integrations.codex_cli` mirrors the
claude adapter shape — same `run_agentic_loop` signature, same
`ClaudeResponse` output, same `cli_available` / `prompt_too_long` /
`stop_reason_to_recovery_action` helpers. Instead of `claude -p
--output-format stream-json` it shells out to `codex exec --json
--skip-git-repo-check` and consumes the JSONL event stream
(`thread.started`, `turn.started`, `item.started`/`item.completed` with types
`agent_message`/`command_execution`/`mcp_tool_call`, `turn.completed` with
`usage`, `turn.failed`, `error`). MCP servers are configured via
`-c mcp_servers.<name>.<key>=<val>` overrides (see `CodexMCPConfig`); auth is
`CODEX_API_KEY`; sandbox is `--sandbox read-only|workspace-write|danger-full-access`.
The AURC MCP server (`gaiaagent.mcp.server`) works with both CLIs identically.
Covered by `tests/test_codex_integration.py` (23 tests).

### Step 3 — AURC Governance Around the Loop  ✅

The loop delegates and routes tool calls at the protocol layer (Steps 1 & 2).
Step 3 wires the AURC runtime *around* the loop — the governance that makes
the CLI path a first-class AURC citizen, not just a subprocess:

- **Lifecycle** ✅: `RuntimeHarness.run_with_lifecycle(agent_id, loop,
  get_stop_reason=...)` drives the CLI loop through the full 9-state
  lifecycle — `start()` → RUNNING, run the loop, then `complete()` on a
  clean stop or `report_error()` → RECOVERING → READY → retry on an error
  `stop_reason`. The retry loop re-checks the result so recovered attempts
  also get `complete()` or further recovery. `ClaudeLLM.run_managed_loop()`
  is the end-to-end integration point: it calls the active backend's
  `stop_reason_to_recovery_action` to extract the stop_reason, then delegates
  to `run_with_lifecycle`. Covered by `tests/test_lifecycle_loop.py` (9 tests).
- **CapABAC gating** ✅: `AURCMCPStdioServer.__init__` accepts an optional
  `authz_engine` and `authz_caller_id`. In `_handle_tools_call`, every tool
  call is authorized via `AuthorizationEngine.authorize(caller, tool_name,
  "call", arguments)` *before* routing through the bus. Denied calls return
  an `isError` result without invoking the skill. When `authz_engine` is
  `None` (the default), all calls pass through — fully backward compatible.
  Covered by `tests/test_mcp_authz.py` (6 tests).
- **OTel trace export** ✅: `OTelSpanExporter` (in `observability/otel.py`)
  maps recorded `TraceSpan`s onto OpenTelemetry trace spans with stable
  attribute names (`aurc.correlation_id`, `aurc.bridge_chain`, …). When
  `opentelemetry` is not installed, `export()` is a no-op that logs at DEBUG
  — the exporter is safe to wire unconditionally. Covered by
  `tests/test_otel_exporter.py` (7 tests, 1 skipped when OTel absent).
- **LoopBackend Protocol** ✅: `integrations/base.py` formalizes the CLI
  backend contract as a `@runtime_checkable` `LoopBackend` Protocol
  (`cli_available`, `prompt_too_long`, `stop_reason_to_recovery_action`,
  `run_agentic_loop`). Both `claude_cli` and `codex_cli` satisfy it.
  Covered by `tests/test_loop_backend.py` (9 tests).
- **Session/resume** 🔜: `--resume` is not yet emitted and the CLI session id
  is not persisted in `ContextStore` session scope.
- **CLI-native tools as AURC skills** 🔜 (the reverse direction of Step 1).

**Note:** the original "override `_execute_tool` to route via the bus" plan is
**dropped** — that seam only exists on the fallback path; on the CLI path bus
routing is the MCP server's job (Step 1, done).

### Wiring it together (end-to-end)

```bash
# 1. Run an AURC agent as an MCP server (the CLI calls into it):
python -m gaiaagent.mcp --agent myproj:ResearchAgent &

# 2. Point the CLI at it and run the loop:
claude -p "Research AI agent protocols" \
  --output-format stream-json \
  --mcp-config '{"mcpServers":{"aurc":{"command":"python","args":["-m","gaiaagent.mcp","--agent","myproj:ResearchAgent"]}}}'
```

Or from Python (delegation + MCP wiring in one call):

```python
from gaiaagent.integrations.claude import ClaudeLLM
llm = ClaudeLLM(
    mcp_config='{"mcpServers":{"aurc":{"command":"python","args":["-m","gaiaagent.mcp","--agent","myproj:ResearchAgent"]}}}',
    trace_recorder=recorder, agent_id="aurc:myproj/researcher:v1.0",
)
resp = await llm.agentic_loop(prompt="Research AI agent protocols", correlation_id="req-1")
```

Or with the `codex` CLI backend (OpenAI Codex):

```python
from gaiaagent.integrations.claude import ClaudeLLM
from gaiaagent.integrations.codex_cli import CodexMCPConfig

llm = ClaudeLLM(
    model="gpt-5",
    api_key=os.environ["CODEX_API_KEY"],
    backend="codex",
    codex_sandbox="read-only",
    codex_mcp_config=[CodexMCPConfig(
        name="aurc",
        command="python",
        args=["-m", "gaiaagent.mcp", "--agent", "myproj:ResearchAgent"],
    )],
    trace_recorder=recorder,
    agent_id="aurc:myproj/researcher:v1.0",
)
resp = await llm.agentic_loop(prompt="Research AI agent protocols", correlation_id="req-1")
```

Or let AURC auto-select the first available CLI:

```python
llm = ClaudeLLM(backend="auto")  # prefers codex, then claude, then built-in
```

---

## Out of Scope (for now)

| Non-Goal | Reason |
|:---|:---|
| ❌ Rewrite `ask()` / `converse()` to delegate | Limit blast radius; they can adopt the same pattern later. |
| ❌ Public streaming API (`agentic_loop_stream`) | No async-generator precedent in the codebase today; the CLI stream is consumed internally to produce one `ClaudeResponse`. Streaming exposure is a separate, opt-in change. |
| ❌ Modify `MessageRouter` / bridges / harness / security code | Step 3 only *uses* them via the `_execute_tool` seam, it does not alter them. |
| ❌ Vendor-lock to Claude | **Addressed**: the `backend` parameter (`claude` / `codex` / `auto`) makes the pluggable seam real. The `codex` CLI backend is a second reference; additional backends mirror the same adapter. |
| ❌ Add a Python SDK dependency | The `claude` CLI is the engine; no `claude-agent-sdk` pip dep is introduced. |

---

## Risks & Mitigations

| Risk | Mitigation |
|:---|:---|
| **CLI `stream-json` schema drift** (event/field names change across versions) | Adapter parses defensively (`.get()` everywhere, tolerate missing fields); a captured trace pins the schema at implementation time; fallback loop covers CLI absence. |
| **Caller-supplied Python tool handlers can't be called by a subprocess CLI** | Step 2 falls back to the hand-rolled loop when `tools` with handlers are passed; exposing handlers to the CLI is exactly Step 1's MCP bridge. |
| **Tests hit the network / need a login** | All tests monkeypatch the subprocess; the real-CLI smoke test is a separate manual script, not in CI. |
| **Backward-compat break** | Signature and private attrs (`_model`, `_api_key`, `_max_tokens`, `_system_prompt`, `_conversation_history`) preserved; existing `tests/test_claude_integration.py` is the regression net; `main.py` does not use Claude. |

---

## How to Influence

- **Claim a step** — comment in [Discussions](https://github.com/gaiaagent/gaiaagent/discussions) to take Step 1 or Step 3.
- **Propose a mapping** — if a CLI concept has no AURC counterpart yet, open an issue labeled `loop-integration`.
- **Port to another loop backend** — **demonstrated**: `codex_cli.py` mirrors `claude_cli.py` and is wired via the `backend` parameter. Additional backends follow the same pattern.

---

*This is a living guidance document. Edits welcome via PR — label it `loop-roadmap` so we can discuss scope before committing.*
