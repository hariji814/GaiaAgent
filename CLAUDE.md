# CLAUDE.md

GaiaAgent is the **AURC** (Agent Unified Runtime & Communication) protocol reference implementation — a Python library that bridges AI agent protocols (MCP · A2A · ACP), manages agent lifecycles, enforces CapABAC security across delegation chains, and orchestrates multi-agent workflows. Single PyPI package, Apache-2.0, Python 3.10+.

## Engineering Discipline

- Use best practices and write clean, idiomatic code every time. No shortcuts, no half-measures.
- **Never ship workarounds, patches, or band-aid fixes. Always choose the cleanest, most correct approach — every single time.** When you find a bug, fix it at the root, not at the symptom. If two code paths diverge and one is broken, unify them rather than patching the broken one in place. Surgical-but-duplicative is not "safer" — it is how the bug got there. Surface the tradeoff, then take the clean path.
- Do not override or work around the architecture. Never disable lint rules, add blanket `# noqa` / `# type: ignore`, or bypass CI to force something through. Linting, type-checking, and CI are guardrails that exist for a reason. Fix the cause, not the symptom.
- Match the conventions of the surrounding code. Prefer the existing pattern over inventing a new one.
- **Fail loud — never swallow errors or add silent fallbacks.** No `try: ... except: return None`, no broad `except` that hides the failure, no default value slipped in to make a symptom disappear. A masked error is a bug that resurfaces somewhere worse, later. Let errors propagate to where they can be handled meaningfully; only catch what you can genuinely recover from.
- **No fake, stub, or placeholder implementations.** Don't write code that *looks* done but isn't — hardcoded "sample" responses, mock data left in a real path, `# TODO: implement` stubs that return a fake success, functions that pretend to work. If something genuinely can't be finished now, say so explicitly instead of shipping a hollow shell.

### Verify, Never Assume

This applies to **everything** — coding, debugging, answering questions, deciding what to do next. Not just while writing code. Any claim you make or act on must be grounded in evidence, not assumption.

