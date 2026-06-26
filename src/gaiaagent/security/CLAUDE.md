# Security

CapABAC (Capability + Attribute-Based Access Control) authorization, delegation chains, audit, and message signing.

## Contract (verified against `security/authz.py`, `security/delegation.py`, `security/message_authz.py`, `security/audit.py`)

- **Default deny.** `AuthorizationEngine.authorize()` denies unless an explicit rule matches. Never add an implicit-allow path. A missing policy is a denial, not an error.
- **Delegation only narrows, never widens.** `DelegationValidator` enforces: every hop recorded, scopes monotonically narrowing, depth bounded (`max_depth`, default 5), chain integrity verifiable. This is the MCP Confused Deputy fix — do not weaken it.
- **Ed25519 signatures are per-hop optional but, when present, verified.** `require_signatures` flips the chain to mandatory-signed mode for high-trust deployments. `register_public_key(key_id, pubkey)` registers 32-byte Ed25519 public keys. Never accept an unsigned hop as "good enough" when `require_signatures=True`.
- **Two enforcement points, one derivation.** `BridgeAuthzGuard` (inbound bridge) and `RouteAuthzGuard` (router hot path) both call `derive_authz_request` from `message_authz.py`. If you change how agent_id / resource_type / action are derived, both points change — that is the point.
- **Fail-closed on the hot path.** `RouteAuthzGuard.authorize_message` returns `None` on allow and raises `AuthzDeniedError` on deny. Callers (`AURCServer`) map `AuthzDeniedError` to a structured `forbidden` envelope — they do **not** re-parse the reason string. Keep `AuthzDeniedError` carrying `agent_id` + `resource`.
- **Audit every decision.** When an `AuditLog` is attached, grants log as `AUTHZ_GRANTED` (INFO) and denials as `AUTHZ_DENIED` (WARNING). `log_grants=False` disables grant logging for high-throughput hot paths — denials are always logged. `PrometheusMetricsExporter` renders `aurc_audit_events_total{action=...}` from audit action stats, so wiring a shared audit log makes authz observable for free.
- **No exception leakage.** Deny reasons go to the audit log and the structured error envelope, never raw `str(exc)` to the wire. If you add a new deny reason, route it through `AuthzDeniedError` + audit, not through a generic 500.

## When editing here

- A new `Constraint` operator: implement it in `Constraint.evaluate` (match statement) and add a test. Unknown operators return `False` (fail-closed) — do not change this to `True`.
- A new `AuditAction`: add it to `security/audit.py`, render it in the metrics exporter's action stats, and write the audit + metrics tests together.
- Policy persistence is SQLite-backed (`policy_store.py`); in-memory `MemoryPolicyStore` is the test/default fallback. Do not invent a third store without going through `PolicyStore`.
