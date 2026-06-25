"""Manual smoke test: drive a real agentic loop via the `claude` CLI backend.
人工冒烟:通过 `claude` CLI 后端驱动一次真实的 agentic loop。

This is a *manual* verification script — it does NOT run in CI. It requires:
    - The `claude` CLI on PATH (Claude Code), logged in or with ANTHROPIC_API_KEY set.
Run:
    python examples/cli_loop_demo.py

What it verifies (Loop Roadmap Step 2 acceptance):
    - ClaudeLLM.agentic_loop delegates to `claude -p --output-format stream-json`.
    - The streamed events are aggregated into a ClaudeResponse (text + tool_calls).
    - When the CLI is absent, it falls back to the built-in loop.
"""

from __future__ import annotations

import asyncio
import logging

from gaiaagent.integrations.claude import ClaudeLLM
from gaiaagent.integrations.claude_cli import cli_available

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


async def main() -> None:
    llm = ClaudeLLM(model="claude-sonnet-4-20250514")
    print(f"claude CLI on PATH: {cli_available(llm._cli_path)}")
    print("Backend:", "claude CLI" if cli_available(llm._cli_path) else "built-in fallback")
    print("-" * 60)

    # No tools → CLI backend runs Claude's native tools (Read/Bash/WebSearch/…).
    # With the CLI, this is a real multi-turn loop executed by `claude -p`.
    response = await llm.agentic_loop(
        prompt="In one sentence, what is the AURC protocol? Then name one of its bridges.",
        max_turns=4,
    )
    print("stop_reason:", response.stop_reason)
    print("usage:", response.usage)
    print("tool_calls:", [tc.tool_name for tc in response.tool_calls])
    print("text:", response.text)


if __name__ == "__main__":
    asyncio.run(main())
