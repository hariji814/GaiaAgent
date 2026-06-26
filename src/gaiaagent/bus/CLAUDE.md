# Bus

The AURC message bus: `MessageRouter` (routing), `Codec` (envelope (de)serialization), `Session` (correlation/state).

## Contract (verified against `bus/router.py`, `bus/codec.py`, `bus/session.py`)

- **Routing priority, highest first:** direct (local handler) → bridge (`mcp:`/`a2a:`/`acp:` target) → group broadcast (`aurc:group/...`) → wildcard (`*` in a registered pattern) → dead letter. Do not reorder these without updating the tests and the docs.
- **TTL before dispatch.** `route()` checks `routing.ttl_hops`; expired messages are dropped and counted (`stats.dropped`), TTL is decremented per hop. Never route a message whose TTL has hit zero.
- **Authorization after TTL, before dispatch.** When `set_authorizer` has attached a `MessageAuthorizer`, every routed message is authorized (fail-closed) before any handler runs. **No authorizer => identical behavior to the unauthenticated path** — this is the backward-compat invariant; the 490-test suite depends on it. Denials increment `stats.denied` and re-raise `AuthzDeniedError`.
- **AURC envelope is the frozen wire contract.** `Codec` serializes/deserializes `AURCMessage`. The envelope shape is the cross-protocol contract — do not change field names or semantics in a patch release. Adding a field is additive; renaming or removing is a breaking change.
- **Broadcast is `gather` with `return_exceptions=True`.** A failing subscriber logs + counts `stats.errors` but does not abort the broadcast. Other subscribers still receive.
- **Dead letter queue is bounded** (`_max_dead_letters = 100`, FIFO popleft). It is in-memory only — restart loses it (TODO P3: pluggable `DeadLetterStore`).

## When editing here

- New target prefix (e.g. a new external protocol): register it in the bridge-routing branch of `route()` and via `register_bridge_forwarder`.
- The router is sync-owned but `route()` is async; handler errors propagate (re-raised after logging + `stats.errors`). Do not add a broad `except: return None` around a handler call — that breaks fail-loud.
- Wildcard matching is segment-based (`*` matches a whole `/`-segment, equal segment count required). It is O(n) over registered handlers on a miss (TODO P2: prefix index). Don't "optimize" it by changing the match semantics without updating `test_router.py`.
