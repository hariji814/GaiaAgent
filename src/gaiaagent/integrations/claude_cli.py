"""AURC Claude Code CLI backend — use the `claude` CLI as the agentic loop engine.
AURC Claude Code CLI 后端 —— 用 `claude` CLI 作为 agentic loop 引擎

Instead of depending on a Python SDK, this module shells out to the
`claude` CLI (Claude Code) in headless mode and consumes its
`stream-json` NDJSON event stream. The CLI is the *reference* agentic
loop: streaming, extended thinking, subagents, hooks, permission modes,
and native MCP support.

Architecture / 集成架构:

    AURC Runtime Harness (lifecycle, CapABAC, bridges)
    │  RUNNING → hands control to ──┐
    └────────────────────────────────► claude -p "<prompt>"
                                        --output-format stream-json
                                        (--model --max-turns --append-system-prompt
                                         --permission-mode --allowed-tools --mcp-config …)
                                   │  NDJSON event stream
                                   ▼
                          run_agentic_loop() → ClaudeResponse

The CLI executes its own tools natively inside the subprocess. To make
those tool calls enter the AURC bus, point the CLI at an AURC-fronted MCP
server via `--mcp-config` (see `gaiaagent.mcp.server`); then `tools/call`
crosses the boundary at the protocol level through `MCPBridge` →
`MessageRouter`, which is what AURC's L4 bridges were built for. Passing
`tools` with in-process Python handlers still falls back to the built-in
loop (see `ClaudeLLM.agentic_loop`) — a subprocess cannot call back into
the parent's closures.

Subprocess safety: stdout and stderr are drained concurrently via
`Process.communicate()` (no pipe-buffer deadlock), with an optional
timeout and a `try/finally` that kills the child on timeout/cancel/error
(no orphaned `claude` process leaking `ANTHROPIC_API_KEY`).

External requirement: the `claude` binary on PATH (override with
`CLAUDE_CLI_PATH` env var or the `cli_path` argument).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from .claude import ClaudeResponse, ClaudeTool, ClaudeToolCall

logger = logging.getLogger(__name__)

# Optional AURC runtime handles — wired when the caller wants the CLI loop
# to leave traces in AURC's observability layer. Imported lazily to avoid a
# hard dependency cycle; types are only used for typing.
try:
    from gaiaagent.core.types import RecoveryAction
    from gaiaagent.observability.tracing import BridgeTraceRecorder, TraceSpan
except ImportError:  # pragma: no cover — observability is part of the core package
    RecoveryAction = None  # type: ignore
    BridgeTraceRecorder = None  # type: ignore
    TraceSpan = None  # type: ignore

# Ceiling on prompt length passed as a CLI *argument*. Windows CreateProcess
# caps the whole command line near 32 KiB; we stay well under and force the
# built-in loop for longer prompts (which should use MCP/stdin instead).
_MAX_PROMPT_ARG_CHARS = 8000

# Type for the tool-execution seam — kept for the built-in fallback path.
# On the CLI path this is unused (the CLI runs its own tools); bus routing is
# done at the MCP layer via `--mcp-config`, not by overriding this seam.
ExecuteTool = Callable[[ClaudeTool, dict[str, Any]], Awaitable[Any]]


def cli_available(cli_path: str | None = None) -> bool:
    """Return True if the `claude` CLI is on PATH (or at `cli_path`).
    检查 `claude` CLI 是否在 PATH 上(或在 `cli_path` 指定位置)
    """
    binary = _resolve_binary(cli_path)
    return shutil.which(binary) is not None


def _resolve_binary(cli_path: str | None) -> str:
    return cli_path or os.environ.get("CLAUDE_CLI_PATH", "") or "claude"


def prompt_too_long(prompt: str) -> bool:
    """True if `prompt` exceeds the safe CLI-argument length (caller should fall back).
    判断 prompt 是否超过安全 CLI 参数长度(调用方应降级)
    """
    return len(prompt) > _MAX_PROMPT_ARG_CHARS


def stop_reason_to_recovery_action(stop_reason: str) -> RecoveryAction | None:
    """Map a CLI/built-in `stop_reason` to an AURC `RecoveryAction` (or None when clean).
    把 stop_reason 映射为 AURC RecoveryAction(正常完成返回 None)

    Returns ``None`` for a clean completion (``end_turn``) — nothing to recover.
    Used by callers that want to feed CLI-loop outcomes into the AURC harness
    recovery model (`RuntimeHarness.report_error`).
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


