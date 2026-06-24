# Security Guide / 安全指南

> Authentication, authorization, delegation chains, and audit logging for AURC agents
> AURC Agent 的认证、授权、委托链和审计日志

---

## Table of Contents / 目录

1. [Security Overview / 安全概述](#security-overview--安全概述)
2. [Authentication / 认证](#authentication--认证)
3. [CapABAC Authorization / CapABAC 授权](#capabac-authorization--capabac-授权)
4. [Delegation Chains / 委托链](#delegation-chains--委托链)
5. [Audit Logging / 审计日志](#audit-logging--审计日志)
6. [Security Best Practices / 安全最佳实践](#security-best-practices--安全最佳实践)
7. [Threat Model / 威胁模型](#threat-model--威胁模型)

---

## Security Overview / 安全概述

AURC's security model is designed around the principle of **protocol-level enforcement** — permissions are not just declarative, they are enforceable at every layer of the system.

AURC 的安全模型基于**协议级强制执行**原则 — 权限不仅是声明性的，而且在系统的每一层都是可强制执行的。

```
┌─────────────────────────────────────────────────────────────┐
│ AURC Security Architecture / AURC 安全架构                   │
│                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌────────────┐  │
│  │ Authentication  │  │ Authorization   │  │ Audit      │  │
│  │ 认证            │  │ 授权            │  │ 审计       │  │
│  │                 │  │                 │  │            │  │
│  │ • API Key       │  │ • CapABAC       │  │ • Append-  │  │
│  │ • JWT           │  │ • Constraints   │  │   only log │  │
│  │ • Multi-method  │  │ • Rate limiting │  │ • Query    │  │
│  │                 │  │ • Time windows  │  │ • Export   │  │
│  └─────────────────┘  └─────────────────┘  └────────────┘  │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Delegation Chain Validation / 委托链验证             │    │
│  │  • Scope narrowing only / 仅权限缩小                 │    │
│  │  • Depth limits / 深度限制                          │    │
│  │  • Circular detection / 循环检测                    │    │
│  │  • Chain integrity hashing / 链完整性哈希           │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Solving MCP's Confused Deputy Problem / 解决 MCP 的混淆代理问题

MCP's core security issue: servers act on behalf of users but cannot distinguish or enforce what users are authorized to do. AURC solves this with:

MCP 的核心安全问题：服务器代表用户行事，但无法区分或强制执行用户的授权。AURC 通过以下方式解决：

1. Every invocation carries a **Delegation Chain** / 每次调用携带**委托链**
2. Bridge layer **enforces permission mapping** / 桥接层**强制执行权限映射**
3. **Immutable audit log** records all cross-protocol calls / **不可变审计日志**记录所有跨协议调用

---

## Authentication / 认证

### API Key Authentication / API Key 认证

API keys are the simplest authentication method, suitable for development and internal services.

API Key 是最简单的认证方式，适用于开发和内部服务。

```python
from gaiaagent.security.auth import APIKeyAuthenticator

auth = APIKeyAuthenticator()

# Create a key for an agent / 为 Agent 创建 Key
key = auth.create_key(
    "aurc:gaia/researcher:v1.0",
    scopes=["research:read", "web:search"],
    prefix="aurc",
)
print(f"API Key: {key}")  # e.g., "aurc_aBcDeFgHiJkLmNoPqRsTuVwXyZ..."
# IMPORTANT: The key is shown only once! / 重要：Key 仅显示一次!

# Authenticate / 认证
result = auth.authenticate(key)
print(f"Authenticated: {result.authenticated}")  # True
print(f"Agent ID: {result.agent_id}")           # "aurc:gaia/researcher:v1.0"
print(f"Scopes: {result.scopes}")               # ["research:read", "web:search"]

# Invalid key / 无效 Key
bad_result = auth.authenticate("invalid_key")
print(f"Authenticated: {bad_result.authenticated}")  # False
print(f"Error: {bad_result.error}")                  # "Invalid API key"
```

**Key storage / Key 存储:** Keys are stored as SHA-256 hashes — the raw key is never stored after creation.

**Key 存储:** Key 以 SHA-256 哈希存储 — 原始 Key 在创建后从不存储。

```python
# Revoke a key / 吊销 Key
auth.revoke_key(key)

# Revoke all keys for an agent / 吊销 Agent 的所有 Key
count = auth.revoke_agent_keys("aurc:gaia/researcher:v1.0")
print(f"Revoked {count} keys")
```

### JWT Authentication / JWT 认证

JWT tokens provide time-limited, scope-bearing authentication.

JWT 令牌提供有时限、带权限范围的认证。

```python
from gaiaagent.security.auth import JWTAuthenticator

jwt_auth = JWTAuthenticator(secret="your-secret-key")

# Create a token / 创建令牌
token = jwt_auth.create_token(
    agent_id="aurc:gaia/researcher:v1.0",
    scopes=["research:read", "web:search"],
    expires_in_seconds=3600,  # 1 hour / 1 小时
)
print(f"Token: {token}")  # "eyJhbGciOi..."

# Authenticate / 认证
result = jwt_auth.authenticate(token)
print(f"Authenticated: {result.authenticated}")  # True
print(f"Agent ID: {result.agent_id}")
print(f"Expires at: {result.expires_at}")
print(f"Valid: {result.is_valid}")  # Checks auth + expiration / 检查认证 + 过期
```

**Token structure / 令牌结构:**
- Header: `{"alg": "HS256", "typ": "JWT"}`
- Payload: `{"sub": agent_id, "scopes": [...], "exp": timestamp, "iat": timestamp}`
- Signature: HMAC-SHA256 verification

### Multi-Method Authentication / 多方式认证

Combine multiple authentication methods with `MultiAuthenticator`:

使用 `MultiAuthenticator` 组合多种认证方式:

```python
from gaiaagent.security.auth import MultiAuthenticator

auth = MultiAuthenticator()
api_key_auth = auth.add_api_key()
jwt_auth = auth.add_jwt(secret="my-secret")

# Create credentials / 创建凭证
key = api_key_auth.create_key("aurc:gaia/agent:v1.0", scopes=["read"])
token = jwt_auth.create_token("aurc:gaia/agent:v1.0", scopes=["read"])

# Authenticate with specific method / 使用特定方式认证
result = auth.authenticate("api_key", key)
result = auth.authenticate("jwt", token)

# Try multiple methods, return first success / 尝试多种方式，返回首个成功
result = auth.authenticate_any({
    "api_key": key,
    "jwt": token,
})
```

### AuthResult / 认证结果

All authentication methods return an `AuthResult`:

```python
@dataclass
class AuthResult:
    authenticated: bool          # Success / 成功
    agent_id: str | None         # Authenticated agent / 已认证的 Agent
    scopes: list[str]            # Granted scopes / 授予的权限范围
    expires_at: datetime | None  # Token expiration / 令牌过期时间
    metadata: dict[str, Any]     # Additional info / 附加信息
    error: str | None            # Error message / 错误消息

    @property
    def is_valid(self) -> bool:
        """Check authenticated AND not expired / 检查已认证且未过期"""
```

---

## CapABAC Authorization / CapABAC 授权

CapABAC combines Capability-Based Security with Attribute-Based Access Control:

- **Capabilities**: what actions are allowed / 能力：允许什么操作
- **Attributes**: under what conditions / 属性：在什么条件下

### Core Concepts / 核心概念

- **Default deny** — everything is denied unless explicitly allowed / 默认拒绝 — 除非明确允许
- **Capabilities can be delegated** with narrowing / 能力可以缩小范围后委托
- **Constraints are evaluated** at authorization time / 约束在授权时求值

### Setting Up Authorization / 设置授权

```python
from gaiaagent.security.authz import (
    AuthorizationEngine, AgentPolicy, AuthorizationRule,
    Constraint, DelegationPolicy,
)

engine = AuthorizationEngine()

# Define a policy for a research agent / 为研究 Agent 定义策略
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
            rate_limit=100,  # max 100 searches per hour / 每小时最多 100 次搜索
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

### Making Authorization Decisions / 做出授权决策

```python
# Allowed / 允许
result = engine.authorize(
    agent_id="aurc:gaia/researcher:v1.0",
    resource_type="web-search",
    action="execute",
    attributes={"domain": "mit.edu", "query_length": 50},
)
print(f"Allowed: {result.allowed}")  # True
print(f"Reason: {result.reason}")    # "Authorized: 'execute' on 'web-search'"

# Denied by constraint / 被约束拒绝
result = engine.authorize(
    agent_id="aurc:gaia/researcher:v1.0",
    resource_type="web-search",
    action="execute",
    attributes={"domain": "suspicious-site.com", "query_length": 50},
)
print(f"Allowed: {result.allowed}")  # False (domain doesn't match *.edu/*.gov)

# Denied by rate limit / 被速率限制拒绝
# After 100 requests, next one is denied / 100 次请求后，下一次被拒绝
```

### Constraint Operators / 约束操作符

| Operator | Description / 描述 | Example |
|----------|-------------|---------|
| `eq` | Equal / 等于 | `Constraint("status", "eq", "active")` |
| `ne` | Not equal / 不等于 | `Constraint("type", "ne", "admin")` |
| `gt` | Greater than / 大于 | `Constraint("score", "gt", 0.5)` |
| `lt` | Less than / 小于 | `Constraint("size", "lt", 100)` |
| `gte` | Greater or equal / 大于等于 | `Constraint("age", "gte", 18)` |
| `lte` | Less or equal / 小于等于 | `Constraint("length", "lte", 5000)` |
| `in` | In list / 在列表中 | `Constraint("role", "in", ["user", "admin"])` |
| `not_in` | Not in list / 不在列表中 | `Constraint("ip", "not_in", blocklist)` |
| `matches` | Regex match / 正则匹配 | `Constraint("domain", "matches", r".*\.edu$")` |
| `contains` | Contains substring / 包含子串 | `Constraint("text", "contains", "keyword")` |

### Scope-Based Authorization / 基于权限范围的授权

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

## Delegation Chains / 委托链

Delegation chains record the full permission path from the original requester to the executing agent. This is AURC's solution to the Confused Deputy problem.

委托链记录从原始请求者到执行 Agent 的完整权限路径。这是 AURC 解决混淆代理问题的方案。

### Visual Example / 可视化示例

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

### Building Delegation Chains / 构建委托链

```python
from gaiaagent.security.delegation import DelegationBuilder

builder = DelegationBuilder()

# Hop 1: User → Orchestrator / 第 1 跳：用户 → 编排器
builder.add_hop(
    from_agent="aurc:user/alice:v1.0",
    to_agent="aurc:gaia/orchestrator:v1.0",
    scopes=["research:read", "web:search", "admin"],
)

# Hop 2: Orchestrator → Researcher (narrowed) / 第 2 跳：编排器 → 研究员（缩小）
builder.add_hop(
    from_agent="aurc:gaia/orchestrator:v1.0",
    to_agent="aurc:gaia/researcher:v1.2",
    scopes=["research:read", "web:search"],  # admin removed / 移除了 admin
)

# Hop 3: Researcher → MCP Tool (further narrowed) / 第 3 跳：研究员 → MCP 工具
builder.add_hop(
    from_agent="aurc:gaia/researcher:v1.2",
    to_agent="mcp:web-search/server",
    scopes=["research:read"],  # further narrowed / 进一步缩小
)

chain = builder.build()
print(f"Depth: {builder.depth}")               # 3
print(f"Effective scopes: {builder.effective_scopes}")  # ["research:read"]
```

### Scope Widening Prevention / 防止权限扩大

The builder raises `ValueError` if you try to widen scopes:

如果你尝试扩大权限，构建器会抛出 `ValueError`:

```python
builder = DelegationBuilder()
builder.add_hop(
    from_agent="aurc:user/alice:v1.0",
    to_agent="aurc:gaia/orchestrator:v1.0",
    scopes=["research:read"],
)

# This will raise ValueError! / 这会抛出 ValueError!
try:
    builder.add_hop(
        from_agent="aurc:gaia/orchestrator:v1.0",
        to_agent="aurc:gaia/researcher:v1.0",
        scopes=["research:read", "admin"],  # admin not in previous scopes!
    )
except ValueError as e:
    print(f"Cannot widen: {e}")
```

### Validating Delegation Chains / 验证委托链

```python
from gaiaagent.security.delegation import DelegationValidator
from gaiaagent.core.message import MessageSecurity, DelegationHop

validator = DelegationValidator(max_depth=5)

# Build security context / 构建安全上下文
security = MessageSecurity(
    scopes=["research:read"],
    delegation_chain=chain,
)

# Validate / 验证
result = validator.validate(security)
print(f"Valid: {result.valid}")             # True
print(f"Reason: {result.reason}")           # "Valid delegation chain: 3 hops"
print(f"Depth: {result.depth}")             # 3
print(f"Effective scopes: {result.effective_scopes}")

# Validate with required scopes / 带所需权限验证
result = validator.validate_effective_scopes(
    security,
    required_scopes=["research:read"],
)
print(f"Sufficient: {result.valid}")  # True
```

### What Validation Checks / 验证检查项

| Check / 检查项 | Description / 描述 |
|------|-------------|
| **Depth limit** / 深度限制 | Chain length ≤ max_depth |
| **Scope narrowing** / 权限缩小 | Each hop's scopes ⊆ previous hop's scopes |
| **No circular delegation** / 无循环委托 | No agent appears twice as `to_agent` |
| **Timestamp ordering** / 时间戳顺序 | Each hop's timestamp ≥ previous hop's |

### Chain Integrity Hash / 链完整性哈希

```python
from gaiaagent.security.delegation import compute_chain_hash

chain_hash = compute_chain_hash(chain)
print(f"Chain hash: {chain_hash}")
# Store this hash to detect tampering / 存储此哈希以检测篡改
```

---

## Audit Logging / 审计日志

The audit log provides an immutable, append-only trail of all security-relevant events.

审计日志提供所有安全相关事件的不可变、仅追加追踪。

### Creating Audit Entries / 创建审计条目

```python
from gaiaagent.security.audit import AuditLog, AuditAction, AuditSeverity

audit = AuditLog(max_entries=10000)

# Log authentication events / 记录认证事件
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

# Log authorization decisions / 记录授权决策
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

# Log delegation events / 记录委托事件
audit.log(
    action=AuditAction.DELEGATION_CREATED,
    agent_id="aurc:gaia/orchestrator:v1.0",
    target_id="aurc:gaia/researcher:v1.2",
    details={"scopes": ["research:read"], "depth": 2},
)

# Log cross-protocol bridging / 记录跨协议桥接
audit.log(
    action=AuditAction.MESSAGE_BRIDGED,
    agent_id="aurc:gaia/researcher:v1.0",
    protocol="mcp/2025-06-18",
    details={"bridge": "mcp→aurc", "skill": "web-search"},
)
```

### Available Audit Actions / 可用审计动作

| Category / 类别 | Actions / 动作 |
|----------|---------|
| **Agent lifecycle** | `AGENT_REGISTERED`, `AGENT_UNREGISTERED`, `AGENT_STARTED`, `AGENT_STOPPED`, `AGENT_PAUSED`, `AGENT_RESUMED`, `AGENT_ERROR`, `AGENT_RECOVERED` |
| **Messages** | `MESSAGE_SENT`, `MESSAGE_RECEIVED`, `MESSAGE_ROUTED`, `MESSAGE_BRIDGED` |
| **Authentication** | `AUTH_SUCCESS`, `AUTH_FAILURE` |
| **Authorization** | `AUTHZ_GRANTED`, `AUTHZ_DENIED` |
| **Delegation** | `DELEGATION_CREATED`, `DELEGATION_VALIDATED`, `DELEGATION_REJECTED` |
| **Sessions** | `SESSION_CREATED`, `SESSION_CLOSED` |
| **Other** | `CONTEXT_MODIFIED`, `POLICY_CHANGED` |

### Querying the Audit Log / 查询审计日志

```python
# Query by agent / 按 Agent 查询
entries = audit.query(agent_id="aurc:gaia/researcher:v1.0")

# Query by action type / 按动作类型查询
bridge_events = audit.query(action=AuditAction.MESSAGE_BRIDGED)

# Query by severity / 按严重级别查询
warnings = audit.query(severity=AuditSeverity.WARNING)

# Query by time range / 按时间范围查询
from datetime import datetime, timezone, timedelta
since = datetime.now(timezone.utc) - timedelta(hours=1)
recent = audit.query(since=since)

# Query by correlation ID / 按关联 ID 查询
correlated = audit.get_by_correlation("corr-xyz-789")

# Get recent entries / 获取最近条目
last_50 = audit.get_recent(50)

# Get statistics / 获取统计
stats = audit.stats()
# {"auth_success": 150, "authz_granted": 320, "authz_denied": 12, ...}
```

### Exporting for Compliance / 合规导出

```python
# Export to JSON file / 导出为 JSON 文件
count = audit.export_to_file("audit_log_2026_06.json")
print(f"Exported {count} entries")

# Import from file / 从文件导入
count = audit.import_from_file("audit_log_2026_06.json")
print(f"Imported {count} entries")
```

---

## Security Best Practices / 安全最佳实践

### 1. Always Use Delegation Chains / 始终使用委托链

```python
# When delegating tasks, always build a proper chain / 委派任务时始终构建正确的链
builder = DelegationBuilder()
builder.add_hop(from_agent=user_id, to_agent=orchestrator_id, scopes=user_scopes)
builder.add_hop(from_agent=orchestrator_id, to_agent=worker_id,
                scopes=narrowed_scopes)  # Always narrow! / 始终缩小!
```

### 2. Set Rate Limits / 设置速率限制

```python
AuthorizationRule(
    resource_type="expensive-api",
    actions=["execute"],
    rate_limit=50,  # 50 calls per hour / 每小时 50 次调用
)
```

### 3. Use Time Windows for Sensitive Operations / 对敏感操作使用时间窗口

```python
AuthorizationRule(
    resource_type="production-database",
    actions=["write"],
    time_window={"start": "09:00", "end": "17:00", "timezone": "UTC"},
)
```

### 4. Validate Before Executing / 执行前验证

```python
# Always validate delegation chain before executing delegated tasks
# 执行委派任务前始终验证委托链
validator = DelegationValidator(max_depth=3)
result = validator.validate(message.security)
if not result.valid:
    raise PermissionError(result.reason)
```

### 5. Audit Everything / 审计一切

```python
# Log every authorization decision / 记录每个授权决策
audit.log(
    action=AuditAction.AUTHZ_GRANTED if authz_result.allowed else AuditAction.AUTHZ_DENIED,
    agent_id=agent_id,
    details={"resource": resource_type, "action": action, "reason": authz_result.reason},
)
```

### 6. Rotate Keys Regularly / 定期轮换 Key

```python
# Revoke old keys and create new ones / 吊销旧 Key 并创建新 Key
auth.revoke_agent_keys("aurc:gaia/researcher:v1.0")
new_key = auth.create_key("aurc:gaia/researcher:v1.0", scopes=[...])
```

### 7. Use Least Privilege / 使用最小权限

```python
# Only grant the scopes needed / 只授予所需的权限
builder.add_hop(
    from_agent=orchestrator_id,
    to_agent=worker_id,
    scopes=["specific:read"],  # Not ["*"] or all scopes
)
```

---

## Threat Model / 威胁模型

### Threat Categories / 威胁类别

| Threat / 威胁 | Risk / 风险 | AURC Mitigation / AURC 缓解措施 |
|-------|------|-------------------|
| **Unauthorized access** / 未授权访问 | High | CapABAC default deny + API Key/JWT auth |
| **Privilege escalation** / 权限提升 | High | Scope narrowing enforcement in delegation chains |
| **Confused Deputy** / 混淆代理 | High | Delegation chain tracking across all bridges |
| **Replay attacks** / 重放攻击 | Medium | Timestamp ordering + TTL in messages |
| **Circular delegation** / 循环委托 | Medium | Circular detection in DelegationValidator |
| **Chain tampering** / 链篡改 | Medium | Chain integrity hashing via `compute_chain_hash()` |
| **Rate limit abuse** / 速率限制滥用 | Medium | Sliding-window rate limiter per agent/resource |
| **Unbounded delegation** / 无限委托 | Medium | Max depth limit in DelegationValidator |
| **Audit evasion** / 审计规避 | Low | Append-only audit log with ring buffer |

### Security Architecture Decisions / 安全架构决策

1. **API keys are SHA-256 hashed** — raw keys never stored / API Key 经 SHA-256 哈希 — 从不存储原始 Key
2. **JWT tokens have expiration** — no indefinite tokens / JWT 令牌有过期时间 — 无无限期令牌
3. **Delegation scopes are monotonic** — can only narrow / 委托权限是单调的 — 只能缩小
4. **Audit log is append-only** — entries cannot be modified / 审计日志仅追加 — 条目不可修改
5. **Ring buffer with max capacity** — prevents unbounded memory growth / 最大容量环形缓冲区 — 防止无限内存增长

---

*See also / 另请参阅: [Architecture Deep Dive](../architecture.md) | [Bridge Guide](bridges.md) | [API Reference](../api-reference.md)*
