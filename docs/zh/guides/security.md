# 安全指南

> 🌐 [English](../../en/guides/security.md)
>
> **[← 返回 README](../../../README.zh.md)** | [架构](../architecture.md) | [安全模型深入解析](../architecture/security-model.md) | [协议规范](../../../PROTOCOL.zh.md)
>
> AURC Agent 的认证、授权、委托链和审计日志

---

## 目录

1. [安全概述](#安全概述)
2. [认证](#认证)
3. [CapABAC 授权](#capabac-授权)
4. [委托链](#委托链)
5. [审计日志](#审计日志)
6. [安全最佳实践](#安全最佳实践)
7. [威胁模型](#威胁模型)

---

## 安全概述

AURC 的安全模型基于**协议级强制执行**原则 — 权限不仅是声明性的，而且在系统的每一层都是可强制执行的。

```
┌─────────────────────────────────────────────────────────────┐
│ AURC 安全架构                                                │
│                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌────────────┐  │
│  │ 认证            │  │ 授权            │  │ 审计       │  │
│  │                 │  │                 │  │            │  │
│  │ • API Key       │  │ • CapABAC       │  │ • 仅追加   │  │
│  │ • JWT           │  │ • 约束          │  │   日志     │  │
│  │ • 多方式        │  │ • 速率限制      │  │ • 查询     │  │
│  │                 │  │ • 时间窗口      │  │ • 导出     │  │
│  └─────────────────┘  └─────────────────┘  └────────────┘  │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 委托链验证                                             │    │
│  │  • 仅权限缩小                                          │    │
│  │  • 深度限制                                            │    │
│  │  • 循环检测                                            │    │
│  │  • 链完整性哈希                                        │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 解决 MCP 的混淆代理问题

MCP 的核心安全问题：服务器代表用户行事，但无法区分或强制执行用户的授权。AURC 通过以下方式解决：

1. 每次调用携带**委托链**
2. 桥接层**强制执行权限映射**
3. **不可变审计日志**记录所有跨协议调用

---

## 认证

### API Key 认证

API Key 是最简单的认证方式，适用于开发和内部服务。

```python
from gaiaagent.security.auth import APIKeyAuthenticator

auth = APIKeyAuthenticator()

# 为 Agent 创建 Key
key = auth.create_key(
    "aurc:gaia/researcher:v1.0",
    scopes=["research:read", "web:search"],
    prefix="aurc",
)
print(f"API Key: {key}")  # e.g., "aurc_aBcDeFgHiJkLmNoPqRsTuVwXyZ..."
# 重要：Key 仅显示一次!

# 认证
result = auth.authenticate(key)
print(f"Authenticated: {result.authenticated}")  # True
print(f"Agent ID: {result.agent_id}")           # "aurc:gaia/researcher:v1.0"
print(f"Scopes: {result.scopes}")               # ["research:read", "web:search"]

# 无效 Key
bad_result = auth.authenticate("invalid_key")
print(f"Authenticated: {bad_result.authenticated}")  # False
print(f"Error: {bad_result.error}")                  # "Invalid API key"
```

**Key 存储:** Key 以 SHA-256 哈希存储 — 原始 Key 在创建后从不存储。

```python
# 吊销 Key
auth.revoke_key(key)

# 吊销 Agent 的所有 Key
count = auth.revoke_agent_keys("aurc:gaia/researcher:v1.0")
print(f"Revoked {count} keys")
```

### JWT 认证

JWT 令牌提供有时限、带权限范围的认证。

```python
from gaiaagent.security.auth import JWTAuthenticator

jwt_auth = JWTAuthenticator(secret="your-secret-key")

# 创建令牌
token = jwt_auth.create_token(
    agent_id="aurc:gaia/researcher:v1.0",
    scopes=["research:read", "web:search"],
    expires_in_seconds=3600,  # 1 小时
)
print(f"Token: {token}")  # "eyJhbGciOi..."

# 认证
result = jwt_auth.authenticate(token)
print(f"Authenticated: {result.authenticated}")  # True
print(f"Agent ID: {result.agent_id}")
print(f"Expires at: {result.expires_at}")
print(f"Valid: {result.is_valid}")  # 检查认证 + 过期
```

**令牌结构:**
- Header: `{"alg": "HS256", "typ": "JWT"}`
- Payload: `{"sub": agent_id, "scopes": [...], "exp": timestamp, "iat": timestamp}`
- Signature: HMAC-SHA256 verification

### 多方式认证

使用 `MultiAuthenticator` 组合多种认证方式:

```python
from gaiaagent.security.auth import MultiAuthenticator

auth = MultiAuthenticator()
api_key_auth = auth.add_api_key()
jwt_auth = auth.add_jwt(secret="my-secret")

# 创建凭证
key = api_key_auth.create_key("aurc:gaia/agent:v1.0", scopes=["read"])
token = jwt_auth.create_token("aurc:gaia/agent:v1.0", scopes=["read"])

# 使用特定方式认证
result = auth.authenticate("api_key", key)
result = auth.authenticate("jwt", token)

# 尝试多种方式，返回首个成功
result = auth.authenticate_any({
    "api_key": key,
    "jwt": token,
})
```

### 认证结果

所有认证方式都返回一个 `AuthResult`:

```python
@dataclass
class AuthResult:
    authenticated: bool          # 成功
    agent_id: str | None         # 已认证的 Agent
    scopes: list[str]            # 授予的权限范围
    expires_at: datetime | None  # 令牌过期时间
    metadata: dict[str, Any]     # 附加信息
    error: str | None            # 错误消息

    @property
    def is_valid(self) -> bool:
        """检查已认证且未过期"""
```

---

## CapABAC 授权

CapABAC 将基于能力的安全与基于属性的访问控制相结合:

- **能力**: 允许什么操作
- **属性**: 在什么条件下

### 核心概念

- **默认拒绝** — 除非明确允许
- **能力可以缩小范围后委托**
- **约束在授权时求值**

### 设置授权

```python
from gaiaagent.security.authz import (
    AuthorizationEngine, AgentPolicy, AuthorizationRule,
    Constraint, DelegationPolicy,
)

engine = AuthorizationEngine()

# 为研究 Agent 定义策略
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
            rate_limit=100,  # 每小时最多 100 次搜索
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

### 做出授权决策

```python
# 允许
result = engine.authorize(
    agent_id="aurc:gaia/researcher:v1.0",
    resource_type="web-search",
    action="execute",
    attributes={"domain": "mit.edu", "query_length": 50},
)
print(f"Allowed: {result.allowed}")  # True
print(f"Reason: {result.reason}")    # "Authorized: 'execute' on 'web-search'"

# 被约束拒绝
result = engine.authorize(
    agent_id="aurc:gaia/researcher:v1.0",
    resource_type="web-search",
    action="execute",
    attributes={"domain": "suspicious-site.com", "query_length": 50},
)
print(f"Allowed: {result.allowed}")  # False (domain doesn't match *.edu/*.gov)

# 被速率限制拒绝
# 100 次请求后，下一次被拒绝
```

### 约束操作符

| 操作符 | 描述 | 示例 |
|----------|-------------|---------|
| `eq` | 等于 | `Constraint("status", "eq", "active")` |
| `ne` | 不等于 | `Constraint("type", "ne", "admin")` |
| `gt` | 大于 | `Constraint("score", "gt", 0.5)` |
| `lt` | 小于 | `Constraint("size", "lt", 100)` |
| `gte` | 大于等于 | `Constraint("age", "gte", 18)` |
| `lte` | 小于等于 | `Constraint("length", "lte", 5000)` |
| `in` | 在列表中 | `Constraint("role", "in", ["user", "admin"])` |
| `not_in` | 不在列表中 | `Constraint("ip", "not_in", blocklist)` |
| `matches` | 正则匹配 | `Constraint("domain", "matches", r".*\.edu$")` |
| `contains` | 包含子串 | `Constraint("text", "contains", "keyword")` |

### 基于权限范围的授权

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

## 委托链

委托链记录从原始请求者到执行 Agent 的完整权限路径。这是 AURC 解决混淆代理问题的方案。

### 可视化示例

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

### 构建委托链

```python
from gaiaagent.security.delegation import DelegationBuilder

builder = DelegationBuilder()

# 第 1 跳：用户 → 编排器
builder.add_hop(
    from_agent="aurc:user/alice:v1.0",
    to_agent="aurc:gaia/orchestrator:v1.0",
    scopes=["research:read", "web:search", "admin"],
)

# 第 2 跳：编排器 → 研究员（缩小）
builder.add_hop(
    from_agent="aurc:gaia/orchestrator:v1.0",
    to_agent="aurc:gaia/researcher:v1.2",
    scopes=["research:read", "web:search"],  # 移除了 admin
)

# 第 3 跳：研究员 → MCP 工具
builder.add_hop(
    from_agent="aurc:gaia/researcher:v1.2",
    to_agent="mcp:web-search/server",
    scopes=["research:read"],  # 进一步缩小
)

chain = builder.build()
print(f"Depth: {builder.depth}")               # 3
print(f"Effective scopes: {builder.effective_scopes}")  # ["research:read"]
```

### 防止权限扩大

如果你尝试扩大权限，构建器会抛出 `ValueError`:

```python
builder = DelegationBuilder()
builder.add_hop(
    from_agent="aurc:user/alice:v1.0",
    to_agent="aurc:gaia/orchestrator:v1.0",
    scopes=["research:read"],
)

# 这会抛出 ValueError!
try:
    builder.add_hop(
        from_agent="aurc:gaia/orchestrator:v1.0",
        to_agent="aurc:gaia/researcher:v1.0",
        scopes=["research:read", "admin"],  # admin not in previous scopes!
    )
except ValueError as e:
    print(f"Cannot widen: {e}")
```

### 验证委托链

```python
from gaiaagent.security.delegation import DelegationValidator
from gaiaagent.core.message import MessageSecurity, DelegationHop

validator = DelegationValidator(max_depth=5)

# 构建安全上下文
security = MessageSecurity(
    scopes=["research:read"],
    delegation_chain=chain,
)

# 验证
result = validator.validate(security)
print(f"Valid: {result.valid}")             # True
print(f"Reason: {result.reason}")           # "Valid delegation chain: 3 hops"
print(f"Depth: {result.depth}")             # 3
print(f"Effective scopes: {result.effective_scopes}")

# 带所需权限验证
result = validator.validate_effective_scopes(
    security,
    required_scopes=["research:read"],
)
print(f"Sufficient: {result.valid}")  # True
```

### 验证检查项

| 检查项 | 描述 |
|------|-------------|
| **深度限制** | Chain length ≤ max_depth |
| **权限缩小** | Each hop's scopes ⊆ previous hop's scopes |
| **无循环委托** | No agent appears twice as `to_agent` |
| **时间戳顺序** | Each hop's timestamp ≥ previous hop's' |

### 链完整性哈希

```python
from gaiaagent.security.delegation import compute_chain_hash

chain_hash = compute_chain_hash(chain)
print(f"Chain hash: {chain_hash}")
# 存储此哈希以检测篡改
```

---

## 审计日志

审计日志提供所有安全相关事件的不可变、仅追加追踪。

### 创建审计条目

```python
from gaiaagent.security.audit import AuditLog, AuditAction, AuditSeverity

audit = AuditLog(max_entries=10000)

# 记录认证事件
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

# 记录授权决策
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

# 记录委托事件
audit.log(
    action=AuditAction.DELEGATION_CREATED,
    agent_id="aurc:gaia/orchestrator:v1.0",
    target_id="aurc:gaia/researcher:v1.2",
    details={"scopes": ["research:read"], "depth": 2},
)

# 记录跨协议桥接
audit.log(
    action=AuditAction.MESSAGE_BRIDGED,
    agent_id="aurc:gaia/researcher:v1.0",
    protocol="mcp/2025-06-18",
    details={"bridge": "mcp→aurc", "skill": "web-search"},
)
```

### 可用审计动作

| 类别 | 动作 |
|----------|---------|
| **Agent lifecycle** | `AGENT_REGISTERED`, `AGENT_UNREGISTERED`, `AGENT_STARTED`, `AGENT_STOPPED`, `AGENT_PAUSED`, `AGENT_RESUMED`, `AGENT_ERROR`, `AGENT_RECOVERED` |
| **Messages** | `MESSAGE_SENT`, `MESSAGE_RECEIVED`, `MESSAGE_ROUTED`, `MESSAGE_BRIDGED` |
| **Authentication** | `AUTH_SUCCESS`, `AUTH_FAILURE` |
| **Authorization** | `AUTHZ_GRANTED`, `AUTHZ_DENIED` |
| **Delegation** | `DELEGATION_CREATED`, `DELEGATION_VALIDATED`, `DELEGATION_REJECTED` |
| **Sessions** | `SESSION_CREATED`, `SESSION_CLOSED` |
| **Other** | `CONTEXT_MODIFIED`, `POLICY_CHANGED` |

### 查询审计日志

```python
# 按 Agent 查询
entries = audit.query(agent_id="aurc:gaia/researcher:v1.0")

# 按动作类型查询
bridge_events = audit.query(action=AuditAction.MESSAGE_BRIDGED)

# 按严重级别查询
warnings = audit.query(severity=AuditSeverity.WARNING)

# 按时间范围查询
from datetime import datetime, timezone, timedelta
since = datetime.now(timezone.utc) - timedelta(hours=1)
recent = audit.query(since=since)

# 按关联 ID 查询
correlated = audit.get_by_correlation("corr-xyz-789")

# 获取最近条目
last_50 = audit.get_recent(50)

# 获取统计
stats = audit.stats()
# {"auth_success": 150, "authz_granted": 320, "authz_denied": 12, ...}
```

### 合规导出

```python
# 导出为 JSON 文件
count = audit.export_to_file("audit_log_2026_06.json")
print(f"Exported {count} entries")

# 从文件导入
count = audit.import_from_file("audit_log_2026_06.json")
print(f"Imported {count} entries")
```

---

## 安全最佳实践

### 1. 始终使用委托链

```python
# 委派任务时始终构建正确的链
builder = DelegationBuilder()
builder.add_hop(from_agent=user_id, to_agent=orchestrator_id, scopes=user_scopes)
builder.add_hop(from_agent=orchestrator_id, to_agent=worker_id,
                scopes=narrowed_scopes)  # 始终缩小!
```

### 2. 设置速率限制

```python
AuthorizationRule(
    resource_type="expensive-api",
    actions=["execute"],
    rate_limit=50,  # 每小时 50 次调用
)
```

### 3. 对敏感操作使用时间窗口

```python
AuthorizationRule(
    resource_type="production-database",
    actions=["write"],
    time_window={"start": "09:00", "end": "17:00", "timezone": "UTC"},
)
```

### 4. 执行前验证

```python
# 执行委派任务前始终验证委托链
validator = DelegationValidator(max_depth=3)
result = validator.validate(message.security)
if not result.valid:
    raise PermissionError(result.reason)
```

### 5. 审计一切

```python
# 记录每个授权决策
audit.log(
    action=AuditAction.AUTHZ_GRANTED if authz_result.allowed else AuditAction.AUTHZ_DENIED,
    agent_id=agent_id,
    details={"resource": resource_type, "action": action, "reason": authz_result.reason},
)
```

### 6. 定期轮换 Key

```python
# 吊销旧 Key 并创建新 Key
auth.revoke_agent_keys("aurc:gaia/researcher:v1.0")
new_key = auth.create_key("aurc:gaia/researcher:v1.0", scopes=[...])
```

### 7. 使用最小权限

```python
# 只授予所需的权限
builder.add_hop(
    from_agent=orchestrator_id,
    to_agent=worker_id,
    scopes=["specific:read"],  # Not ["*"] or all scopes
)
```

---

## 威胁模型

### 威胁类别

| 威胁 | 风险 | AURC 缓解措施 |
|-------|------|-------------------|
| **未授权访问** | High | CapABAC default deny + API Key/JWT auth |
| **权限提升** | High | Scope narrowing enforcement in delegation chains |
| **混淆代理** | High | Delegation chain tracking across all bridges |
| **重放攻击** | Medium | Timestamp ordering + TTL in messages |
| **循环委托** | Medium | Circular detection in DelegationValidator |
| **链篡改** | Medium | Chain integrity hashing via `compute_chain_hash()` |
| **速率限制滥用** | Medium | Sliding-window rate limiter per agent/resource |
| **无限委托** | Medium | Max depth limit in DelegationValidator |
| **审计规避** | Low | Append-only audit log with ring buffer |

### 安全架构决策

1. **API Key 经 SHA-256 哈希** — 从不存储原始 Key
2. **JWT 令牌有过期时间** — 无无限期令牌
3. **委托权限是单调的** — 只能缩小
4. **审计日志仅追加** — 条目不可修改
5. **最大容量环形缓冲区** — 防止无限内存增长

---

*另请参阅: [架构深入解析](../architecture.md) | [桥接指南](bridges.md) | [API 参考](../api-reference.md)*
