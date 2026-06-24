# API Reference / API 参考

> **[← Back to README](../README.md)** | [Protocol Spec](../PROTOCOL.md) | [Architecture](architecture.md) | [Quick Start](guides/quickstart.md)
>
> Complete API documentation for the GaiaAgent / AURC Protocol SDK
> GaiaAgent / AURC 协议 SDK 完整 API 文档

---

## Table of Contents / 目录

1. [Core Types / 核心类型](#core-types--核心类型)
2. [AURCId / AURC ID](#aurcid--aurc-id)
3. [AgentDescriptor / Agent 描述文档](#agentdescriptor--agent-描述文档)
4. [AURCMessage / AURC 消息](#aurcmessage--aurc-消息)
5. [RuntimeHarness / 运行时 Harness](#runtimeharness--运行时-harness)
6. [MessageRouter / 消息路由器](#messagerouter--消息路由器)
7. [SessionManager / 会话管理器](#sessionmanager--会话管理器)
8. [Bridge APIs / 桥接器 API](#bridge-apis--桥接器-api)
9. [Security APIs / 安全 API](#security-apis--安全-api)
10. [Workflow APIs / 工作流 API](#workflow-apis--工作流-api)
11. [SDK Decorators / SDK 装饰器](#sdk-decorators--sdk-装饰器)
12. [CLI Commands / CLI 命令](#cli-commands--cli-命令)

---

## Core Types / 核心类型

Module: `gaiaagent.core.types`

### AgentState / Agent 状态

Agent lifecycle states / Agent 生命周期状态。

```python
class AgentState(str, Enum):
    REGISTERING = "registering"   # Agent registering / 注册中
    READY       = "ready"         # Waiting for tasks / 等待任务
    RUNNING     = "running"       # Executing / 执行中
    PAUSED      = "paused"        # Paused / 暂停
    FAILING     = "failing"       # Error recovery pending / 恢复待处理
    RECOVERING  = "recovering"    # Recovering / 恢复中
    COMPLETED   = "completed"     # Terminal: success / 终态：成功
    FAILED      = "failed"        # Terminal: failure / 终态：失败
    STOPPED     = "stopped"       # Terminal: stopped / 终态：已停止

    @property
    def is_terminal(self) -> bool:
        """COMPLETED, FAILED, or STOPPED / 是否为终态"""

    @property
    def is_active(self) -> bool:
        """RUNNING, FAILING, or RECOVERING / 是否在活跃工作"""
```

### MessageDirection / 消息方向

```python
class MessageDirection(str, Enum):
    REQUEST      = "request"       # Requires response / 需要响应
    RESPONSE     = "response"      # Reply to request / 对请求的回复
    NOTIFICATION = "notification"  # One-way / 单向通知
    STREAM       = "stream"        # Streaming data / 流式数据
    DELEGATION   = "delegation"    # Task delegation / 任务委派
    HANDOFF      = "handoff"       # Task ownership transfer / 任务移交
    HEARTBEAT    = "heartbeat"     # Keep-alive / 心跳保活
```

### ContextScope / 上下文作用域

```python
class ContextScope(str, Enum):
    SESSION = "session"  # Per-task / 单次任务
    AGENT   = "agent"    # Per-agent lifetime / Agent 生命周期
    SHARED  = "shared"   # Cross-agent / 跨 Agent 共享
    GLOBAL  = "global"   # System-wide / 全局
```

### Priority / 优先级

```python
class Priority(str, Enum):
    LOW      = "low"
    NORMAL   = "normal"
    HIGH     = "high"
    CRITICAL = "critical"
```

### HealthStatus / 健康状态

```python
class HealthStatus(str, Enum):
    HEALTHY   = "healthy"
    DEGRADED  = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN   = "unknown"
```

### RecoveryAction / 恢复动作

```python
class RecoveryAction(str, Enum):
    RETRY_WITH_BACKOFF  = "retry_with_backoff"    # Exponential backoff / 指数退避
    RETRY_ALTERNATIVE   = "retry_alternative"      # Try alternative skill / 尝试替代技能
    COMPACT_AND_RETRY   = "compact_and_retry"      # Summarize context, retry / 压缩上下文重试
    REFRESH_AND_RETRY   = "refresh_and_retry"      # Refresh auth, retry / 刷新认证重试
    ESCALATE            = "escalate"                # Human operator / 人类操作员
    FAIL                = "fail"                    # Give up / 放弃
```

### AuthMethod / 认证方式

```python
class AuthMethod(str, Enum):
    API_KEY = "api_key"
    OAUTH2  = "oauth2"
    MTLS    = "mtls"
    JWT     = "jwt"
```

### TransportType / 传输方式

```python
class TransportType(str, Enum):
    HTTP      = "http"
    WEBSOCKET = "websocket"
    STDIO     = "stdio"
    GRPC      = "grpc"
```

### Data Models / 数据模型

```python
class ResourceLimits(BaseModel):
    max_memory_mb: int = 1024
    max_cpu_percent: float = 100.0
    max_concurrency: int = 10
    timeout_seconds: int = 3600

class ResourceMetrics(BaseModel):
    memory_mb: float = 0.0
    cpu_percent: float = 0.0
    active_tasks: int = 0
    total_tasks_completed: int = 0
    total_tasks_failed: int = 0
    uptime_seconds: float = 0.0

class HealthReport(BaseModel):
    agent_id: str
    status: HealthStatus = HealthStatus.UNKNOWN
    state: AgentState = AgentState.READY
    metrics: ResourceMetrics
    last_error: str | None = None
    timestamp: datetime

class RecoveryPolicy(BaseModel):
    max_retries: int = 3
    backoff_ms: list[int] = [1000, 5000, 15000]
    strategies: list[RecoveryStrategy] = []

class RecoveryStrategy(BaseModel):
    trigger: str                              # Error type / 错误类型
    action: RecoveryAction                    # Recovery action / 恢复动作
    alternatives: list[str] = []              # Fallback skills / 备选技能
    escalate_to: str | None = None            # Escalation target / 升级目标
```

---

## AURCId / AURC ID

Module: `gaiaagent.core.identity`

```python
class AURCId(BaseModel):
    raw: str          # Full string: "aurc:gaia/researcher:v1.2"
    namespace: str    # "gaia"
    name: str         # "researcher"
    version: str      # "v1.2"
```

### Methods / 方法

| Method / 方法 | Signature / 签名 | Description / 描述 |
|--------|-----------|-------------|
| `parse` | `AURCId.parse(id_string: str) → AURCId` | Parse and validate / 解析并验证 |
| `matches` | `matches(pattern: str) → bool` | Glob-like matching / 通配符匹配 |

**Format / 格式:** `aurc:{namespace}/{name}:{version}`

**Validation regex / 验证正则:**
```
^aurc:[a-z0-9][a-z0-9._-]{0,63}/[a-z0-9][a-z0-9._-]{0,127}:v\d+(?:\.\d+){0,2}$
```

**Examples / 示例:**
```python
aid = AURCId.parse("aurc:gaia/researcher:v1.2")
aid.matches("aurc:gaia/*")             # True
aid.matches("aurc:*/researcher:v1.*")  # True
aid.matches("aurc:other/*")            # False
```

---

## AgentDescriptor / Agent 描述文档

Module: `gaiaagent.core.identity`

```python
class AgentDescriptor(BaseModel):
    schema_version: str = "aurc://spec/v0.1/agent-descriptor.json"
    aurc_id: str                                    # Validated AURC ID
    display_name: str                                # Human-readable name / 人类可读名
    description: str = ""                            # Agent description / Agent 描述
    version: str = "0.1.0"                           # Software version / 软件版本
    author: str = ""                                 # Author / 作者
    license: str = "AGPL-3.0"                        # License / 许可证
    capabilities: Capabilities                       # Skills provided/consumed / 技能
    protocols: ProtocolSupport                       # Supported protocols / 协议支持
    runtime: RuntimeRequirements                     # Runtime needs / 运行时需求
    auth: AuthDeclaration                            # Auth methods / 认证方式
    tags: list[str] = []                             # Searchable tags / 标签
    metadata: dict[str, Any] = {}                    # Arbitrary metadata / 元数据
```

### Sub-Models / 子模型

```python
class SkillDeclaration(BaseModel):
    skill_id: str           # Unique ID / 唯一标识
    name: str               # Human-readable / 人类可读
    description: str = ""
    input_schema: InputOutputSchema
    output_schema: InputOutputSchema
    tags: list[str] = []

class Capabilities(BaseModel):
    provides: list[SkillDeclaration] = []   # Skills offered / 提供的技能
    consumes: list[str] = []                # Skills needed / 需要的技能
    def has_skill(skill_id: str) -> bool
    def get_skill(skill_id: str) -> SkillDeclaration | None

class ProtocolSupport(BaseModel):
    native: str = "aurc/0.1"
    bridges: list[str] = []
    def supports(protocol: str) -> bool

class RuntimeRequirements(BaseModel):
    min_memory_mb: int = 256
    max_concurrency: int = 10
    supports_streaming: bool = True
    supports_pause: bool = False
    timeout_seconds: int = 3600

class AuthDeclaration(BaseModel):
    methods: list[str] = ["api_key"]
    scopes: list[str] = []
```

### Methods / 方法

| Method | Signature | Description |
|--------|-----------|-------------|
| `parsed_id` | `@property → AURCId` | Get parsed ID / 获取解析的 ID |
| `to_registry_entry` | `() → dict` | Registry-compatible dict / 注册中心兼容字典 |

---

## AURCMessage / AURC 消息

Module: `gaiaagent.core.message`

### AURCMessage / AURC 消息

```python
class AURCMessage(BaseModel):
    aurc_version: str = "0.1"
    message_id: str            # Auto-generated UUID / 自动生成的 UUID
    correlation_id: str | None # Cross-protocol correlation / 跨协议关联
    trace_id: str | None       # Distributed tracing / 分布式追踪
    timestamp: datetime        # UTC creation time / UTC 创建时间
    source: str                # Source agent AURC ID / 源 Agent ID
    target: str                # Target agent AURC ID / 目标 Agent ID
    type: MessageDirection     # Message type / 消息类型
    body: MessageBody          # Payload / 载荷
    protocol_context: BridgeContext   # Bridge tracking / 桥接追踪
    session: SessionInfo              # Conversation tracking / 会话追踪
    routing: RoutingInfo              # Routing metadata / 路由元数据
    security: MessageSecurity         # Security context / 安全上下文
```

### Methods / 方法

| Method | Signature | Description / 描述 |
|--------|-----------|-------------|
| `create_response` | `(result, error) → AURCMessage` | Create response / 创建响应 |
| `create_stream_chunk` | `(data, chunk_index, total_chunks, is_final) → AURCMessage` | Stream chunk / 流式块 |
| `create_notification` | `(event, data) → AURCMessage` | Notification / 通知 |

### Sub-Models / 子模型

```python
class BridgeContext(BaseModel):
    origin_protocol: str = "aurc"
    bridged_from: str | None = None
    bridge_chain: list[str] = []        # ["mcp→aurc", "aurc→a2a"]
    @property is_bridged: bool
    @property hop_count: int
    def add_hop(from_proto, to_proto) -> BridgeContext

class SessionInfo(BaseModel):
    session_id: str             # Auto-generated / 自动生成
    conversation_id: str | None
    turn: int = 0
    parent_message_id: str | None

class DelegationHop(BaseModel):
    from_agent: str             # Delegating agent / 委托方
    to_agent: str               # Receiving agent / 被委托方
    scopes: list[str]           # Granted scopes / 授予的权限
    timestamp: datetime

class MessageSecurity(BaseModel):
    auth_token_ref: str | None
    scopes: list[str]
    delegation_chain: list[DelegationHop]
    def validate_delegation_chain() -> bool

class RoutingInfo(BaseModel):
    ttl_hops: int = 5
    priority: Priority = Priority.NORMAL
    timeout_ms: int = 30000
    reply_to: str | None

class MessageBody(BaseModel):
    method: str | None          # "invoke", "query", etc.
    skill: str | None           # Target skill / 目标技能
    params: dict[str, Any]      # Parameters / 参数
    result: Any                 # Response result / 响应结果
    error: ErrorInfo | None     # Error details / 错误详情
    event: str | None           # Notification event / 通知事件
    chunk_index: int | None     # Stream chunk index / 流式块索引
    total_chunks: int | None    # Total chunks / 总块数
    data: Any                   # Chunk/event data / 块/事件数据
    is_final: bool = False      # Final stream chunk / 最终流式块
    capabilities_required: list[str]
    metadata: dict[str, Any]

class ErrorInfo(BaseModel):
    code: str                   # Error code / 错误代码
    message: str                # Human-readable / 人类可读
    details: dict[str, Any]
    recoverable: bool = True
    suggested_recovery: str | None
```

---

## RuntimeHarness / 运行时 Harness

Module: `gaiaagent.harness.lifecycle`

```python
class RuntimeHarness:
    def __init__(
        self,
        recovery_policy: RecoveryPolicy | None = None,
        resource_limits: ResourceLimits | None = None,
    )
```

### Methods / 方法

| Method / 方法 | Signature / 签名 | Description / 描述 |
|--------|-----------|-------------|
| `register` | `async (descriptor: AgentDescriptor) → str` | Register agent / 注册 Agent |
| `unregister` | `async (agent_id: str) → None` | Unregister agent / 注销 Agent |
| `start` | `async (agent_id, task_params?, *, new_task=False) → str` | Start task / 启动任务 |
| `pause` | `async (agent_id: str, reason: str = "") → None` | Pause agent / 暂停 Agent |
| `resume` | `async (agent_id: str) → None` | Resume agent / 恢复 Agent |
| `stop` | `async (agent_id: str, graceful: bool = True) → None` | Stop agent / 停止 Agent |
| `complete` | `async (agent_id: str) → None` | Mark completed / 标记完成 |
| `restart` | `async (agent_id: str) → str` | Restart agent / 重启 Agent |
| `report_error` | `async (agent_id: str, error: str) → bool` | Report error, trigger recovery / 报告错误 |
| `health_check` | `async (agent_id: str) → HealthReport` | Agent health / Agent 健康 |
| `health_check_all` | `async () → list[HealthReport]` | All agents health / 所有 Agent 健康 |
| `add_listener` | `(listener: StateListener) → None` | Add state listener / 添加状态监听器 |
| `remove_listener` | `(listener: StateListener) → None` | Remove listener / 移除监听器 |
| `get_agent` | `(agent_id: str) → AgentInstance \| None` | Get agent instance / 获取实例 |
| `list_agents` | `(state: AgentState \| None) → list[AgentInstance]` | List agents / 列出 Agent |
| `shutdown` | `async (graceful: bool = True) → None` | Shutdown all / 关闭所有 |
| `agent_count` | `@property → int` | Number of agents / Agent 数量 |

### StateListener Type / StateListener 类型

```python
StateListener = Callable[[str, AgentState, AgentState], Any]
# (agent_id, old_state, new_state) → Any
```

### StateTransitionError / 状态转换错误

```python
class StateTransitionError(Exception):
    current: AgentState
    target: AgentState
    agent_id: str
```

---

## MessageRouter / 消息路由器

Module: `gaiaagent.bus.router`

```python
class MessageRouter:
    def __init__(self)
```

### Methods / 方法

| Method | Signature | Description / 描述 |
|--------|-----------|-------------|
| `register_handler` | `(agent_id: str, handler: MessageHandler) → None` | Register handler / 注册处理函数 |
| `unregister_handler` | `(agent_id: str) → None` | Remove handler / 移除处理函数 |
| `register_bridge_forwarder` | `(protocol: str, forwarder: MessageHandler) → None` | Bridge forwarder / 桥接转发器 |
| `subscribe` | `(group_id: str, handler: MessageHandler) → None` | Subscribe to group / 订阅组 |
| `unsubscribe` | `(group_id: str, handler: MessageHandler) → None` | Unsubscribe / 取消订阅 |
| `route` | `async (message: AURCMessage) → Any` | Route message / 路由消息 |
| `has_handler` | `(agent_id: str) → bool` | Check handler / 检查处理函数 |
| `handler_count` | `@property → int` | Handler count / 处理函数数量 |
| `stats` | `@property → RouterStats` | Router statistics / 路由统计 |
| `dead_letter_queue` | `@property → list[AURCMessage]` | Undeliverable messages / 不可投递消息 |
| `clear_dead_letters` | `() → int` | Clear dead letters / 清除死信 |

### RouterStats / 路由统计

```python
class RouterStats:
    total_routed: int
    direct: int
    bridged: int
    broadcast: int
    dead_lettered: int
    dropped: int
    errors: int
    def to_dict() → dict[str, int]
    def reset() → None
```

---

## SessionManager / 会话管理器

Module: `gaiaagent.bus.session`

```python
class SessionManager:
    def __init__(self, max_sessions: int = 10000)
```

### Methods / 方法

| Method | Signature | Description / 描述 |
|--------|-----------|-------------|
| `create_session` | `(initiator, conversation_id?, metadata?) → SessionState` | Create session / 创建会话 |
| `close_session` | `(session_id: str) → None` | Close session / 关闭会话 |
| `get_session` | `(session_id: str) → SessionState \| None` | Get session / 获取会话 |
| `get_conversation_sessions` | `(conversation_id: str) → list[SessionState]` | Get by conversation / 按对话获取 |
| `advance_turn` | `(session_id, participant?) → int` | Next turn / 下一轮 |
| `set_context` | `(session_id, key, value) → None` | Set context / 设置上下文 |
| `get_context` | `(session_id, key, default?) → Any` | Get context / 获取上下文 |
| `get_active_sessions` | `() → list[SessionState]` | Active sessions / 活跃会话 |
| `get_sessions_by_participant` | `(agent_id) → list[SessionState]` | By participant / 按参与者 |
| `cleanup_stale` | `(max_age_seconds=3600) → int` | Cleanup / 清理 |
| `session_count` | `@property → int` | Total sessions / 总会话数 |
| `active_count` | `@property → int` | Active count / 活跃数 |

---

## Bridge APIs / 桥接器 API

Module: `gaiaagent.bridges.base`, `gaiaagent.bridges.a2a`, `gaiaagent.bridges.acp`

### ProtocolBridge (Interface / 接口)

```python
class ProtocolBridge(Protocol):
    source_protocol: str
    def can_bridge(source: str, target: str) → bool
    async def translate_to_aurc(external_message: Any) → AURCMessage
    async def translate_from_aurc(aurc_message: AURCMessage) → Any
    async def map_capabilities(external_caps: list[dict]) → list[dict]
```

### MCPBridge

```python
class MCPBridge:
    source_protocol = "mcp/2025-06-18"
    # Implements ProtocolBridge / 实现 ProtocolBridge
```

### A2ABridge

```python
class A2ABridge:
    source_protocol = "a2a/1.0"
    # Implements ProtocolBridge / 实现 ProtocolBridge
    def map_agent_card(agent_card: dict) → dict
```

### ACPBridge

Module: `gaiaagent.bridges.acp`

```python
class ACPBridge:
    source_protocol = "acp/1.0"
    # Implements ProtocolBridge / 实现 ProtocolBridge
    # ACP invoke      → AURC delegation
    # ACP cancel      → AURC notification (task_cancelled)
    # ACP get-task    → AURC request (query_task_status)
    # ACP list-tasks  → AURC request (list_tasks)
    # ACP set-task    → AURC notification (task_state_updated)
    def map_agent_card(agent_descriptor: dict) → dict
```

### BridgeRegistry

```python
class BridgeRegistry:
    def __init__(self)
    def register(bridge: ProtocolBridge) → None
    def unregister(protocol: str) → None
    def get_bridge(protocol: str) → ProtocolBridge | None
    def find_bridge(source: str, target: str) → ProtocolBridge | None
    def list_protocols() → list[str]
    count: @property → int
```

---

## Security APIs / 安全 API

### Authentication / 认证

Module: `gaiaagent.security.auth`

```python
class APIKeyAuthenticator:
    def create_key(agent_id, scopes?, prefix="aurc") → str
    def authenticate(raw_key: str) → AuthResult
    def revoke_key(raw_key: str) → bool
    def revoke_agent_keys(agent_id: str) → int
    key_count: @property → int

class JWTAuthenticator:
    def __init__(self, secret: str | None = None)
    def create_token(agent_id, scopes?, expires_in_seconds=3600) → str
    def authenticate(token: str) → AuthResult

class MultiAuthenticator:
    def add_api_key() → APIKeyAuthenticator
    def add_jwt(secret?) → JWTAuthenticator
    def authenticate(method: str, credential: str) → AuthResult
    def authenticate_any(credentials: dict[str, str]) → AuthResult

class AuthResult:
    authenticated: bool
    agent_id: str | None
    scopes: list[str]
    expires_at: datetime | None
    metadata: dict[str, Any]
    error: str | None
    is_valid: @property → bool    # authenticated AND not expired
```

### Authorization / 授权

Module: `gaiaagent.security.authz`

```python
class AuthorizationEngine:
    def set_policy(agent_id: str, policy: AgentPolicy) → None
    def get_policy(agent_id: str) → AgentPolicy | None
    def remove_policy(agent_id: str) → bool
    def authorize(agent_id, resource_type, action, attributes?) → AuthzResult
    def authorize_scopes(agent_id, resource_type, action,
                         required_scopes, granted_scopes, attributes?) → AuthzResult

class AgentPolicy:
    agent_id: str
    rules: list[AuthorizationRule]
    delegation: DelegationPolicy

class AuthorizationRule:
    resource_type: str
    actions: list[str]
    constraints: list[Constraint]
    time_window: dict[str, str] | None
    rate_limit: int | None

class Constraint:
    field: str
    operator: str    # eq, ne, gt, lt, gte, lte, in, not_in, matches, contains
    value: Any
    def evaluate(actual_value: Any) → bool

class DelegationPolicy:
    allowed: bool = True
    max_depth: int = 3
    scope_reduction_required: bool = True

class AuthzResult:
    allowed: bool
    reason: str
    matched_rule: AuthorizationRule | None
```

### Delegation / 委托

Module: `gaiaagent.security.delegation`

```python
class DelegationValidator:
    def __init__(self, max_depth=5, require_signatures=False)
    def validate(security: MessageSecurity) → DelegationResult
    def validate_effective_scopes(security, required_scopes) → DelegationResult

class DelegationBuilder:
    def add_hop(from_agent, to_agent, scopes) → DelegationBuilder  # chainable
    def build() → list[DelegationHop]
    depth: @property → int
    effective_scopes: @property → list[str]

class DelegationResult:
    valid: bool
    reason: str
    depth: int
    failed_hop: int | None
    effective_scopes: list[str]

def compute_chain_hash(chain: list[DelegationHop]) → str
```

### Audit / 审计

Module: `gaiaagent.security.audit`

```python
class AuditLog:
    def __init__(self, max_entries=10000)
    def log(action, agent_id?, target_id?, message_id?, correlation_id?,
              protocol?, severity?, details?) → AuditEntry
    def query(action?, agent_id?, target_id?, severity?, protocol?,
              correlation_id?, since?, until?, limit=100) → list[AuditEntry]
    def get_recent(count=50) → list[AuditEntry]
    def get_by_correlation(correlation_id) → list[AuditEntry]
    def stats() → dict[str, int]
    def export_to_file(path) → int
    def import_from_file(path) → int
    def clear() → int
    count: @property → int

class AuditAction(str, Enum):
    # 22 action types covering: agent lifecycle, messages, auth, delegation, sessions

class AuditSeverity(str, Enum):
    INFO, WARNING, ERROR, CRITICAL
```

---

## Workflow APIs / 工作流 API

Module: `gaiaagent.workflows.orchestrator`

### PromptChain

```python
class PromptChain:
    def __init__(self, steps: list[SkillHandler], step_names: list[str] | None)
    async def execute(initial_input: Any) → WorkflowResult
```

### IntelligentRouter

```python
class IntelligentRouter:
    def add_route(name: str, handler: SkillHandler) → None
    def set_classifier(classifier: Callable[[Any], Awaitable[str]]) → None
    async def execute(input_data: Any) → WorkflowResult
```

### ParallelFanOut

```python
class ParallelFanOut:
    def __init__(self, tasks: list[SkillHandler], mode="all", task_names=None)
    async def execute(input_data: Any) → WorkflowResult
    # mode: "all" | "first" | "vote"
```

### OrchestratorWorkers

```python
class OrchestratorWorkers:
    def __init__(
        self,
        orchestrator: Callable[[Any], Awaitable[list[dict]]],
        workers: dict[str, SkillHandler],
        synthesizer: Callable[[list[Any]], Awaitable[Any]] | None,
    )
    async def execute(input_data: Any) → WorkflowResult
```

### EvaluatorOptimizer

```python
class EvaluatorOptimizer:
    def __init__(
        self,
        generator: Callable[[Any, str | None], Awaitable[Any]],
        evaluator: Callable[[Any], Awaitable[EvalResult]],
        max_iterations: int = 5,
        quality_threshold: float = 0.8,
    )
    async def execute(input_data: Any) → WorkflowResult

class EvalResult:
    score: float        # 0.0 to 1.0
    passed: bool
    feedback: str
    details: dict[str, Any]
```

### DynamicWorkflowEngine

```python
class DynamicWorkflowEngine:
    async def chain(steps, initial_input, **kwargs) → WorkflowResult
    async def route(input_data, routes, classifier) → WorkflowResult
    async def parallel(tasks, input_data, mode="all", **kwargs) → WorkflowResult
    async def orchestrate(orchestrator, workers, input_data, **kwargs) → WorkflowResult
    async def optimize(generator, evaluator, input_data, **kwargs) → WorkflowResult
```

### WorkflowResult

```python
class WorkflowResult:
    success: bool
    output: Any
    steps_completed: int
    total_steps: int
    errors: list[str]
    metadata: dict[str, Any]
```

---

## SDK Decorators / SDK 装饰器

Module: `gaiaagent.sdk.decorators`

### @aurc_agent

```python
def aurc_agent(
    id: str,                              # AURC ID (required)
    display_name: str | None = None,      # Human-readable name
    description: str = "",
    version: str = "0.1.0",
    author: str = "",
    license: str = "AGPL-3.0",
    protocols: list[str] | None = None,   # External protocols
    tags: list[str] | None = None,
    consumes: list[str] | None = None,    # External skills needed
    max_concurrency: int = 10,
    supports_streaming: bool = True,
    supports_pause: bool = False,
    timeout_seconds: int = 3600,
    auth_methods: list[str] | None = None,
) → Callable[[type], type]
```

**Effects / 效果:**
- Scans class for `@skill` methods / 扫描类中的 `@skill` 方法
- Builds `AgentDescriptor` automatically / 自动构建 `AgentDescriptor`
- Attaches `_aurc_descriptor` and `_aurc_skills` to class / 附加到类
- Adds `aurc_descriptor` property / 添加 `aurc_descriptor` 属性

### @skill

```python
def skill(
    skill_id: str | None = None,       # Defaults to method name
    name: str | None = None,            # Defaults to method name
    description: str = "",
    tags: list[str] | None = None,
) → Callable[[F], F]
```

**Effects / 效果:**
- Stores `SkillMetadata` on function / 在函数上存储元数据
- Extracts input schema from type hints / 从类型提示提取输入模式
- Extracts output schema from return type / 从返回类型提取输出模式
- Wraps function with logging / 用日志包装函数

### Example / 示例

```python
@aurc_agent(
    id="aurc:myproject/agent:v1.0",
    display_name="My Agent",
    protocols=["mcp/2025-06-18"],
    tags=["custom"],
)
class MyAgent:
    @skill("my-skill", description="Does something")
    async def my_skill(self, input: str, count: int = 1) -> dict:
        return {"result": input * count}
```

---

## Claude Integration / Claude 集成

Module: `gaiaagent.integrations.claude`

### ClaudeLLM

```python
class ClaudeLLM:
    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: str | None = None,       # Falls back to ANTHROPIC_API_KEY env
        max_tokens: int = 4096,
        system_prompt: str | None = None,
    )
    async def ask(prompt, tools?, system?, max_tokens?) → ClaudeResponse
    async def agentic_loop(prompt, tools?, max_turns=10, system?) → ClaudeResponse
    async def converse(message, tools?, system?) → ClaudeResponse
    def clear_history() → None
```

### ClaudeTool

```python
class ClaudeTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable | None
    def to_claude_format() → dict
    @classmethod from_aurc_skill(skill_declaration, handler?) → ClaudeTool
```

### ClaudeResponse

```python
class ClaudeResponse:
    text: str
    tool_calls: list[ClaudeToolCall]
    stop_reason: str        # "end_turn", "error", "max_turns"
    usage: dict[str, int]   # {"input_tokens": N, "output_tokens": N}
    has_tool_calls: @property → bool
```

### ClaudeAgent

```python
class ClaudeAgent:
    def __init__(self, model?, api_key?, system_prompt?)
    claude: ClaudeLLM       # Access to Claude / 访问 Claude
    def get_claude_tools() → list[ClaudeTool]
```

---

## Observability APIs / 可观测性 API

Module: `gaiaagent.observability`

### HealthDashboard

```python
class HealthDashboard:
    def __init__(harness: RuntimeHarness, audit: AuditLog | None = None,
                 router: MessageRouter | None = None)
    def get_system_health() → dict          # health counts + state dist + router stats
    def get_agent_health(agent_id) → dict | None
    def get_all_agents() → list[dict]
    def get_audit_summary() → dict
    def get_metrics() → dict                # aggregate resource + router + audit metrics
    def get_dashboard_html() → str          # self-contained HTML page
```

### DashboardAPI (ASGI)

```python
class DashboardAPI:
    def __init__(dashboard: HealthDashboard)
    async def handle_request(scope, receive, send) → None
    # Routes / 路由:
    #   GET /dashboard        HTML dashboard / HTML 仪表盘
    #   GET /api/health       JSON system health / JSON 系统健康
    #   GET /api/agents       JSON agent list / JSON Agent 列表
    #   GET /api/agents/{id}  JSON single agent / JSON 单个 Agent
    #   GET /api/audit        JSON audit summary / JSON 审计摘要
    #   GET /api/metrics      JSON metrics / JSON 指标
    #   GET /metrics          Prometheus text exposition / Prometheus 文本指标
    #   GET /api/stats        JSON combined statistics / JSON 组合统计
```

### PrometheusMetricsExporter

```python
class PrometheusMetricsExporter:
    def __init__(dashboard: HealthDashboard, *, namespace="aurc")
    content_type: @property → str           # "text/plain; version=0.0.4; charset=utf-8"
    def render() → str                       # Prometheus text exposition (for /metrics)
```

Emits: `aurc_up`, `aurc_agents_total`, `aurc_active_tasks`, `aurc_tasks_completed_total`,
`aurc_tasks_failed_total`, `aurc_error_rate`, `aurc_memory_mb`, `aurc_cpu_percent`,
`aurc_audit_entries_total`, `aurc_messages_total{route=...}`, `aurc_router_errors_total`,
`aurc_agent_state{state=...}`, `aurc_health{status=...}`, `aurc_audit_events_total{action=...}`.

### BridgeTraceRecorder / TraceSpan

```python
class TraceSpan:                              # one recorded hop / 一个记录的跳
    correlation_id: str | None
    message_id: str
    source: str; target: str; type: str
    origin_protocol: str
    bridge_chain: list[str]
    hop_count: int
    timestamp: str
    def to_log_line() → str                  # single structured log line / 单行结构化日志
    def to_dict() → dict

class BridgeTraceRecorder:
    def __init__(max_traces=10_000)
    def record(message: AURCMessage) → TraceSpan        # record a message hop / 记录消息跳
    def record_span(span: TraceSpan) → TraceSpan        # record a synthetic span / 记录合成 span
    def get_trace(correlation_id) → list[TraceSpan]     # all hops for a correlation / 该关联所有跳
    def all_traces() → dict[str | None, list[TraceSpan]]
    def render_trace(correlation_id) → str              # multi-line trace log / 多行追踪日志
    trace_count: @property → int
    span_count: @property → int
    def clear() → int
```

> See `docs/examples/observability_demo.py` for a runnable end-to-end example
> that exercises all three bridges under a shared `correlation_id` and renders
> Prometheus metrics + a bridge-chain trace.
>
> 参见 `docs/examples/observability_demo.py`：一个可运行的端到端示例，在共享
> `correlation_id` 下驱动三个桥接，并渲染 Prometheus 指标与桥接链追踪。

---

## CLI Commands / CLI 命令

Module: `gaiaagent.cli`

### aurc serve

Start the AURC harness with HTTP transport. Optionally enable the health dashboard.

启动带 HTTP 传输的 AURC Harness。可选启用健康仪表盘。

```bash
aurc serve [--host HOST] [--port PORT] [--dashboard]

# Options / 选项:
#   --host       Bind address (default: 0.0.0.0) / 绑定地址
#   --port       Port number (default: 8080) / 端口号
#   --dashboard  Enable health dashboard / 启用健康仪表盘
#   -q, --quiet  Machine-readable output / 机器可读输出
```

### aurc version

Show version information.

显示版本信息。

```bash
aurc version
# Output: gaiaagent v0.1.0 (AURC Protocol v0.1)
```

### aurc info

Show system and configuration info.

显示系统和配置信息。

```bash
aurc info
# Output: Python version, installed bridges, AURC version
```

### aurc validate

Validate an Agent Descriptor file.

验证 Agent 描述文档文件。

```bash
aurc validate <path-to-descriptor.json>
# Validates AURC ID format, schema, capabilities
```

### aurc bridge test

Test a protocol bridge translation using built-in sample messages (no live server required).

使用内置示例消息测试协议桥接器翻译（无需真实服务器）。

```bash
aurc bridge test --protocol mcp
aurc bridge test --protocol a2a
aurc bridge test --protocol acp

# Options / 选项:
#   --protocol  Protocol to test: mcp, a2a, or acp (required)
#   -q, --quiet Machine-readable JSON output / 机器可读 JSON 输出
#
# Runs three steps per protocol:
#   1. translate_to_aurc   (external → AURC)
#   2. translate_from_aurc (AURC → external)
#   3. map_capabilities     (external caps → AURC skills)
```

### aurc registry export

Export the local registry to JSON (printed to stdout).

将本地注册中心导出为 JSON（输出到标准输出）。

```bash
aurc registry export
```

---

*See also / 另请参阅: [Architecture](architecture.md) | [Quickstart](guides/quickstart.md) | [Protocol Spec](../PROTOCOL.md)*
