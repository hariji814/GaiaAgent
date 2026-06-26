# RouterDelegate: correlation propagation + unified denial envelope

## Goal

Two fixes to `RouterDelegate` (`src/gaiaagent/workflows/orchestrator.py`), both verified against the runtime path:

1. **Correlation propagation.** Default `correlation_id=None` leaves every bus-delegated hop uncorrelated in audit (`correlation_id=""`) and tracing (`None`). The patterns should own one correlation id per `execute()` run, shared by all hops, so a chain's audit entries / trace spans group together.
2. **Unified denial envelope.** A hot-path `AuthzDeniedError` (raised by `RouteAuthzGuard`, re-raised by `router.route()`) currently propagates as a generic `Exception` and gets stringified by the pattern. `AURCServer.http_handler` maps it to `{"code":"forbidden","message":exc.reason,"recoverable":False}`. `RouterDelegate.__call__` should do the same mapping → raise `RouterDelegateError`, so both failure modes (denial + `{"error":...}` envelope) surface as one type.

## Design (final decisions)

### Correlation

- Add `contextvars.ContextVar[str | None]` `_workflow_correlation` (default `None`).
- Add `_mint_correlation_id() -> str` → `f"wf-{uuid.uuid4().hex[:12]}"` (mirrors `AURCMessage.message_id`'s `f"msg-{uuid.uuid4().hex[:12]}"` in `core/message.py:261`).
- Add `@contextmanager _workflow_correlation_scope() -> Iterator[str]`: reuses the outer correlation if one is already active (nested patterns inherit), otherwise mints; sets a token, resets in `finally`.
- Each pattern's `execute()` wraps its body in `with _workflow_correlation_scope():`. Sync contextmanager inside async method is fine (no await in setup/teardown). Child tasks from `asyncio.gather`/`create_task` copy the parent context at creation → they see the scope's correlation.
- `RouterDelegate.__call__` resolves `correlation_id = self._correlation_id or _workflow_correlation.get() or _mint_correlation_id()`. Explicit override wins; else active workflow scope; else per-call mint (standalone use, e.g. tests calling `await delegate("x")` directly).

### Denial envelope

- `RouterDelegate.__call__`: wrap `await self._router.route(message)` in `try/except AuthzDeniedError as exc:` → `raise RouterDelegateError({"code":"forbidden","message":exc.reason,"recoverable":False}) from exc`. Matches `server.py:141` exactly (inline string code — matches codebase convention; no shared error-code module exists).
- Import `AuthzDeniedError` from `..security.message_authz` (runtime import; workflows L6 → security L4, no cycle — bus/router already imports the same symbol).

### Constant

- Extract `DEFAULT_ORCH_SOURCE = "aurc:workflow/orchestrator:v1.0"` as a module constant; `RouterDelegate.__init__` default + test reference it. Test currently hardcodes the literal — switch to importing the constant (single source of truth).

## Tests (`tests/test_workflow_bus_delegation.py`)

- `test_promptchain_hops_share_correlation_id`: two-hop chain → both `AUTHZ_GRANTED` entries have the same non-empty `correlation_id`; `audit.get_by_correlation(<that id>)` returns both.
- `test_standalone_delegate_has_non_empty_correlation`: `await delegate("x")` outside any pattern → audit entry has non-empty `correlation_id`.
- `test_nested_pattern_inherits_outer_correlation`: ParallelFanOut step inside a PromptChain → all hops (chain + fan-out) share one correlation id.
- `test_authz_denial_surfaces_as_forbidden_envelope`: delegate with untrusted source, called directly → raises `RouterDelegateError` with `error == {"code":"forbidden","message":...,"recoverable":False}`.

## Out of scope (adjacent debt, call out in summary)

- `server.py` has 5 inline error codes (`forbidden`, `route_error`, `bad_message`, `skill_not_found`, `bad_skill_params`) with no shared constant module. Codebase-wide extraction is a separate cleanup.
- `RouterDelegate` is still the only invoke-message constructor besides bridges; no shared `build_invoke_message` helper exists. Not worth abstracting for 2 call sites.

## Verify

`make lint && make type-check && make test` (the 4 new tests + existing delegation tests must pass).