def _build_argv(  # noqa: PLR0913 — CLI flag assembly, one arg per flag
    *,
    prompt: str,
    model: str | None,
    max_turns: int,
    system: str | None,
    cli_path: str | None,
    cli_args: list[str] | None,
    permission_mode: str | None,
    allowed_tools: list[str] | None,
    mcp_config: str | None,
) -> list[str]:
    """Assemble the `claude` headless invocation argv.
    组装 `claude` headless 调用的参数列表
    """
    argv: list[str] = [_resolve_binary(cli_path), "-p", prompt, "--output-format", "stream-json"]
    if model:
        argv += ["--model", model]
    if max_turns:
        argv += ["--max-turns", str(max_turns)]
    if system:
        # Append (not replace) so we don't strip the CLI's own tool guidance.
        argv += ["--append-system-prompt", system]
    if permission_mode:
        argv += ["--permission-mode", permission_mode]
    if allowed_tools:
        argv += ["--allowed-tools", ",".join(allowed_tools)]
    if mcp_config:
        argv += ["--mcp-config", mcp_config]
    if cli_args:
        argv += list(cli_args)
    return argv


async def _spawn(argv: list[str], env: dict[str, str]) -> asyncio.subprocess.Process:
    """Spawn the CLI subprocess. Separated for testability (monkeypatch this).
    启动 CLI 子进程。单独抽出便于测试 monkeypatch。
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
    except OSError as exc:  # pragma: no cover — platform edge
        logger.warning("failed to kill claude subprocess: %s", exc)


async def _communicate(
    proc: asyncio.subprocess.Process, timeout: float | None
) -> tuple[bytes, bytes]:
    """Concurrently drain stdout+stderr (no deadlock). Applies `timeout` if set.
    并发排空 stdout+stderr(无死锁)。设了 timeout 则应用。
    """
    if timeout is None:
        return await proc.communicate()
    return await asyncio.wait_for(proc.communicate(), timeout=timeout)


def _parse_event_stream(  # noqa: PLR0912, C901 — defensive parsing of a streaming schema
    events: list[Any],
) -> tuple[list[str], list[ClaudeToolCall], dict[str, Any], str, str, bool]:
    """Reduce parsed stream-json events.

    Returns ``(texts, tool_calls, usage, stop_reason, result_text, result_seen)``.
    ``result_seen`` is True iff a terminal ``result`` event was observed — callers
    use it to distinguish a genuinely empty answer from a broken/empty stream.
    """
    text_parts: list[str] = []
    tool_calls: list[ClaudeToolCall] = []
    usage: dict[str, Any] = {}
    assistant_stop_reason: str | None = None
    result_text = ""
    result_seen = False
    result_is_error = False
    result_subtype: str | None = None

    for evt in events:
        if not isinstance(evt, dict):
            continue
        etype = evt.get("type")
        if etype == "assistant":
            msg = evt.get("message") or {}
            if isinstance(msg, dict):
                for block in msg.get("content", []) or []:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    if btype == "text":
                        text_parts.append(block.get("text", ""))
                    elif btype == "tool_use":
                        tool_calls.append(
                            ClaudeToolCall(
                                tool_name=block.get("name", ""),
                                tool_input=block.get("input", {}) or {},
                                tool_use_id=block.get("id", ""),
                            )
                        )
                sr = msg.get("stop_reason")
                if sr:
                    assistant_stop_reason = sr
        elif etype == "result":
            result_seen = True
            result_text = evt.get("result", "") or ""
            u = evt.get("usage")
            if isinstance(u, dict):
                usage = u
            if evt.get("is_error"):
                result_is_error = True
            sub = evt.get("subtype")
            if isinstance(sub, str):
                result_subtype = sub

    # Precedence: a terminal result event overrides assistant stop_reason.
    # max_turns (subtype) wins over generic error; clean result → end_turn.
    if result_subtype == "error_max_turns":
        stop_reason = "max_turns"
    elif result_is_error:
        stop_reason = "error"
    elif result_seen:
        stop_reason = "end_turn"
    elif assistant_stop_reason:
        stop_reason = assistant_stop_reason
    else:
        stop_reason = "end_turn"
    return text_parts, tool_calls, usage, stop_reason, result_text, result_seen


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
            message_id=f"cli-{uuid.uuid4().hex[:12]}",
            source=agent_id or "claude-cli",
            target="claude-cli",
            type="cli_loop",
            origin_protocol="claude-cli",
            bridge_chain=["claude-cli→aurc"],
            hop_count=1,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        trace_recorder.record_span(span)
    except Exception as exc:  # pragma: no cover — observability must never break the loop
        logger.debug("trace recording failed: %s", exc)


async def run_agentic_loop(  # noqa: PLR0913 — one kw per CLI concern
    *,
    prompt: str,
    tools: list[ClaudeTool] | None,
    max_turns: int,
    system: str | None,
    model: str | None,
    api_key: str | None,
    max_tokens: int | None,  # noqa: ARG001 — parity with ClaudeLLM; the CLI manages its own budget
    execute_tool: ExecuteTool | None,  # noqa: ARG001 — unused on CLI path; bus routing is via --mcp-config
    cli_path: str | None = None,
    cli_args: list[str] | None = None,
    permission_mode: str | None = None,
    allowed_tools: list[str] | None = None,
    mcp_config: str | None = None,
    timeout: float | None = None,
    trace_recorder: Any = None,
    agent_id: str | None = None,
    correlation_id: str | None = None,
) -> ClaudeResponse:
    """Run the `claude` CLI headless loop and aggregate its stream into a ClaudeResponse.
    运行 `claude` CLI headless 循环,把流聚合成 ClaudeResponse

    The CLI runs its own tools natively; to route those calls through the AURC
    bus, pass `mcp_config` pointing at an AURC MCP server (see
    `gaiaagent.mcp.server`). `execute_tool` is accepted for API parity but is
    not invoked on this path.
    """
    argv = _build_argv(
        prompt=prompt,
        model=model,
        max_turns=max_turns,
        system=system,
        cli_path=cli_path,
        cli_args=cli_args,
        permission_mode=permission_mode,
        allowed_tools=allowed_tools,
        mcp_config=mcp_config,
    )
    env = dict(os.environ)
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key

    logger.info("claude CLI backend spawning: %s", argv[0])
    proc = await _spawn(argv, env)
    try:
        stdout_bytes, stderr_bytes = await _communicate(proc, timeout)
    except asyncio.TimeoutError:
        _kill(proc)
        return ClaudeResponse(text="[claude CLI timed out]", stop_reason="error")
    except asyncio.CancelledError:
        _kill(proc)
        raise
    except Exception:
        _kill(proc)
        raise

    returncode = proc.returncode
    stderr_text = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""

    if returncode not in (0, None):
        logger.error("claude CLI exited %s: %s", returncode, stderr_text)
        return ClaudeResponse(
            text=f"[claude CLI exited {returncode}: {stderr_text.strip()}]",
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
            logger.debug("claude CLI: non-JSON stream line skipped: %r", line)

    if not events:
        # No parseable events + exit 0 = silent failure (wrong output format,
        # CLI banner, schema drift). Do NOT mask it as a successful empty turn.
        return ClaudeResponse(
            text=f"[claude CLI produced no stream-json events: {stderr_text.strip()}]",
            stop_reason="error",
        )

    parsed = _parse_event_stream(events)
    text_parts, tool_calls, usage, stop_reason, result_text, result_seen = parsed
    final_text = result_text if result_text else "\n".join(t for t in text_parts if t)

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
        raw_response={"result_seen": result_seen},
    )
