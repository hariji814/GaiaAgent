"""AURC Codex CLI backend - use the `codex` CLI as the agentic loop engine.
AURC Codex CLI 后端 —— 用 `codex` CLI 作为 agentic loop 引擎

This is the second reference agentic-loop backend (Loop Roadmap Step 2 parity
with the `claude` CLI). Instead of shelling out to `claude -p
--output-format stream-json`, it shells out to ``codex exec --json`` and
consumes its JSON Lines (JSONL) event stream. The adapter shape mirrors
:mod:`gaiaagent.integrations.claude_cli` so the two backends are
interchangeable: both reduce a vendor CLI stream into one
:class:`~gaiaagent.integrations.claude.ClaudeResponse`.

Architecture / 集成架构:

    AURC Runtime Harness (lifecycle, CapABAC, bridges)
    | RUNNING -> hands control to |________________________|
    | codex exec --json --skip-git-repo-check
                                   (-m --sandbox -c mcp_servers.* ...)
                                   --ephemeral
                             | JSONL event stream
                             v
                          run_agentic_loop() -> ClaudeResponse

The CLI executes its own tools natively inside the subprocess. To make those
tool calls enter the AURC bus, point the CLI at an AURC-fronted MCP server via
the ``mcp_servers`` config (see :class:`CodexMCPConfig` / ``mcp_config`` and
:mod:`gaiaagent.mcp.server`); then ``tools/call`` crosses the boundary at the
protocol level through ``MCPBridge`` -> ``MessageRouter``, which is what AURC's
L4 bridges were built for. Passing ``tools`` with in-process Python handlers
still falls back to the built-in loop (see
:meth:`ClaudeLLM.agentic_loop`) - a subprocess cannot call back into the
parent's closures.

Subprocess safety: stdout and stderr are drained concurrently via
``Process.communicate()`` (no pipe-buffer deadlock), with an optional timeout
and a ``try/finally`` that kills the child on timeout/cancel/error (no orphaned
``codex`` process leaking ``CODEX_API_KEY``).

External requirement: the ``codex`` binary on PATH (override with
``CODEX_CLI_PATH`` env var or the ``cli_path`` argument). In automation the key
is supplied via ``CODEX_API_KEY`` (see the official Codex manual; do NOT export
``OPENAI_API_KEY`` as a job-level env var near untrusted code).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from .claude import ClaudeResponse, ClaudeTool, ClaudeToolCall

logger = logging.getLogger(__name__)

# Optional AURC runtime handles - wired when the caller wants the CLI loop to
# leave traces in AURC's observability layer. Imported lazily to avoid a hard
# dependency cycle; types are only used for typing.
try:
    from gaiaagent.core.types import RecoveryAction
    from gaiaagent.observability.tracing import BridgeTraceRecorder, TraceSpan
except ImportError:  # pragma: no cover - observability is part of the core package
    RecoveryAction = None  # type: ignore[assignment]
    BridgeTraceRecorder = None  # type: ignore[assignment]
    TraceSpan = None  # type: ignore[assignment]

# Ceiling on prompt length passed as a CLI *argument*. Windows CreateProcess
# caps the whole command line near 32 KiB; we stay well under and force the
# built-in loop for longer prompts (which should use MCP/stdin instead).
_MAX_PROMPT_ARG_CHARS = 8000

# Default sandbox policy for headless codex runs. ``read-only`` is the safest
# default; callers that need the loop to apply changes pass ``workspace-write``.
DEFAULT_SANDBOX = "read-only"

# Type for the tool-execution seam - kept for the built-in fallback path.
# On the CLI path this is unused (the CLI runs its own tools); bus routing is
# done at the MCP layer via ``mcp_servers``, not by overriding this seam.
ExecuteTool = Callable[[ClaudeTool, dict[str, Any]], Awaitable[Any]]


@dataclass
class CodexMCPConfig:
    """One codex MCP server entry, mirroring the claude ``--mcp-config`` shape.

    Codex configures MCP servers under the ``[mcp_servers.<name>]`` table of
    ``config.toml`` (or via ``-c mcp_servers.<name>.<key>=<val>`` overrides).
    This dataclass captures the stdio-launch shape used by the AURC MCP server
    so the same intent that feeds claude's ``--mcp-config`` can feed codex.
    """

    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None

    def to_config_overrides(self) -> list[str]:
        """Render this server as ``-c mcp_servers.<name>.<key>=<val>`` pairs."""
        prefix = f"mcp_servers.{self.name}"
        overrides = [
            f"{prefix}.command={self.command}",
            f"{prefix}.type=stdio",
        ]
        if self.args:
            # codex config parses a TOML array; repeat the key for each element.
            for a in self.args:
                overrides.append(f"{prefix}.args+={a}")
        if self.env:
            for k, v in self.env.items():
                overrides.append(f"{prefix}.env.{k}={v}")
        return overrides


def cli_available(cli_path: str | None = None) -> bool:
    """Return True if the `codex` CLI is on PATH (or at `cli_path`).

    检查 `codex` CLI 是否在 PATH 中(或在 `cli_path` 指定位置)
    """
    binary = _resolve_binary(cli_path)
    return shutil.which(binary) is not None


def _resolve_binary(cli_path: str | None) -> str:
    return cli_path or os.environ.get("CODEX_CLI_PATH", "") or "codex"


def prompt_too_long(prompt: str) -> bool:
    """True if `prompt` exceeds the safe CLI-argument length (caller should fall back).

    判断 prompt 是否超过安全 CLI 参数长度(调用方应降级)
    """
    return len(prompt) > _MAX_PROMPT_ARG_CHARS


def stop_reason_to_recovery_action(stop_reason: str) -> RecoveryAction | None:
    """Map a CLI/built-in `stop_reason` to an AURC `RecoveryAction` (or None when clean).

    抄 stop_reason 映射为 AURC RecoveryAction(正常完成返回 None)

    Returns ``None`` for a clean completion (``end_turn``) - nothing to recover.
    Used by callers that want to feed CLI-loop outcomes into the AURC harness
    recovery model (``RuntimeHarness.report_error``).
    """
    if RecoveryAction is None:  # pragma: no cover
        return None
    mapping = {
        "end_turn": None,
        "max_turns": RecoveryAction.COMPACT_AND_RETRY,
        "error": RecoveryAction.RETRY_WITH_BACKOFF,
        "tool_use": RecoveryAction.RETRY_ALTERNATIVE,
    }
    return mapping.get(stop_reason, RecoveryAction.ESCALATE)


def _build_argv(  # noqa: PLR0913 - CLI flag assembly, one arg per flag
    *,
    prompt: str,
    model: str | None,
    max_turns: int | None,
    system: str | None,
    cli_path: str | None,
    cli_args: list[str] | None,
    sandbox: str | None,
    working_dir: str | None,
    mcp_config: list[CodexMCPConfig] | None,
    extra_config: list[str] | None,
    output_last_message: str | None,
) -> list[str]:
    """Assemble the `codex exec` headless invocation argv.

    组装 `codex exec` headless 调用的参数列表
    """
    argv: list[str] = [_resolve_binary(cli_path), "exec", "--json", "--skip-git-repo-check"]
    if model:
        argv += ["--model", model]
    if sandbox:
        argv += ["--sandbox", sandbox]
    if working_dir:
        # codex resolves the repo/workspace here; combined with
        # --skip-git-repo-check it works outside a git repo too.
        argv += ["--cd", working_dir]
    if max_turns:
        # codex has no direct max-turns flag; cap via the turn-limit config key.
        argv += ["-c", f"exec.max_turns={int(max_turns)}"]
    if output_last_message:
        argv += ["--output-last-message", output_last_message]
    # codex's one-shot instructions come from AGENTS.md or the prompt; for a
    # headless call we prepend the system guidance to the prompt so the
    # instruction is always present without touching repo files.
    final_prompt = f"{system}\n\n---\n\n{prompt}" if system else prompt
    argv.append(final_prompt)
    for server in mcp_config or []:
        argv += ["-c", *server.to_config_overrides()]
        # An MCP server must be enabled for codex to start it.
        argv += ["-c", f"mcp_servers.{server.name}.enabled=true"]
    for kv in extra_config or []:
        argv += ["-c", kv]
    if cli_args:
        argv += list(cli_args)
    return argv


async def _spawn(argv: list[str], env: dict[str, str], cwd: str | None) -> asyncio.subprocess.Process:
    """Spawn the CLI subprocess. Separated for testability (monkeypatch this).

    启动 CLI 子进程。单独抽出便于测试(monkeypatch)
    """
    # CREATE_NO_WINDOW on Windows avoids a flashing console when spawned from a
    # GUI/no-console parent. On POSIX this attribute is ignored.
    creationflags = 0
    if os.name == "nt":
        creationflags = 0x08000000  # CREATE_NO_WINDOW
    return await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=cwd,
        creationflags=creationflags,
    )


def _kill(proc: asyncio.subprocess.Process) -> None:
    """Best-effort terminate the subprocess so it never leaks as an orphan.

    尽力终止子进程,避免成为孤儿进程
    """
    try:
        proc.kill()
    except ProcessLookupError:
        pass
    except OSError as exc:  # pragma: no cover - platform edge
        logger.warning("failed to kill codex subprocess: %s", exc)


async def _communicate(
    proc: asyncio.subprocess.Process, timeout: float | None
) -> tuple[bytes, bytes]:
    """Concurrently drain stdout+stderr (no deadlock). Applies `timeout` if set.

    并发排空 stdout+stderr(无死锁)。设了 timeout 则应用
    """
    if timeout is None:
        return await proc.communicate()
    return await asyncio.wait_for(proc.communicate(), timeout=timeout)


def _normalize_usage(usage: Any) -> dict[str, Any]:
    """Pass codex usage fields through; keep Claude-shaped keys for compatibility."""
    if not isinstance(usage, dict):
        return {}
    out: dict[str, Any] = dict(usage)
    # Map codex names onto the Claude-shaped fields the rest of AURC reads,
    # while preserving the originals for observability.
    out.setdefault("input_tokens", out.get("input_tokens"))
    out.setdefault("output_tokens", out.get("output_tokens"))
    return out


def _parse_event_stream(  # noqa: PLR0912, C901 - defensive parsing of a streaming schema
    events: list[Any],
) -> tuple[list[str], list[ClaudeToolCall], dict[str, Any], str, bool]:
    """Reduce parsed codex JSONL events.

    Returns ``(texts, tool_calls, usage, stop_reason, result_seen)``.
    ``result_seen`` is True iff a terminal ``turn.completed`` event was
    observed - callers use it to distinguish a genuinely empty answer from a
    broken/empty stream.

    Codex event types (from the official manual):
        thread.started, turn.started, item.started, item.completed,
        turn.completed, turn.failed, error.
    Item types include: agent_message, reasoning, command_execution,
    file_change, mcp_tool_call, web_search, plan_update.
    """
    text_parts: list[str] = []
    tool_calls: list[ClaudeToolCall] = []
    usage: dict[str, Any] = {}
    stop_reason: str = "end_turn"
    result_seen = False
    failed = False

    for evt in events:
        if not isinstance(evt, dict):
            continue
        etype = evt.get("type")
        if etype in ("item.started", "item.completed"):
            item = evt.get("item") or {}
            if not isinstance(item, dict):
                continue
            itype = item.get("type")
            if itype == "agent_message":
                txt = item.get("text", "") or ""
                if txt and etype == "item.completed":
                    text_parts.append(txt)
            elif itype in ("command_execution", "shell_call"):
                # A command the model decided to run; surface as a tool call so
                # AURC observability sees the loop's actions.
                tool_calls.append(
                    ClaudeToolCall(
                        tool_name=item.get("name") or "shell",
                        tool_input={"command": item.get("command", "")},
                        tool_use_id=item.get("id", ""),
                    )
                )
            elif itype in ("mcp_tool_call", "function_call"):
                # MCP tool calls already crossed the bus via the AURC MCP
                # server; we still record them for trace completeness.
                name = item.get("name") or item.get("tool") or ""
                raw_args = item.get("arguments") or item.get("input") or {}
                tool_calls.append(
                    ClaudeToolCall(
                        tool_name=name,
                        tool_input=raw_args if isinstance(raw_args, dict) else {"input": raw_args},
                        tool_use_id=item.get("id", ""),
                    )
                )
        elif etype == "turn.completed":
            result_seen = True
            u = evt.get("usage")
            if isinstance(u, dict):
                usage = _normalize_usage(u)
        elif etype == "turn.failed":
            failed = True
        elif etype == "error":
            failed = True

    # Precedence: an explicit failure overrides a clean turn; a clean
    # turn.completed -> end_turn. A stream with no terminal event but with
    # agent text is also treated as a clean completion.
    if failed:
        stop_reason = "error"
    elif result_seen:
        stop_reason = "end_turn"
    elif text_parts:
        stop_reason = "end_turn"
    else:
        stop_reason = "end_turn"
    return text_parts, tool_calls, usage, stop_reason, result_seen


def _record_trace(
    trace_recorder: Any,
    *,
    agent_id: str | None,
    correlation_id: str | None,
    usage: dict[str, Any],
    stop_reason: str,
) -> None:
    """Record a synthetic trace span for the CLI loop run, keyed by correlation_id.

    按 correlation_id 为 CLI loop 运行记录一条合成 trace span
    """
    if trace_recorder is None or TraceSpan is None:
        return
    try:
        span = TraceSpan(
            correlation_id=correlation_id,
            message_id=f"codex-cli-{uuid.uuid4().hex[:12]}",
            source=agent_id or "codex-cli",
            target="codex-cli",
            type="cli_loop",
            origin_protocol="codex-cli",
            bridge_chain=["codex-cli->aurc"],
            hop_count=1,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        trace_recorder.record_span(span)
    except Exception as exc:  # pragma: no cover - observability must never break the loop
        logger.debug("trace recording failed: %s", exc)


async def run_agentic_loop(  # noqa: PLR0913 - one kw per CLI concern
    *,
    prompt: str,
    tools: list[ClaudeTool] | None,
    max_turns: int,
    system: str | None,
    model: str | None,
    api_key: str | None,
    max_tokens: int | None,  # noqa: ARG001 - parity with ClaudeLLM; the CLI manages its own budget
    execute_tool: ExecuteTool | None,  # noqa: ARG001 - unused on CLI path; bus routing is via mcp_servers
    cli_path: str | None = None,
    cli_args: list[str] | None = None,
    sandbox: str | None = None,
    working_dir: str | None = None,
    mcp_config: list[CodexMCPConfig] | None = None,
    extra_config: list[str] | None = None,
    output_last_message: str | None = None,
    timeout: float | None = None,
    trace_recorder: Any = None,
    agent_id: str | None = None,
    correlation_id: str | None = None,
) -> ClaudeResponse:
    """Run the `codex exec --json` headless loop and aggregate its stream into a ClaudeResponse.

    运行 `codex exec --json` headless 循环,把流聚合为 ClaudeResponse

    The CLI runs its own tools natively; to route those calls through the AURC
    bus, pass ``mcp_config`` pointing at an AURC MCP server (see
    :mod:`gaiaagent.mcp.server`). ``execute_tool`` is accepted for API parity
    but is not invoked on this path.
    """
    argv = _build_argv(
        prompt=prompt,
        model=model,
        max_turns=max_turns,
        system=system,
        cli_path=cli_path,
        cli_args=cli_args,
        sandbox=sandbox,
        working_dir=working_dir,
        mcp_config=mcp_config,
        extra_config=extra_config,
        output_last_message=output_last_message,
    )
    env = dict(os.environ)
    if api_key:
        env["CODEX_API_KEY"] = api_key

    logger.info("codex CLI backend spawning: %s", argv[0])
    proc = await _spawn(argv, env, working_dir)
    try:
        stdout_bytes, stderr_bytes = await _communicate(proc, timeout)
    except asyncio.TimeoutError:
        _kill(proc)
        return ClaudeResponse(text="[codex CLI timed out]", stop_reason="error")
    except asyncio.CancelledError:
        _kill(proc)
        raise
    except Exception:
        _kill(proc)
        raise

    returncode = proc.returncode
    stderr_text = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""

    if returncode not in (0, None):
        logger.error("codex CLI exited %s: %s", returncode, stderr_text)
        return ClaudeResponse(
            text=f"[codex CLI exited {returncode}: {stderr_text.strip()}]",
            stop_reason="error",
        )

    events: list[Any] = []
    for line in stdout_bytes.decode("utf-8", errors="replace").splitlines() if stdout_bytes else []:
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            logger.debug("codex CLI: non-JSON stream line skipped: %r", line)

    if not events:
        # No parseable events + exit 0 = silent failure (wrong output format,
        # CLI banner, schema drift). Do NOT mask it as a successful empty turn.
        return ClaudeResponse(
            text=f"[codex CLI produced no JSONL events: {stderr_text.strip()}]",
            stop_reason="error",
        )

    text_parts, tool_calls, usage, stop_reason, result_seen = _parse_event_stream(events)
    final_text = "\n".join(t for t in text_parts if t)

    _record_trace(
        trace_recorder,
        agent_id=agent_id,
        correlation_id=correlation_id,
        usage=usage,
        stop_reason=stop_reason,
    )

    return ClaudeResponse(
        text=final_text,
        tool_calls=tool_calls,
        stop_reason=stop_reason,
        usage=usage,
        raw_response={"result_seen": result_seen, "backend": "codex-cli"},
    )