- **Never make things up.** Do not invent file paths, function names, API signatures, config keys, env vars, library behavior, return shapes, or facts about how the system behaves. If you have not seen it in this codebase or confirmed it from docs, you do not know it — go find it.
- **Reading code is not validation.** This code is intricate — control flow, async timing, middleware, config, env, and cross-protocol interactions mean the static text rarely tells the whole story. Reading tells you what the code *looks like* it does; only **running it** tells you what it *actually* does. To truly confirm behavior, execute it: run the function/endpoint, write a throwaway script, add a log and trigger the path, check the real response. Treat "I read it and it should work" as a hypothesis, not a conclusion.
- **Don't generalize from a small sample.** Seeing one usage does not tell you the pattern; seeing one caller does not tell you all callers. Before changing shared code, find *every* call site, *every* implementation of an interface, and the *actual* runtime path — don't assume the first example is representative.
- **When debugging, prove the root cause before fixing.** Don't assume what's broken from a symptom or a guess — reproduce it, instrument it, observe the actual failure. A fix built on an unverified theory usually just moves the bug.
- **State confidence honestly.** If something is unverified, say so and verify it before relying on it. Never present an assumption as a fact. A confident wrong answer is worse than "let me check."
- **Understand before you change or delete.** Don't modify, refactor, or remove code whose purpose you haven't confirmed (Chesterton's fence) — the weird-looking line is often load-bearing. If you don't know why it's there, find out before touching it.
- **Don't claim done without proof.** Never say "it works," "tests pass," or "this is fixed" unless you actually ran it and saw the result. Report outcomes faithfully — if a step was skipped or something failed, say so with the output. "Done" means verified, not "should be done."
- If after genuine investigation something is still ambiguous, stop and ask — do not paper over the gap with a guess.

### Maintainability & Tech Debt

Optimize for the next engineer who has to read, extend, or debug this code six months from now — not for getting it working today. Code is read far more often than it is written.

- **Debt is not a shipping option.** Every change should leave the area as clean as or cleaner than you found it. The correct thing now; there is no "fix it later."
- **Never use workarounds.** A workaround is debt that hides the real problem, drifts out of sync, and turns one bug into three. Fix the root cause, not the symptom.
- **Never write the same code twice — and "same" means similar, not identical.** There should be **one canonical way to do a thing** in this codebase. Before writing a utility/type/helper, search for one that already does it; if you find a near-equivalent, use or extend it instead of adding a rival.
- **Abstractions are also debt.** Don't abstract single-use code or speculative "flexibility." Abstract only when the third real case appears and the shape is clear.
- **Keep diffs minimal and reviewable.** No drive-by reformatting, no reordering imports the formatter didn't ask for. Every line in the diff should trace to the task.
- **When you spot debt adjacent to your change, surface it.** Fix it if it's in scope and cheap; otherwise call it out explicitly so it's a decision, not an accident.

### Agent Guidelines (Karpathy-inspired)

Bias toward caution over speed; for trivial tasks, use judgment.

1. **Think Before Coding.** Don't assume. Don't hide confusion. Surface tradeoffs. State assumptions explicitly; if uncertain, ask. If multiple interpretations exist, present them, don't pick silently.
2. **Simplicity First.** Minimum code that solves the problem, nothing speculative. No features beyond what was asked. No abstractions for single-use code. If you write 200 lines and it could be 50, rewrite it.
3. **Surgical Changes.** Touch only what you must. Don't "improve" adjacent code, comments, or formatting. Match existing style. Remove imports/variables/functions that YOUR changes made unused. Every changed line should trace directly to the request.
4. **Goal-Driven Execution.** Define success criteria. Loop until verified. Turn vague tasks into verifiable goals before starting. For multi-step tasks, state a brief plan with a verify check per step. Strong success criteria let you loop independently; weak criteria ("make it work") require constant clarification.

## Key Commands

```bash
# Install (editable, all extras)
make install            # pip install -e ".[all]"

# Quality (run after changes — see After Major Changes)
make lint               # ruff check src/ tests/
make format             # ruff format src/ tests/
make type-check         # mypy src/

# Tests
make test               # pytest -v --tb=short
make test-cov           # pytest --cov --cov-report=html

# Run
make serve              # python -m gaiaagent.cli serve --dashboard
make demo               # python main.py

# Pre-commit (local guard — install once: pre-commit install)
pre-commit run --all-files
pre-commit install
```

## Architecture

### Package Layout

```
src/gaiaagent/
  core/          - AURCMessage, identity, capability, types
  bus/           - Router, Codec, Session (message bus)
  transport/     - HTTP / WebSocket transports (stdio, gRPC planned)
  bridges/       - MCP / A2A / ACP protocol bridges + BridgeAuthzGuard
  security/      - CapABAC AuthorizationEngine, delegation, audit, signing
  harness/       - Runtime harness: lifecycle, context, recovery
  workflows/     - 5 orchestration patterns
  registry/      - Agent discovery (local + protocol)
  observability/ - metrics, otel, tracing, dashboard
  integrations/  - Claude / Codex CLI integrations
  mcp/           - Built-in MCP server exposing AURC @skills
  sdk/           - @aurc_agent / @skill decorators
```

### 8-Layer Stack

L0 Transport → L1 Codec → L2 Session → L3 Router → L4 Security → L5 Harness → L6 Workflows → L7 Discovery. Each layer independently testable.

### Routing Hot Path

`MessageRouter.route()` applies: TTL check → authorization (if `set_authorizer` attached) → direct → bridge (`mcp:`/`a2a:`/`acp:`) → group broadcast → wildcard → dead letter. See `src/gaiaagent/bus/router.py`.

### Security Model

CapABAC (Capability + ABAC): default-deny, delegable capabilities that **only narrow, never widen**, constraints evaluated at decision time, Ed25519-signed delegation chains. Two enforcement points share `derive_authz_request`: inbound `BridgeAuthzGuard` (`bridges/authz_guard.py`) and hot-path `RouteAuthzGuard` (`security/message_authz.py`). See `src/gaiaagent/security/CLAUDE.md`.

## Code Style

### Python

- **Ruff** for linting/formatting — not black/flake8/isort. Config in `pyproject.toml` (`E,F,I,N,W,UP`, line-length 100, target py310).
- **mypy strict** — full type annotations required on all functions and methods. No `# type: ignore` to silence; fix the type.
- **No inline imports** — all imports at the top of the file.
- **No blanket `# noqa`** — if a rule fires, either fix the code or narrow the disable with a reason.
- **Bilingual comments** are the existing convention (English + 中文). Match it when editing files that use it; do not strip the Chinese half.

### Monorepo-wide rules

Live in `.claude/rules/general.md` (DRY, dead code, constants, domain org, file size, self-documenting code, cleanup) and load every session.

### Subdomain rules

Nested `CLAUDE.md` files load automatically when you work in that part of the tree:

- **Bridges** (`src/gaiaagent/bridges/CLAUDE.md`) — protocol bridge + BridgeAuthzGuard contract
- **Security** (`src/gaiaagent/security/CLAUDE.md`) — CapABAC, delegation, audit
- **Bus** (`src/gaiaagent/bus/CLAUDE.md`) — Router, Codec, Session, AURC envelope
- **Transport** (`src/gaiaagent/transport/CLAUDE.md`) — HTTP/WS, graceful drain, heartbeat

## Working Style

### Subagents & Parallelism

Always spawn subagents wherever possible — for research, exploration, or independent tasks, use the Agent tool with specialized subagents in parallel. Don't do sequentially what can be done concurrently.

### Deep Exploration

When investigating a bug, feature, or unfamiliar area: never assume the root cause — trace the actual code path. Use the `Explore` subagent for broad discovery; spawn multiple subagents to explore different layers in parallel. Check edge cases, related config, env vars, and cross-protocol interactions.

### Reporting Issues

Only report problems that a real user would actually encounter: functional bugs, wrong data, missing functionality. Do NOT flag theoretical race conditions or contrived microsecond timing scenarios. Prioritize: functional > UX > code quality. Skip hypothetical concerns.

### Task Tracking

Always create todos for multi-step work — use TaskCreate at the start of any non-trivial task. Update status (`in_progress` → `completed`) as you go. Never leave tasks stale.

### Planning

Non-trivial changes: write a plan to `.agents/plans/` (gitignored) first — architecture decisions, step-by-step implementation, edge cases, rollback. A plan is a spec, not a journal — final decisions only, no thought-process commentary.

### Testing

GaiaAgent has ~490 tests. **Run them for changes that touch runtime behavior** (`make test`). A change is not done until `make lint && make type-check && make test` are green.

### After Major Changes

```bash
make lint
make type-check
make test
```

## Git Conventions

- **Conventional commits** — `feat(security): ...`, `fix(bus): ...`, `docs: ...`, `test: ...`, `refactor: ...`. Scope matches the subdomain (`bridges`/`bus`/`security`/`transport`/`harness`/…).
- **`main` is the base branch.** Feature branches from and merge into `main`.
- **Never add Claude as a co-author** in commit messages.
- **Never merge pull requests** — PRs are merged by the team, not by Claude.
- Work is **not complete until `git push` succeeds.**
- Use plain `git merge` for syncing with `origin/main`; do not rebase.

## Encoding Guard

Source files are UTF-8 + LF (enforced by `.gitattributes` + a pre-commit encoding hook). The historical Chinese-comment mojibake (UTF-8 double-encoded as GBK) is being normalized out — never re-introduce non-UTF-8 bytes or CRLF endings. If a commit is rejected by the encoding hook, fix the file's encoding, don't bypass the hook.
