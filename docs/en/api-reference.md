# API Reference

> 🌐 [中文版](../zh/api-reference.md)
> **[← Back to README](../../README.md)** | [Protocol Spec](../../PROTOCOL.md) | [Architecture](architecture.md) | [Quick Start](guides/quickstart.md)
>
> Complete API documentation for the GaiaAgent / AURC Protocol SDK

---

## Table of Contents

1. [Core Types](#core-types)
2. [AURCId](#aurcid)
3. [AgentDescriptor](#agentdescriptor)
4. [AURCMessage](#aurcmessage)
5. [RuntimeHarness](#runtimeharness)
6. [MessageRouter](#messagerouter)
7. [SessionManager](#sessionmanager)
8. [Bridge APIs](#bridge-apis)
9. [Security APIs](#security-apis)
10. [Workflow APIs](#workflow-apis)
11. [SDK Decorators](#sdk-decorators)
12. [CLI Commands](#cli-commands)

---

## Core Types

Module: `gaiaagent.core.types`

### AgentState

Agent lifecycle states.

```python
class AgentState(str, Enum):
    REGISTERING = "registering"   # Agent registering
    READY       = "ready"         # Waiting for tasks
    RUNNING     = "running"       # Executing
    PAUSED      = "paused"        # Paused
    FAILING     = "failing"       # Error recovery pending
    RECOVERING  = "recovering"    # Recovering
    COMPLETED   = "completed"     # Terminal: success
    FAILED      = "failed"        # Terminal: failure
    STOPPED     = "stopped"       # Terminal: stopped

    @property
    def is_terminal(self) -> bool:
        """COMPLETED, FAILED, or STOPPED"""

    @property
    def is_active(self) -> bool:
        """RUNNING, FAILING, or RECOVERING"""
```

### MessageDirection

```python
class MessageDirection(str, Enum):
    REQUEST      = "request"       # Requires response
    RESPONSE     = "response"      # Reply to request
    NOTIFICATION = "notification"  # One-way
    STREAM       = "stream"        # Streaming data
    DELEGATION   = "delegation"    # Task delegation
    HANDOFF      = "handoff"       # Task ownership transfer
    HEARTBEAT    = "heartbeat"     # Keep-alive
```

### ContextScope

```python
class ContextScope(str, Enum):
    SESSION = "session"  # Per-task
    AGENT   = "agent"    # Per-agent lifetime
    SHARED  = "shared"   # Cross-agent
    GLOBAL  = "global"   # System-wide
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
    RETRY_WITH_BACKOFF  = "retry_with_backoff"    # Exponential backoff
    RETRY_ALTERNATIVE   = "retry_alternative"      # Try alternative skill
    COMPACT_AND_RETRY   = "compact_and_retry"      # Summarize context, retry
    REFRESH_AND_RETRY   = "refresh_and_retry"      # Refresh auth, retry
    ESCALATE            = "escalate"                # Human operator
    FAIL                = "fail"                    # Give up
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

### Data Models

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
    trigger: str                              # Error type
    action: RecoveryAction                    # Recovery action
    alternatives: list[str] = []              # Fallback skills
    escalate_to: str | None = None            # Escalation target
```

---

## AURCId

Module: `gaiaagent.core.identity`

```python
class AURCId(BaseModel):
    raw: str          # Full string: "aurc:gaia/researcher:v1.2"
    namespace: str    # "gaia"
    name: str         # "researcher"
    version: str      # "v1.2"
```

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `parse` | `AURCId.parse(id_string: str) → AURCId` | Parse and validate |
| `matches` | `matches(pattern: str) → bool` | Glob-like matching |

**Format:** `aurc:{namespace}/{name}:{version}`

**Validation regex:**
```
^aurc:[a-z0-9][a-z0-9._-]{0,63}/[a-z0-9][a-z0-9._-]{0,127}:v\d+(?:\.\d+){0,2}$
```

**Examples:**
```python
aid = AURCId.parse("aurc:gaia/researcher:v1.2")
aid.matches("aurc:gaia/*")             # True
aid.matches("aurc:*/researcher:v1.*")  # True
aid.matches("aurc:other/*")            # False
```

---

## AgentDescriptor

Module: `gaiaagent.core.identity`

```python
class AgentDescriptor(BaseModel):
    schema_version: str = "aurc://spec/v0.1/agent-descriptor.json"
    aurc_id: str                                    # Validated AURC ID
    display_name: str                                # Human-readable name
    description: str = ""                            # Agent description
    version: str = "0.1.0"                           # Software version
    author: str = ""                                 # Author
    license: str = "AGPL-3.0"                        # License
    capabilities: Capabilities                       # Skills provided/consumed
    protocols: ProtocolSupport                       # Supported protocols
    runtime: RuntimeRequirements                     # Runtime needs
    auth: AuthDeclaration                            # Auth methods
    tags: list[str] = []                             # Searchable tags
    metadata: dict[str, Any] = {}                    # Arbitrary metadata
```

### Sub-Models

```python
class SkillDeclaration(BaseModel):
    skill_id: str           # Unique ID
    name: str               # Human-readable
    description: str = ""
    input_schema: InputOutputSchema
    output_schema: InputOutputSchema
    tags: list[str] = []

class Capabilities(BaseModel):
    provides: list[SkillDeclaration] = []   # Skills offered
    consumes: list[str] = []                # Skills needed
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

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `parsed_id` | `@property → AURCId` | Get parsed ID |
| `to_registry_entry` | `() → dict` | Registry-compatible dict |

---

## AURCMessage

Module: `gaiaagent.core.message`

### AURCMessage

```python
class AURCMessage(BaseModel):
    aurc_version: str = "0.1"
    message_id: str            # Auto-generated UUID
    correlation_id: str | None # Cross-protocol correlation
    trace_id: str | None       # Distributed tracing
    timestamp: datetime        # UTC creation time
    source: str                # Source agent AURC ID
    target: str                # Target agent AURC ID
    type: MessageDirection     # Message type
    body: MessageBody          # Payload
    protocol_context: BridgeContext   # Bridge tracking
    session: SessionInfo              # Conversation tracking
    routing: RoutingInfo              # Routing metadata
    security: MessageSecurity         # Security context
```

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `create_response` | `(result, error) → AURCMessage` | Create response |
| `create_stream_chunk` | `(data, chunk_index, total_chunks, is_final) → AURCMessage` | Stream chunk |
| `create_notification` | `(event, data) → AURCMessage` | Notification |

### Sub-Models

```python
class BridgeContext(BaseModel):
    origin_protocol: str = "aurc"
    bridged_from: str | None = None
    bridge_chain: list[str] = []        # ["mcp→aurc", "aurc→a2a"]
    @property is_bridged: bool
    @property hop_count: int
    def add_hop(from_proto, to_proto) -> BridgeContext

class SessionInfo(BaseModel):
    session_id: str             # Auto-generated
    conversation_id: str | None
    turn: int = 0
    parent_message_id: str | None

class DelegationHop(BaseModel):
    from_agent: str             # Delegating agent
    to_agent: str               # Receiving agent
    scopes: list[str]           # Granted scopes
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
    skill: str | None           # Target skill
    params: dict[str, Any]      # Parameters
    result: Any                 # Response result
    error: ErrorInfo | None     # Error details
    event: str | None           # Notification event
    chunk_index: int | None     # Stream chunk index
    total_chunks: int | None    # Total chunks
    data: Any                   # Chunk/event data
    is_final: bool = False      # Final stream chunk
    capabilities_required: list[str]
    metadata: dict[str, Any]

class ErrorInfo(BaseModel):
    code: str                   # Error code
    message: str                # Human-readable
    details: dict[str, Any]
    recoverable: bool = True
    suggested_recovery: str | None
```

---

## RuntimeHarness

Module: `gaiaagent.harness.lifecycle`

```python
class RuntimeHarness:
    def __init__(
        self,
        recovery_policy: RecoveryPolicy | None = None,
        resource_limits: ResourceLimits | None = None,
    )
```

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `register` | `async (descriptor: AgentDescriptor) → str` | Register agent |
| `unregister` | `async (agent_id: str) → None` | Unregister agent |
| `start` | `async (agent_id, task_params?, *, new_task=False) → str` | Start task |
| `pause` | `async (agent_id: str, reason: str = "") → None` | Pause agent |
| `resume` | `async (agent_id: str) → None` | Resume agent |
| `stop` | `async (agent_id: str, graceful: bool = True) → None` | Stop agent |
| `complete` | `async (agent_id: str) → None` | Mark completed |
| `restart` | `async (agent_id: str) → str` | Restart agent |
| `report_error` | `async (agent_id: str, error: str) → bool` | Report error, trigger recovery |
| `health_check` | `async (agent_id: str) → HealthReport` | Agent health |
| `health_check_all` | `async () → list[HealthReport]` | All agents health |
| `add_listener` | `(listener: StateListener) → None` | Add state listener |
| `remove_listener` | `(listener: StateListener) → None` | Remove listener |
| `get_agent` | `(agent_id: str) → AgentInstance \| None` | Get agent instance |
| `list_agents` | `(state: AgentState \| None) → list[AgentInstance]` | List agents |
| `shutdown` | `async (graceful: bool = True) → None` | Shutdown all |
| `agent_count` | `@property → int` | Number of agents |

### StateListener Type

```python
StateListener = Callable[[str, AgentState, AgentState], Any]
# (agent_id, old_state, new_state) → Any
```

### StateTransitionError

```python
class StateTransitionError(Exception):
    current: AgentState
    target: AgentState
    agent_id: str
```

---

## MessageRouter

Module: `gaiaagent.bus.router`

```python
class MessageRouter:
    def __init__(self)
```

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `register_handler` | `(agent_id: str, handler: MessageHandler) → None` | Register handler |
| `unregister_handler` | `(agent_id: str) → None` | Remove handler |
| `register_bridge_forwarder` | `(protocol: str, forwarder: MessageHandler) → None` | Bridge forwarder |
| `subscribe` | `(group_id: str, handler: MessageHandler) → None` | Subscribe to group |
| `unsubscribe` | `(group_id: str, handler: MessageHandler) → None` | Unsubscribe |
| `route` | `async (message: AURCMessage) → Any` | Route message |
| `has_handler` | `(agent_id: str) → bool` | Check handler |
| `handler_count` | `@property → int` | Handler count |
| `stats` | `@property → RouterStats` | Router statistics |
| `dead_letter_queue` | `@property → list[AURCMessage]` | Undeliverable messages |
| `clear_dead_letters` | `() → int` | Clear dead letters |

### RouterStats

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

## SessionManager

Module: `gaiaagent.bus.session`

```python
class SessionManager:
    def __init__(self, max_sessions: int = 10000)
```

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `create_session` | `(initiator, conversation_id?, metadata?) → SessionState` | Create session |
| `close_session` | `(session_id: str) → None` | Close session |
| `get_session` | `(session_id: str) → SessionState \| None` | Get session |
| `get_conversation_sessions` | `(conversation_id: str) → list[SessionState]` | Get by conversation |
| `advance_turn` | `(session_id, participant?) → int` | Next turn |
| `set_context` | `(session_id, key, value) → None` | Set context |
| `get_context` | `(session_id, key, default?) → Any` | Get context |
| `get_active_sessions` | `() → list[SessionState]` | Active sessions |
| `get_sessions_by_participant` | `(agent_id) → list[SessionState]` | By participant |
| `cleanup_stale` | `(max_age_seconds=3600) → int` | Cleanup |
| `session_count` | `@property → int` | Total sessions |
| `active_count` | `@property → int` | Active count |

---

## Bridge APIs

Module: `gaiaagent.bridges.base`, `gaiaagent.bridges.a2a`, `gaiaagent.bridges.acp`

### ProtocolBridge (Interface)

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
    # Implements ProtocolBridge
```

### A2ABridge

```python
class A2ABridge:
    source_protocol = "a2a/1.0"
    # Implements ProtocolBridge
    def map_agent_card(agent_card: dict) → dict
```

### ACPBridge

Module: `gaiaagent.bridges.acp`

```python
class ACPBridge:
    source_protocol = "acp/1.0"
    # Implements ProtocolBridge
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

## Security APIs

### Authentication

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

### Authorization

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

### Delegation

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

### Audit

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

## Workflow APIs

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

## SDK Decorators

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

**Effects:**
- Scans class for `@skill` methods
- Builds `AgentDescriptor` automatically
- Attaches `_aurc_descriptor` and `_aurc_skills` to class
- Adds `aurc_descriptor` property

### @skill

```python
def skill(
    skill_id: str | None = None,       # Defaults to method name
    name: str | None = None,            # Defaults to method name
    description: str = "",
    tags: list[str] | None = None,
) → Callable[[F], F]
```

**Effects:**
- Stores `SkillMetadata` on function
- Extracts input schema from type hints
- Extracts output schema from return type
- Wraps function with logging

### Example

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

## Claude Integration

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
        *,
        cli_path: str | None = None,      # Override `claude` binary (else PATH/CLAUDE_CLI_PATH)
        cli_args: list[str] | None = None,  # Extra flags passed to the CLI (e.g. --mcp-config)
        permission_mode: str | None = None,
        mcp_config: str | None = None,
    )
    async def ask(prompt, tools?, system?, max_tokens?) → ClaudeResponse
    async def agentic_loop(prompt, tools?, max_turns=10, system?) → ClaudeResponse
    async def converse(message, tools?, system?) → ClaudeResponse
    def clear_history() → None
```

> **Agentic loop backend** (see [LOOP_ROADMAP.md](../../LOOP_ROADMAP.md)): when the
> `claude` CLI is on PATH and no caller-supplied tool handlers need to run
> in-process, `agentic_loop` delegates to `claude -p … --output-format stream-json`
> (the reference agentic loop). Otherwise it falls back to the built-in
> `anthropic`-based loop. Both return the same `ClaudeResponse`.

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
    claude: ClaudeLLM       # Access to Claude
    def get_claude_tools() → list[ClaudeTool]
```

`ClaudeAgent` forwards the CLI-backend kwargs to `ClaudeLLM`. An `@aurc_agent`-decorated
subclass can also be served as an MCP server for the `claude` CLI via
`python -m gaiaagent.mcp --agent module:ClassName` (see
[LOOP_ROADMAP.md](../../LOOP_ROADMAP.md)).

---

## Observability APIs

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
    # Routes:
    #   GET /dashboard        HTML dashboard
    #   GET /api/health       JSON system health
    #   GET /api/agents       JSON agent list
    #   GET /api/agents/{id}  JSON single agent
    #   GET /api/audit        JSON audit summary
    #   GET /api/metrics      JSON metrics
    #   GET /metrics          Prometheus text exposition
    #   GET /api/stats        JSON combined statistics
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
class TraceSpan:                              # one recorded hop
    correlation_id: str | None
    message_id: str
    source: str; target: str; type: str
    origin_protocol: str
    bridge_chain: list[str]
    hop_count: int
    timestamp: str
    def to_log_line() → str                  # single structured log line
    def to_dict() → dict

class BridgeTraceRecorder:
    def __init__(max_traces=10_000)
    def record(message: AURCMessage) → TraceSpan        # record a message hop
    def record_span(span: TraceSpan) → TraceSpan        # record a synthetic span
    def get_trace(correlation_id) → list[TraceSpan]     # all hops for a correlation
    def all_traces() → dict[str | None, list[TraceSpan]]
    def render_trace(correlation_id) → str              # multi-line trace log
    trace_count: @property → int
    span_count: @property → int
    def clear() → int
```

> See `docs/examples/observability_demo.py` for a runnable end-to-end example
> that exercises all three bridges under a shared `correlation_id` and renders
> Prometheus metrics + a bridge-chain trace.

---

## CLI Commands

Module: `gaiaagent.cli`

### aurc serve

Start the AURC harness with HTTP transport. Optionally enable the health dashboard.

```bash
aurc serve [--host HOST] [--port PORT] [--dashboard]

# Options:
#   --host       Bind address (default: 0.0.0.0)
#   --port       Port number (default: 8080)
#   --dashboard  Enable health dashboard
#   -q, --quiet  Machine-readable output
```

### aurc version

Show version information.

```bash
aurc version
# Output: gaiaagent v0.1.0 (AURC Protocol v0.1)
```

### aurc info

Show system and configuration info.

```bash
aurc info
# Output: Python version, installed bridges, AURC version
```

### aurc validate

Validate an Agent Descriptor file.

```bash
aurc validate <path-to-descriptor.json>
# Validates AURC ID format, schema, capabilities
```

### aurc bridge test

Test a protocol bridge translation using built-in sample messages (no live server required).

```bash
aurc bridge test --protocol mcp
aurc bridge test --protocol a2a
aurc bridge test --protocol acp

# Options:
#   --protocol  Protocol to test: mcp, a2a, or acp (required)
#   -q, --quiet Machine-readable JSON output
#
# Runs three steps per protocol:
#   1. translate_to_aurc   (external → AURC)
#   2. translate_from_aurc (AURC → external)
#   3. map_capabilities     (external caps → AURC skills)
```

### aurc registry export

Export the local registry to JSON (printed to stdout).

```bash
aurc registry export
```

---

*See also: [Architecture](architecture.md) | [Quickstart](guides/quickstart.md) | [Protocol Spec](../../PROTOCOL.md)*
