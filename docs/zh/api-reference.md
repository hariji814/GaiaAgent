# API 参考

> 🌐 [English](../en/api-reference.md)
> **[← 返回 README](../../README.zh.md)** | [协议规范](../../PROTOCOL.zh.md) | [架构](architecture.md) | [快速开始](guides/quickstart.md)
>
> GaiaAgent / AURC 协议 SDK 完整 API 文档

---

## 目录

1. [核心类型](#核心类型)
2. [AURC ID](#aurc-id)
3. [Agent 描述文档](#agent-描述文档)
4. [AURC 消息](#aurc-消息)
5. [运行时 Harness](#运行时-harness)
6. [消息路由器](#消息路由器)
7. [会话管理器](#会话管理器)
8. [桥接器 API](#桥接器-api)
9. [安全 API](#安全-api)
10. [工作流 API](#工作流-api)
11. [SDK 装饰器](#sdk-装饰器)
12. [CLI 命令](#cli-命令)

---

## 核心类型

模块：`gaiaagent.core.types`

### AgentState

Agent 生命周期状态。

```python
class AgentState(str, Enum):
    REGISTERING = "registering"   # 注册中
    READY       = "ready"         # 等待任务
    RUNNING     = "running"       # 执行中
    PAUSED      = "paused"        # 暂停
    FAILING     = "failing"       # 恢复待处理
    RECOVERING  = "recovering"    # 恢复中
    COMPLETED   = "completed"     # 终态：成功
    FAILED      = "failed"        # 终态：失败
    STOPPED     = "stopped"       # 终态：已停止

    @property
    def is_terminal(self) -> bool:
        """是否为终态"""

    @property
    def is_active(self) -> bool:
        """是否在活跃工作"""
```

### MessageDirection

```python
class MessageDirection(str, Enum):
    REQUEST      = "request"       # 需要响应
    RESPONSE     = "response"      # 对请求的回复
    NOTIFICATION = "notification"  # 单向通知
    STREAM       = "stream"        # 流式数据
    DELEGATION   = "delegation"    # 任务委派
    HANDOFF      = "handoff"       # 任务移交
    HEARTBEAT    = "heartbeat"     # 心跳保活
```

### ContextScope

```python
class ContextScope(str, Enum):
    SESSION = "session"  # 单次任务
    AGENT   = "agent"    # Agent 生命周期
    SHARED  = "shared"   # 跨 Agent 共享
    GLOBAL  = "global"   # 全局
```

### Priority

```python
class Priority(str, Enum):
    LOW      = "low"
    NORMAL   = "normal"
    HIGH     = "high"
    CRITICAL = "critical"
```

### HealthStatus

```python
class HealthStatus(str, Enum):
    HEALTHY   = "healthy"
    DEGRADED  = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN   = "unknown"
```

### RecoveryAction

```python
class RecoveryAction(str, Enum):
    RETRY_WITH_BACKOFF  = "retry_with_backoff"    # 指数退避
    RETRY_ALTERNATIVE   = "retry_alternative"      # 尝试替代技能
    COMPACT_AND_RETRY   = "compact_and_retry"      # 压缩上下文重试
    REFRESH_AND_RETRY   = "refresh_and_retry"      # 刷新认证重试
    ESCALATE            = "escalate"                # 人类操作员
    FAIL                = "fail"                    # 放弃
```

### AuthMethod

```python
class AuthMethod(str, Enum):
    API_KEY = "api_key"
    OAUTH2  = "oauth2"
    MTLS    = "mtls"
    JWT     = "jwt"
```

### TransportType

```python
class TransportType(str, Enum):
    HTTP      = "http"
    WEBSOCKET = "websocket"
    STDIO     = "stdio"
    GRPC      = "grpc"
```

### 数据模型

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
    trigger: str                              # 错误类型
    action: RecoveryAction                    # 恢复动作
    alternatives: list[str] = []              # 备选技能
    escalate_to: str | None = None            # 升级目标
```

---

## AURC ID

模块：`gaiaagent.core.identity`

```python
class AURCId(BaseModel):
    raw: str          # Full string: "aurc:gaia/researcher:v1.2"
    namespace: str    # "gaia"
    name: str         # "researcher"
    version: str      # "v1.2"
```

### 方法

| 方法 | 签名 | 描述 |
|--------|-----------|-------------|
| `parse` | `AURCId.parse(id_string: str) → AURCId` | 解析并验证 |
| `matches` | `matches(pattern: str) → bool` | 通配符匹配 |

**格式：** `aurc:{namespace}/{name}:{version}`

**验证正则：**
```
^aurc:[a-z0-9][a-z0-9._-]{0,63}/[a-z0-9][a-z0-9._-]{0,127}:v\d+(?:\.\d+){0,2}$
```

**示例：**
```python
aid = AURCId.parse("aurc:gaia/researcher:v1.2")
aid.matches("aurc:gaia/*")             # True
aid.matches("aurc:*/researcher:v1.*")  # True
aid.matches("aurc:other/*")            # False
```

---

## Agent 描述文档

模块：`gaiaagent.core.identity`

```python
class AgentDescriptor(BaseModel):
    schema_version: str = "aurc://spec/v0.1/agent-descriptor.json"
    aurc_id: str                                    # Validated AURC ID
    display_name: str                                # 人类可读名
    description: str = ""                            # Agent 描述
    version: str = "0.1.0"                           # 软件版本
    author: str = ""                                 # 作者
    license: str = "Apache-2.0"                     # 许可证
    capabilities: Capabilities                       # 技能
    protocols: ProtocolSupport                       # 协议支持
    runtime: RuntimeRequirements                     # 运行时需求
    auth: AuthDeclaration                            # 认证方式
    tags: list[str] = []                             # 标签
    metadata: dict[str, Any] = {}                    # 元数据
```

### 子模型

```python
class SkillDeclaration(BaseModel):
    skill_id: str           # 唯一标识
    name: str               # 人类可读
    description: str = ""
    input_schema: InputOutputSchema
    output_schema: InputOutputSchema
    tags: list[str] = []

class Capabilities(BaseModel):
    provides: list[SkillDeclaration] = []   # 提供的技能
    consumes: list[str] = []                # 需要的技能
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

### 方法

| 方法 | 签名 | 描述 |
|--------|-----------|-------------|
| `parsed_id` | `@property → AURCId` | 获取解析的 ID |
| `to_registry_entry` | `() → dict` | 注册中心兼容字典 |

---

## AURC 消息

模块：`gaiaagent.core.message`

### AURC 消息

```python
class AURCMessage(BaseModel):
    aurc_version: str = "0.1"
    message_id: str            # 自动生成的 UUID
    correlation_id: str | None # 跨协议关联
    trace_id: str | None       # 分布式追踪
    timestamp: datetime        # UTC 创建时间
    source: str                # 源 Agent ID
    target: str                # 目标 Agent ID
    type: MessageDirection     # 消息类型
    body: MessageBody          # 载荷
    protocol_context: BridgeContext   # 桥接追踪
    session: SessionInfo              # 会话追踪
    routing: RoutingInfo              # 路由元数据
    security: MessageSecurity         # 安全上下文
```

### 方法

| 方法 | 签名 | 描述 |
|--------|-----------|-------------|
| `create_response` | `(result, error) → AURCMessage` | 创建响应 |
| `create_stream_chunk` | `(data, chunk_index, total_chunks, is_final) → AURCMessage` | 流式块 |
| `create_notification` | `(event, data) → AURCMessage` | 通知 |

### 子模型

```python
class BridgeContext(BaseModel):
    origin_protocol: str = "aurc"
    bridged_from: str | None = None
    bridge_chain: list[str] = []        # ["mcp→aurc", "aurc→a2a"]
    @property is_bridged: bool
    @property hop_count: int
    def add_hop(from_proto, to_proto) -> BridgeContext

class SessionInfo(BaseModel):
    session_id: str             # 自动生成
    conversation_id: str | None
    turn: int = 0
    parent_message_id: str | None

class DelegationHop(BaseModel):
    from_agent: str             # 委托方
    to_agent: str               # 被委托方
    scopes: list[str]           # 授予的权限
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
    skill: str | None           # 目标技能
    params: dict[str, Any]      # 参数
    result: Any                 # 响应结果
    error: ErrorInfo | None     # 错误详情
    event: str | None           # 通知事件
    chunk_index: int | None     # 流式块索引
    total_chunks: int | None    # 总块数
    data: Any                   # 块/事件数据
    is_final: bool = False      # 最终流式块
    capabilities_required: list[str]
    metadata: dict[str, Any]

class ErrorInfo(BaseModel):
    code: str                   # 错误代码
    message: str                # 人类可读
    details: dict[str, Any]
    recoverable: bool = True
    suggested_recovery: str | None
```

---

## 运行时 Harness

模块：`gaiaagent.harness.lifecycle`

```python
class RuntimeHarness:
    def __init__(
        self,
        recovery_policy: RecoveryPolicy | None = None,
        resource_limits: ResourceLimits | None = None,
    )
```

### 方法

| 方法 | 签名 | 描述 |
|--------|-----------|-------------|
| `register` | `async (descriptor: AgentDescriptor) → str` | 注册 Agent |
| `unregister` | `async (agent_id: str) → None` | 注销 Agent |
| `start` | `async (agent_id, task_params?, *, new_task=False) → str` | 启动任务 |
| `pause` | `async (agent_id: str, reason: str = "") → None` | 暂停 Agent |
| `resume` | `async (agent_id: str) → None` | 恢复 Agent |
| `stop` | `async (agent_id: str, graceful: bool = True) → None` | 停止 Agent |
| `complete` | `async (agent_id: str) → None` | 标记完成 |
| `restart` | `async (agent_id: str) → str` | 重启 Agent |
| `report_error` | `async (agent_id: str, error: str) → bool` | 报告错误 |
| `health_check` | `async (agent_id: str) → HealthReport` | Agent 健康 |
| `health_check_all` | `async () → list[HealthReport]` | 所有 Agent 健康 |
| `add_listener` | `(listener: StateListener) → None` | 添加状态监听器 |
| `remove_listener` | `(listener: StateListener) → None` | 移除监听器 |
| `get_agent` | `(agent_id: str) → AgentInstance \| None` | 获取实例 |
| `list_agents` | `(state: AgentState \| None) → list[AgentInstance]` | 列出 Agent |
| `shutdown` | `async (graceful: bool = True) → None` | 关闭所有 |
| `agent_count` | `@property → int` | Agent 数量 |

### StateListener 类型

```python
StateListener = Callable[[str, AgentState, AgentState], Any]
# (agent_id, old_state, new_state) → Any
```

### 状态转换错误

```python
class StateTransitionError(Exception):
    current: AgentState
    target: AgentState
    agent_id: str
```

---

## 消息路由器

模块：`gaiaagent.bus.router`

```python
class MessageRouter:
    def __init__(self)
```

### 方法

| 方法 | 签名 | 描述 |
|--------|-----------|-------------|
| `register_handler` | `(agent_id: str, handler: MessageHandler) → None` | 注册处理函数 |
| `unregister_handler` | `(agent_id: str) → None` | 移除处理函数 |
| `register_bridge_forwarder` | `(protocol: str, forwarder: MessageHandler) → None` | 桥接转发器 |
| `subscribe` | `(group_id: str, handler: MessageHandler) → None` | 订阅组 |
| `unsubscribe` | `(group_id: str, handler: MessageHandler) → None` | 取消订阅 |
| `route` | `async (message: AURCMessage) → Any` | 路由消息 |
| `has_handler` | `(agent_id: str) → bool` | 检查处理函数 |
| `handler_count` | `@property → int` | 处理函数数量 |
| `stats` | `@property → RouterStats` | 路由统计 |
| `dead_letter_queue` | `@property → list[AURCMessage]` | 不可投递消息 |
| `clear_dead_letters` | `() → int` | 清除死信 |

### 路由统计

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

## 会话管理器

模块：`gaiaagent.bus.session`

```python
class SessionManager:
    def __init__(self, max_sessions: int = 10000)
```

### 方法

| 方法 | 签名 | 描述 |
|--------|-----------|-------------|
| `create_session` | `(initiator, conversation_id?, metadata?) → SessionState` | 创建会话 |
| `close_session` | `(session_id: str) → None` | 关闭会话 |
| `get_session` | `(session_id: str) → SessionState \| None` | 获取会话 |
| `get_conversation_sessions` | `(conversation_id: str) → list[SessionState]` | 按对话获取 |
| `advance_turn` | `(session_id, participant?) → int` | 下一轮 |
| `set_context` | `(session_id, key, value) → None` | 设置上下文 |
| `get_context` | `(session_id, key, default?) → Any` | 获取上下文 |
| `get_active_sessions` | `() → list[SessionState]` | 活跃会话 |
| `get_sessions_by_participant` | `(agent_id) → list[SessionState]` | 按参与者 |
| `cleanup_stale` | `(max_age_seconds=3600) → int` | 清理 |
| `session_count` | `@property → int` | 总会话数 |
| `active_count` | `@property → int` | 活跃数 |

---

## 桥接器 API

模块：`gaiaagent.bridges.base`, `gaiaagent.bridges.a2a`, `gaiaagent.bridges.acp`

### ProtocolBridge（接口）

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
    # 实现 ProtocolBridge
```

### A2ABridge

```python
class A2ABridge:
    source_protocol = "a2a/1.0"
    # 实现 ProtocolBridge
    def map_agent_card(agent_card: dict) → dict
```

### ACPBridge

模块：`gaiaagent.bridges.acp`

```python
class ACPBridge:
    source_protocol = "acp/1.0"
    # 实现 ProtocolBridge
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

## 安全 API

### 认证

模块：`gaiaagent.security.auth`

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

### 授权

模块：`gaiaagent.security.authz`

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

### 委托

模块：`gaiaagent.security.delegation`

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

### 审计

模块：`gaiaagent.security.audit`

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

## 工作流 API

模块：`gaiaagent.workflows.orchestrator`

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

## SDK 装饰器

模块：`gaiaagent.sdk.decorators`

### @aurc_agent

```python
def aurc_agent(
    id: str,                              # AURC ID（必填）
    display_name: str | None = None,      # 人类可读名
    description: str = "",
    version: str = "0.1.0",
    author: str = "",
    license: str = "Apache-2.0",
    protocols: list[str] | None = None,   # 外部协议
    tags: list[str] | None = None,
    consumes: list[str] | None = None,    # 需要的外部技能
    max_concurrency: int = 10,
    supports_streaming: bool = True,
    supports_pause: bool = False,
    timeout_seconds: int = 3600,
    auth_methods: list[str] | None = None,
) → Callable[[type], type]
```

**效果：**
- 扫描类中的 `@skill` 方法
- 自动构建 `AgentDescriptor`
- 附加 `_aurc_descriptor` 和 `_aurc_skills` 到类
- 添加 `aurc_descriptor` 属性

### @skill

```python
def skill(
    skill_id: str | None = None,       # 默认为方法名
    name: str | None = None,            # 默认为方法名
    description: str = "",
    tags: list[str] | None = None,
) → Callable[[F], F]
```

**效果：**
- 在函数上存储元数据
- 从类型提示提取输入模式
- 从返回类型提取输出模式
- 用日志包装函数

### 示例

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

## Claude 集成

模块：`gaiaagent.integrations.claude`

### ClaudeLLM

```python
class ClaudeLLM:
    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: str | None = None,       # 回退到 ANTHROPIC_API_KEY 环境变量
        max_tokens: int = 4096,
        system_prompt: str | None = None,
        *,
        cli_path: str | None = None,      # 覆盖 `claude` 二进制(否则用 PATH/CLAUDE_CLI_PATH)
        cli_args: list[str] | None = None,  # 传给 CLI 的额外 flag(如 --mcp-config)
        permission_mode: str | None = None,
        mcp_config: str | None = None,
    )
    async def ask(prompt, tools?, system?, max_tokens?) → ClaudeResponse
    async def agentic_loop(prompt, tools?, max_turns=10, system?) → ClaudeResponse
    async def converse(message, tools?, system?) → ClaudeResponse
    def clear_history() → None
```

> **Agentic loop 后端**(见 [LOOP_ROADMAP.zh.md](../../LOOP_ROADMAP.zh.md)):当 `claude`
> CLI 在 PATH 上且无调用方传入的工具 handler 需进程内执行时,`agentic_loop` 委托给
> `claude -p … --output-format stream-json`(参考 agentic loop);否则降级到内置
> `anthropic` 循环。两者返回相同的 `ClaudeResponse`。

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
    def __init__(self, model?, api_key?, system_prompt?, *,
                  cli_path?, cli_args?, permission_mode?, mcp_config?,
                  allowed_tools?, timeout?, trace_recorder?, agent_id?)
    claude: ClaudeLLM       # 访问 Claude
    def get_claude_tools() → list[ClaudeTool]
```

`ClaudeAgent` 把 CLI 后端 kwarg 透传给 `ClaudeLLM`。`@aurc_agent` 装饰的子类还可经
`python -m gaiaagent.mcp --agent module:ClassName` 作为 MCP server 供 `claude` CLI 调用
(见 [LOOP_ROADMAP.zh.md](../../LOOP_ROADMAP.zh.md))。

---

## 可观测性 API

模块：`gaiaagent.observability`

### HealthDashboard

```python
class HealthDashboard:
    def __init__(harness: RuntimeHarness, audit: AuditLog | None = None,
                 router: MessageRouter | None = None)
    def get_system_health() → dict          # 健康计数 + 状态分布 + 路由统计
    def get_agent_health(agent_id) → dict | None
    def get_all_agents() → list[dict]
    def get_audit_summary() → dict
    def get_metrics() → dict                # 聚合资源 + 路由 + 审计指标
    def get_dashboard_html() → str          # 自包含 HTML 页面
```

### DashboardAPI（ASGI）

```python
class DashboardAPI:
    def __init__(dashboard: HealthDashboard)
    async def handle_request(scope, receive, send) → None
    # 路由：
    #   GET /dashboard        HTML 仪表盘
    #   GET /api/health       JSON 系统健康
    #   GET /api/agents       JSON Agent 列表
    #   GET /api/agents/{id}  JSON 单个 Agent
    #   GET /api/audit        JSON 审计摘要
    #   GET /api/metrics      JSON 指标
    #   GET /metrics          Prometheus 文本指标
    #   GET /api/stats        JSON 组合统计
```

### PrometheusMetricsExporter

```python
class PrometheusMetricsExporter:
    def __init__(dashboard: HealthDashboard, *, namespace="aurc")
    content_type: @property → str           # "text/plain; version=0.0.4; charset=utf-8"
    def render() → str                       # Prometheus 文本指标（用于 /metrics）
```

输出指标：`aurc_up`、`aurc_agents_total`、`aurc_active_tasks`、`aurc_tasks_completed_total`、
`aurc_tasks_failed_total`、`aurc_error_rate`、`aurc_memory_mb`、`aurc_cpu_percent`、
`aurc_audit_entries_total`、`aurc_messages_total{route=...}`、`aurc_router_errors_total`、
`aurc_agent_state{state=...}`、`aurc_health{status=...}`、`aurc_audit_events_total{action=...}`。

### BridgeTraceRecorder / TraceSpan

```python
class TraceSpan:                              # 一个记录的跳
    correlation_id: str | None
    message_id: str
    source: str; target: str; type: str
    origin_protocol: str
    bridge_chain: list[str]
    hop_count: int
    timestamp: str
    def to_log_line() → str                  # 单行结构化日志
    def to_dict() → dict

class BridgeTraceRecorder:
    def __init__(max_traces=10_000)
    def record(message: AURCMessage) → TraceSpan        # 记录消息跳
    def record_span(span: TraceSpan) → TraceSpan        # 记录合成 span
    def get_trace(correlation_id) → list[TraceSpan]     # 该关联所有跳
    def all_traces() → dict[str | None, list[TraceSpan]]
    def render_trace(correlation_id) → str              # 多行追踪日志
    trace_count: @property → int
    span_count: @property → int
    def clear() → int
```

> 参见 `docs/examples/observability_demo.py`：一个可运行的端到端示例，在共享
> `correlation_id` 下驱动三个桥接，并渲染 Prometheus 指标与桥接链追踪。

---

## CLI 命令

模块：`gaiaagent.cli`

### aurc serve

启动带 HTTP 传输的 AURC Harness。可选启用健康仪表盘。

```bash
aurc serve [--host HOST] [--port PORT] [--dashboard]

# 选项：
#   --host       绑定地址（默认：0.0.0.0）
#   --port       端口号（默认：8080）
#   --dashboard  启用健康仪表盘
#   -q, --quiet  机器可读输出
```

### aurc version

显示版本信息。

```bash
aurc version
# Output: gaiaagent v0.1.0 (AURC Protocol v0.1)
```

### aurc info

显示系统和配置信息。

```bash
aurc info
# Output: Python version, installed bridges, AURC version
```

### aurc validate

验证 Agent 描述文档文件。

```bash
aurc validate <path-to-descriptor.json>
# Validates AURC ID format, schema, capabilities
```

### aurc bridge test

使用内置示例消息测试协议桥接器翻译（无需真实服务器）。

```bash
aurc bridge test --protocol mcp
aurc bridge test --protocol a2a
aurc bridge test --protocol acp

# 选项：
#   --protocol  要测试的协议：mcp、a2a 或 acp（必填）
#   -q, --quiet 机器可读 JSON 输出
#
# 每个协议运行三个步骤：
#   1. translate_to_aurc   (external → AURC)
#   2. translate_from_aurc (AURC → external)
#   3. map_capabilities     (external caps → AURC skills)
```

### aurc registry export

将本地注册中心导出为 JSON（输出到标准输出）。

```bash
aurc registry export
```

---

*另请参阅：[架构](architecture.md) | [快速开始](guides/quickstart.md) | [协议规范](../../PROTOCOL.zh.md)*
