# Bridges

Protocol bridges translate between external agent protocols (MCP · A2A · ACP) and the AURC core. Each bridge is bidirectional (`translate_to_aurc` / `translate_from_aurc`), context-preserving, and capability-mapped.

## Contract (verified against `bridges/authz_guard.py`, `bridges/base.py`)

- **Inbound is fail-closed.** `BridgeAuthzGuard` wraps `translate_to_aurc()` so every inbound message is authorized against the CapABAC `AuthorizationEngine` *before* it reaches the orchestrator. Default deny: no matching policy => `BridgeAuthzError`, and the translated message is **never returned** on denial.
- **Opt-in guard.** Bridges without a guard keep their original (unauthenticated) behavior, so existing deployments are not broken. When you attach a guard, ensure the engine has the policies the deployment needs — there is no implicit allow.
- **Delegation only narrows.** If a `DelegationValidator` is attached and the message carries a `delegation_chain`, the chain is validated *before* the authz decision. A rejected chain raises `BridgeAuthzError("Delegation rejected: ...")` — capabilities never widen across a hop.
- **Outbound passes through.** Only `translate_to_aurc` is guarded; `translate_from_aurc` and `map_capabilities` are unchanged.
- **Errors propagate, never swallowed.** If `translate_to_aurc` itself throws, the exception propagates — the guard does not mask translation failures into a silent deny.
- **Shared derivation.** Agent_id / resource_type / action come from `security.message_authz.derive_authz_request` — the same helper the router hot path uses. Do not re-derive in a bridge-specific way; the two enforcement points must stay consistent.

## When editing here

- Adding a new bridge: subclass the base in `base.py`, implement both translation directions, and register a forwarder with `MessageRouter.register_bridge_forwarder` for your `mcp:`/`a2a:`/`acp:` prefix.
- Do not bypass the guard "just to get it working" — if a legitimate message is denied, the policy is wrong, not the guard. Add the policy.
- Deny path must log at WARNING and increment `denied_count`; allow path logs at INFO and increments `allowed_count`. Keep the counters in sync if you touch the logic.
