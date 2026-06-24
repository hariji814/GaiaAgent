# Security Model Deep Dive / 安全模型详解

> **[← Back to README](../../README.md)** | [Architecture](../architecture.md) | [Protocol Spec](../../PROTOCOL.md) | [API Reference](../api-reference.md)

## Threat Model / 威胁模型

AURC addresses these threats in multi-agent systems:

| Threat | Description | AURC Mitigation |
|--------|-------------|-----------------|
| **Confused Deputy** | Agent acts on behalf of user but can't enforce user's permissions | Delegation chain validation |
| **Scope Escalation** | Agent gains more permissions than delegated | CapABAC scope narrowing rule |
| **Unauthorized Access** | Agent accesses resources it shouldn't | CapABAC constraint evaluation |
| **Replay Attacks** | Old messages reused maliciously | Timestamp validation in delegation chains |
| **Audit Evasion** | Malicious actions go unrecorded | Immutable append-only audit log |
| **Protocol Bypass** | Security rules bypassed via bridge | Bridge-level permission enforcement |

## CapABAC Model / CapABAC 模型

CapABAC = **Cap**ability-Based + **A**ttribute-**B**ased **A**ccess **C**ontrol

```
┌─────────────────────────────────────────────────┐
│  Authorization Decision                          │
│                                                  │
│  1. Policy exists for agent? ─── No ──→ DENY     │
│         │ Yes                                    │
│  2. Rule matches resource + action? ── No → DENY │
│         │ Yes                                    │
│  3. Time window valid? ──────────────── No → SKIP│
│         │ Yes                                    │
│  4. All constraints satisfied? ──────── No → SKIP│
│         │ Yes                                    │
│  5. Rate limit OK? ──────────────────── No → DENY│
│         │ Yes                                    │
│  6. → ALLOW                                      │
└─────────────────────────────────────────────────┘
```

### Constraint Operators / 约束运算符

| Operator | Example | Description |
|----------|---------|-------------|
| `eq` | `Constraint("role", "eq", "admin")` | Equal |
| `ne` | `Constraint("status", "ne", "blocked")` | Not equal |
| `gt/lt/gte/lte` | `Constraint("amount", "lte", 1000)` | Comparison |
| `in` | `Constraint("env", "in", ["prod", "staging"])` | Membership |
| `not_in` | `Constraint("ip", "not_in", blacklist)` | Exclusion |
| `matches` | `Constraint("domain", "matches", r".*\.edu$")` | Regex |
| `contains` | `Constraint("tags", "contains", "verified")` | Substring |

## Delegation Chain Rules / 委托链规则

```
Rule 1: Scopes ONLY narrow, never widen
  User [read, write, admin]
    → Orchestrator [read, write]        ✓ narrowed
    → Researcher [read]                 ✓ narrowed
    → Tool [read, execute]              ✗ WIDENED → REJECTED

Rule 2: No circular delegations
  A → B → C → A                        ✗ REJECTED

Rule 3: Timestamps must be ordered
  Hop 1: 10:00:00
  Hop 2: 09:59:00                      ✗ REJECTED (out of order)

Rule 4: Depth limit enforced
  max_depth=3, chain has 5 hops        ✗ REJECTED
```

## Authentication Methods / 认证方法

```python
from gaiaagent.security import MultiAuthenticator

auth = MultiAuthenticator()

# API Key (dev/internal) / API Key（开发/内部）
api = auth.add_api_key()
key = api.create_key("aurc:my/agent:v1.0", scopes=["read", "write"])

# JWT (cross-org) / JWT（跨组织）
jwt = auth.add_jwt(secret="your-secret")
token = jwt.create_token("aurc:my/agent:v1.0", scopes=["read"])

# Authenticate / 认证
result = auth.authenticate_any({"api_key": key, "jwt": token})
```

## Audit Trail / 审计追踪

Every security-relevant event is recorded:

```python
from gaiaagent.security import AuditLog, AuditAction

audit = AuditLog()
audit.log(AuditAction.AUTHZ_DENIED,
          agent_id="aurc:my/agent:v1.0",
          severity=AuditSeverity.WARNING,
          details={"resource": "database", "action": "write"})

# Query / 查询
denied = audit.query(action=AuditAction.AUTHZ_DENIED)

# Export for compliance / 合规导出
audit.export_to_file("audit-2026-06.json")
```
