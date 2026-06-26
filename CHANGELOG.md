# Changelog

All notable changes to GaiaAgent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- `gaiaagent demo` subcommand: zero-config, 3-agent cross-protocol demo
  with live dashboard and auto-browser. No API key required.
- Real message routing wired into `gaiaagent serve` (MessageRouter +
  RuntimeHarness + DashboardAPI).
- Dashboard ASGI mounting on HTTP transport server.
- Community files: SECURITY.md, GOVERNANCE.md, ADOPTERS.md, CHANGELOG.md.
- Apache-2.0 license (migrated from AGPL-3.0).

### Fixed
- Lifecycle: `_on_transition` listener now fires on every state transition.
- Lifecycle: `wait_if_paused()` makes pause/resume genuinely blocking.
- Lifecycle: `restart()` uses `reset_to_ready()` instead of bypassing the
  state machine.
- Orchestrator: `OrchestratorWorkers.execute` now runs subtasks in parallel
  via `asyncio.gather` instead of serial loop.
- Router: TTL is now decremented per hop (was checked but never decremented).
- Router: Dead-letter queue uses `deque` with `popleft()` for O(1) eviction.
- Router: Broadcast routing uses `asyncio.gather` for concurrent delivery.

## [0.1.0] - 2025-01-15

### Added
- AURC protocol v0.1 specification (PROTOCOL.md)
- 3 protocol bridges: MCP, A2A, ACP
- 9-state agent lifecycle state machine
- 5 workflow orchestration patterns
- CapABAC security model with delegation chains
- Health dashboard with Prometheus metrics export
- CLI tool (`aurc` command) with serve/validate/bridge/registry subcommands
- Claude CLI integration for agentic loops
- 352 passing tests
