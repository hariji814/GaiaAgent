# Security Guide

> 🌐 [中文版](../../zh/guides/security.md)
>
> **[← Back to README](../../../README.md)** | [Architecture](../architecture.md) | [Security Model Deep Dive](../architecture/security-model.md) | [Protocol Spec](../../../PROTOCOL.md)
>
> Authentication, authorization, delegation chains, and audit logging for AURC agents

---

## Table of Contents

1. [Security Overview](#security-overview)
2. [Authentication](#authentication)
3. [CapABAC Authorization](#capabac-authorization)
4. [Delegation Chains](#delegation-chains)
5. [Audit Logging](#audit-logging)
6. [Security Best Practices](#security-best-practices)
7. [Threat Model](#threat-model)

---

## Security Overview

AURC's security model is designed around the principle of **protocol-level enforcement** — permissions are not just declarative, they are enforceable at every layer of the system.

```
┌─────────────────────────────────────────────────────────────┐
│ AURC Security Architecture                                   │
│                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌────────────┐  │
│  │ Authentication  │  │ Authorization   │  │ Audit      │  │
│  │                 │  │                 │  │            │  │
│  │ • API Key       │  │ • CapABAC       │  │ • Append-  │  │
│  │ • JWT           │  │ • Constraints   │  │   only log │  │
│  │ • Multi-method  │  │ • Rate limiting │  │ • Query    │  │
│  │                 │  │ • Time windows  │  │ • Export   │  │
│  └─────────────────┘  └─────────────────┘  └────────────┘  │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Delegation Chain Validation                           │    │
│  │  • Scope narrowing only                                │    │
│  │  • Depth limits                                        │    │
│  │  • Circular detection                                  │    │
│  │  • Chain integrity hashing                             │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Solving MCP's Confused Deputy Problem

MCP's core security issue: servers act on behalf of users but cannot distinguish or enforce what users are authorized to do. AURC solves this with:

1. Every invocation carries a **Delegation Chain**
2. Bridge layer **enforces permission mapping**
3. **Immutable audit log** records all cross-protocol calls

---

## Authentication

### API Key Authentication

API keys are the simplest authentication method, suitable for development and internal services.

```python
from gaiaagent.security.auth import APIKeyAuthenticator

auth = APIKeyAuthenticator()

# Create a key for an agent
key = auth.create_key(
    "aurc:gaia/researcher:v1.0",
    scopes=["research:read", "web:search"],
    prefix="aurc",
)
print(f"API Key: {key}")  # e.g., "aurc_aBcDeFgHiJkLmNoPqRsTuVwXyZ..."
# IMPORTANT: The key is shown only once!

# Authenticate
result = auth.authenticate(key)
print(f"Authenticated: {result.authenticated}")  # True
print(f"Agent ID: {result.agent_id}")           # "aurc:gaia/researcher:v1.0"
print(f"Scopes: {result.scopes}")               # ["research:read", "web:search"]

# Invalid key
bad_result = auth.authenticate("invalid_key")
print(f"Authenticated: {bad_result.authenticated}")  # False
print(f"Error: {bad_result.error}")                  # "Invalid API key"
```

**Key storage:** Keys are stored as SHA-256 hashes — the raw key is never stored after creation.

```python
# Revoke a key
auth.revoke_key(key)

# Revoke all keys for an agent
count = auth.revoke_agent_keys("aurc:gaia/researcher:v1.0")
print(f"Revoked {count} keys")
```

### JWT Authentication

JWT tokens provide time-limited, scope-bearing authentication.

```python
from gaiaagent.security.auth import JWTAuthenticator

jwt_auth = JWTAuthenticator(secret="your-secret-key")

# Create a token
token = jwt_auth.create_token(
    agent_id="aurc:gaia/researcher:v1.0",
    scopes=["research:read", "web:search"],
    expires_in_seconds=3600,  # 1 hour
)
print(f"Token: {token}")  # "eyJhbGciOi..."

# Authenticate
result = jwt_auth.authenticate(token)
print(f"Authenticated: {result.authenticated}")  # True
print(f"Agent ID: {result.agent_id}")
print(f"Expires at: {result.expires_at}")
print(f"Valid: {result.is_valid}")  # Checks auth + expiration
```

**Token structure:**
- Header: `{"alg": "HS256", "typ": "JWT"}`
- Payload: `{"sub": agent_id, "scopes": [...], "exp": timestamp, "iat": timestamp}`
- Signature: HMAC-SHA256 verification

### Multi-Method Authentication

Combine multiple authentication methods with `MultiAuthenticator`:

```python
from gaiaagent.security.auth import MultiAuthenticator

auth = MultiAuthenticator()
api_key_auth = auth.add_api_key()
jwt_auth = auth.add_jwt(secret="my-secret")

# Create credentials
key = api_key_auth.create_key("aurc:gaia/agent:v1.0", scopes=["read"])
token = jwt_auth.create_token("aurc:gaia/agent:v1.0", scopes=["read"])

# Authenticate with specific method
result = auth.authenticate("api_key", key)
result = auth.authenticate("jwt", token)

# Try multiple methods, return first success
result = auth.authenticate_any({
    "api_key": key,
    "jwt": token,
})
```

### AuthResult

All authentication methods return an `AuthResult`:

```python
@dataclass
class AuthResult:
    authenticated: bool          # Success
    agent_id: str | None         # Authenticated agent
    scopes: list[str]            # Granted scopes
    expires_at: datetime | None  # Token expiration
    metadata: dict[str, Any]     # Additional info
    error: str | None            # Error message

    @property
    def is_valid(self) -> bool:
        """Check authenticated AND not expired"""
```

---

## CapABAC Authorization

CapABAC combines Capability-Based Security with Attribute-Based Access Control:

- **Capabilities**: what actions are allowed
- **Attributes**: under what conditions

### Core Concepts

- **Default deny** — everything is denied unless explicitly allowed
- **Capabilities can be delegated** with narrowing
- **Constraints are evaluated** at authorization time

### Setting Up Authorization

```python
from gaiaagent.security.authz import (
    AuthorizationEngine, AgentPolicy, AuthorizationRule,
    Constraint, DelegationPolicy,
)

engine = AuthorizationEngine()

# Define a policy for a research agent
engine.set_policy("aurc:gaia/researcher:v1.0", AgentPolicy(
    agent_id="aurc:gaia/researcher:v1.0",
    rules=[
        AuthorizationRule(
            resource_type="web-search",
            actions=["execute"],
            constraints=[
                Constraint("domain", "matches", r".*\.(edu|gov)$"),
                Constraint("query_length", "lte", 500),
            ],
            rate_limit=100,  # max 100 searches per hour
        ),
        AuthorizationRule(
            resource_type="document-reader",
            actions=["read"],
            constraints=[
                Constraint("file_size_mb", "lt", 50),
            ],
        ),
        AuthorizationRule(
            resource_type="internal-api",
            actions=["execute"],
            time_window={"start": "08:00", "end": "22:00", "timezone": "UTC"},
        ),
    ],
    delegation=DelegationPolicy(
        allowed=True,
        max_depth=3,
        scope_reduction_required=True,
    ),
))
```

### Making Authorization Decisions

```python
# Allowed
result = engine.authorize(
    agent_id="aurc:gaia/researcher:v1.0",
    resource_type="web-search",
    action="execute",
    attributes={"domain": "mit.edu", "query_length": 50},
)
print(f"Allowed: {result.allowed}")  # True
print(f"Reason: {result.reason}")    # "Authorized: 'execute' on 'web-search'"

# Denied by constraint
result = engine.authorize(
    agent_id="aurc:gaia/researcher:v1.0",
    resource_type="web-search",
    action="execute",
    attributes={"domain": "suspicious-site.com", "query_length": 50},
)
print(f"Allowed: {result.allowed}")  # False (domain doesn't match *.edu/*.gov)

# Denied by rate limit
# After 100 requests, next one is denied
```

### Constraint Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `eq` | Equal | `Constraint("status", "eq", "active")` |
| `ne` | Not equal | `Constraint("type", "ne", "admin")` |
| `gt` | Greater than | `Constraint("score", "gt", 0.5)` |
| `lt` | Less than | `Constraint("size", "lt", 100)` |
| `gte` | Greater or equal | `Constraint("age", "gte", 18)` |
| `lte` | Less or equal | `Constraint("length", "lte", 5000)` |
| `in` | In list | `Constraint("role", "in", ["user", "admin"])` |
| `not_in` | Not in list | `Constraint("ip", "not_in", blocklist)` |
| `matches` | Regex match | `Constraint("domain", "matches", r".*\.edu$")` |
| `contains` | Contains substring | `Constraint("text", "contains", "keyword")` |

### Scope-Based Authorization

```python
result = engine.authorize_scopes(
    agent_id="aurc:gaia/researcher:v1.0",
    resource_type="web-search",
    action="execute",
    required_scopes=["research:read"],
    granted_scopes=["research:read", "web:search"],
    attributes={"domain": "arxiv.org", "query_length": 100},
)
# Checks: required_scopes ⊆ granted_scopes, then checks rules
```

---

## Delegation Chains

Delegation chains record the full permission path from the original requester to the executing agent. This is AURC's solution to the Confused Deputy problem.

### Visual Example

```
User (Alice)
  scopes: [research:read, web:search, admin]
     │
     │ Hop 1: delegates to Orchestrator
     │ scopes granted: [research:read, web:search]  ← narrowed (admin removed)
     ▼
Orchestrator
  scopes: [research:read, web:search]
     │
     │ Hop 2: delegates to Researcher
     │ scopes granted: [research:read]  ← further narrowed
     ▼
Researcher Agent
  effective scopes: [research:read]
     │
     │ Hop 3: calls MCP tool via bridge
     │ effective: [research:read] ∩ MCP permissions
     ▼
MCP Server
```

### Building Delegation Chains

```python
from gaiaagent.security.delegation import DelegationBuilder

builder = DelegationBuilder()

# Hop 1: User → Orchestrator
builder.add_hop(
    from_agent="aurc:user/alice:v1.0",
    to_agent="aurc:gaia/orchestrator:v1.0",
    scopes=["research:read", "web:search", "admin"],
)

# Hop 2: Orchestrator → Researcher (narrowed)
builder.add_hop(
    from_agent="aurc:gaia/orchestrator:v1.0",
    to_agent="aurc:gaia/researcher:v1.2",
    scopes=["research:read", "web:search"],  # admin removed
)

# Hop 3: Researcher → MCP Tool (further narrowed)
builder.add_hop(
    from_agent="aurc:gaia/researcher:v1.2",
    to_agent="mcp:web-search/server",
    scopes=["research:read"],  # further narrowed
)

chain = builder.build()
print(f"Depth: {builder.depth}")               # 3
print(f"Effective scopes: {builder.effective_scopes}")  # ["research:read"]
```

### Scope Widening Prevention

The builder raises `ValueError` if you try to widen scopes:

```python
builder = DelegationBuilder()
builder.add_hop(
    from_agent="aurc:user/alice:v1.0",
    to_agent="aurc:gaia/orchestrator:v1.0",
    scopes=["research:read"],
)

# This will raise ValueError!
try:
    builder.add_hop(
        from_agent="aurc:gaia/orchestrator:v1.0",
        to_agent="aurc:gaia/researcher:v1.0",
        scopes=["research:read", "admin"],  # admin not in previous scopes!
    )
except ValueError as e:
    print(f"Cannot widen: {e}")
```

### Validating Delegation Chains

```python
from gaiaagent.security.delegation import DelegationValidator
from gaiaagent.core.message import MessageSecurity, DelegationHop

validator = DelegationValidator(max_depth=5)

# Build security context
security = MessageSecurity(
    scopes=["research:read"],
    delegation_chain=chain,
)

# Validate
result = validator.validate(security)
print(f"Valid: {result.valid}")             # True
print(f"Reason: {result.reason}")           # "Valid delegation chain: 3 hops"
print(f"Depth: {result.depth}")             # 3
print(f"Effective scopes: {result.effective_scopes}")

# Validate with required scopes
result = validator.validate_effective_scopes(
    security,
    required_scopes=["research:read"],
)
print(f"Sufficient: {result.valid}")  # True
```

### What Validation Checks

| Check | Description |
|------|-------------|
| **Depth limit** | Chain length ≤ max_depth |
| **Scope narrowing** | Each hop's scopes ⊆ previous hop's scopes |
| **No circular delegation** | No agent appears twice as `to_agent` |
| **Timestamp ordering** | Each hop's timestamp ≥ previous hop's' |

### Chain Integrity Hash

```python
from gaiaagent.security.delegation import compute_chain_hash

chain_hash = compute_chain_hash(chain)
print(f"Chain hash: {chain_hash}")
# Store this hash to detect tampering
```

---

## Audit Logging

The audit log provides an immutable, append-only trail of all security-relevant events.

### Creating Audit Entries

```python
from gaiaagent.security.audit import AuditLog, AuditAction, AuditSeverity

audit = AuditLog(max_entries=10000)

# Log authentication events
audit.log(
    action=AuditAction.AUTH_SUCCESS,
    agent_id="aurc:gaia/researcher:v1.0",
    protocol="aurc",
    details={"method": "api_key", "ip": "192.168.1.100"},
)

audit.log(
    action=AuditAction.AUTH_FAILURE,
    agent_id="unknown",
    severity=AuditSeverity.WARNING,
    details={"reason": "Invalid API key", "ip": "10.0.0.5"},
)

# Log authorization decisions
audit.log(
    action=AuditAction.AUTHZ_GRANTED,
    agent_id="aurc:gaia/researcher:v1.0",
    target_id="web-search",
    details={"action": "execute", "resource": "web-search"},
)

audit.log(
    action=AuditAction.AUTHZ_DENIED,
    agent_id="aurc:gaia/researcher:v1.0",
    severity=AuditSeverity.WARNING,
    details={"reason": "Rate limit exceeded"},
)

# Log delegation events
audit.log(
    action=AuditAction.DELEGATION_CREATED,
    agent_id="aurc:gaia/orchestrator:v1.0",
    target_id="aurc:gaia/researcher:v1.2",
    details={"scopes": ["research:read"], "depth": 2},
)

# Log cross-protocol bridging
audit.log(
    action=AuditAction.MESSAGE_BRIDGED,
    agent_id="aurc:gaia/researcher:v1.0",
    protocol="mcp/2025-06-18",
    details={"bridge": "mcp→aurc", "skill": "web-search"},
)
```

### Available Audit Actions

| Category | Actions |
|----------|---------|
| **Agent lifecycle** | `AGENT_REGISTERED`, `AGENT_UNREGISTERED`, `AGENT_STARTED`, `AGENT_STOPPED`, `AGENT_PAUSED`, `AGENT_RESUMED`, `AGENT_ERROR`, `AGENT_RECOVERED` |
| **Messages** | `MESSAGE_SENT`, `MESSAGE_RECEIVED`, `MESSAGE_ROUTED`, `MESSAGE_BRIDGED` |
| **Authentication** | `AUTH_SUCCESS`, `AUTH_FAILURE` |
| **Authorization** | `AUTHZ_GRANTED`, `AUTHZ_DENIED` |
| **Delegation** | `DELEGATION_CREATED`, `DELEGATION_VALIDATED`, `DELEGATION_REJECTED` |
| **Sessions** | `SESSION_CREATED`, `SESSION_CLOSED` |
| **Other** | `CONTEXT_MODIFIED`, `POLICY_CHANGED` |

### Querying the Audit Log

```python
# Query by agent
entries = audit.query(agent_id="aurc:gaia/researcher:v1.0")

# Query by action type
bridge_events = audit.query(action=AuditAction.MESSAGE_BRIDGED)

# Query by severity
warnings = audit.query(severity=AuditSeverity.WARNING)

# Query by time range
from datetime import datetime, timezone, timedelta
since = datetime.now(timezone.utc) - timedelta(hours=1)
recent = audit.query(since=since)

# Query by correlation ID
correlated = audit.get_by_correlation("corr-xyz-789")

# Get recent entries
last_50 = audit.get_recent(50)

# Get statistics
stats = audit.stats()
# {"auth_success": 150, "authz_granted": 320, "authz_denied": 12, ...}
```

### Exporting for Compliance

```python
# Export to JSON file
count = audit.export_to_file("audit_log_2026_06.json")
print(f"Exported {count} entries")

# Import from file
count = audit.import_from_file("audit_log_2026_06.json")
print(f"Imported {count} entries")
```

---

## Security Best Practices

### 1. Always Use Delegation Chains

```python
# When delegating tasks, always build a proper chain
builder = DelegationBuilder()
builder.add_hop(from_agent=user_id, to_agent=orchestrator_id, scopes=user_scopes)
builder.add_hop(from_agent=orchestrator_id, to_agent=worker_id,
                scopes=narrowed_scopes)  # Always narrow!
```

### 2. Set Rate Limits

```python
AuthorizationRule(
    resource_type="expensive-api",
    actions=["execute"],
    rate_limit=50,  # 50 calls per hour
)
```

### 3. Use Time Windows for Sensitive Operations

```python
AuthorizationRule(
    resource_type="production-database",
    actions=["write"],
    time_window={"start": "09:00", "end": "17:00", "timezone": "UTC"},
)
```

### 4. Validate Before Executing

```python
# Always validate delegation chain before executing delegated tasks
validator = DelegationValidator(max_depth=3)
result = validator.validate(message.security)
if not result.valid:
    raise PermissionError(result.reason)
```

### 5. Audit Everything

```python
# Log every authorization decision
audit.log(
    action=AuditAction.AUTHZ_GRANTED if authz_result.allowed else AuditAction.AUTHZ_DENIED,
    agent_id=agent_id,
    details={"resource": resource_type, "action": action, "reason": authz_result.reason},
)
```

### 6. Rotate Keys Regularly

```python
# Revoke old keys and create new ones
auth.revoke_agent_keys("aurc:gaia/researcher:v1.0")
new_key = auth.create_key("aurc:gaia/researcher:v1.0", scopes=[...])
```

### 7. Use Least Privilege

```python
# Only grant the scopes needed
builder.add_hop(
    from_agent=orchestrator_id,
    to_agent=worker_id,
    scopes=["specific:read"],  # Not ["*"] or all scopes
)
```

---

## Threat Model

### Threat Categories

| Threat | Risk | AURC Mitigation |
|-------|------|-------------------|
| **Unauthorized access** | High | CapABAC default deny + API Key/JWT auth |
| **Privilege escalation** | High | Scope narrowing enforcement in delegation chains |
| **Confused Deputy** | High | Delegation chain tracking across all bridges |
| **Replay attacks** | Medium | Timestamp ordering + TTL in messages |
| **Circular delegation** | Medium | Circular detection in DelegationValidator |
| **Chain tampering** | Medium | Chain integrity hashing via `compute_chain_hash()` |
| **Rate limit abuse** | Medium | Sliding-window rate limiter per agent/resource |
| **Unbounded delegation** | Medium | Max depth limit in DelegationValidator |
| **Audit evasion** | Low | Append-only audit log with ring buffer |

### Security Architecture Decisions

1. **API keys are SHA-256 hashed** — raw keys never stored
2. **JWT tokens have expiration** — no indefinite tokens
3. **Delegation scopes are monotonic** — can only narrow
4. **Audit log is append-only** — entries cannot be modified
5. **Ring buffer with max capacity** — prevents unbounded memory growth

---

*See also: [Architecture Deep Dive](../architecture.md) | [Bridge Guide](bridges.md) | [API Reference](../api-reference.md)*
