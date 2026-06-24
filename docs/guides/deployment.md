# Deployment Guide / 部署指南

> **[← Back to README](../../README.md)** | [Architecture](../architecture.md) | [Protocol Spec](../../PROTOCOL.md) | [API Reference](../api-reference.md)
>
> Deploy AURC agents for local development, Docker containers, and production
> 为本地开发、Docker 容器和生产环境部署 AURC Agent

---

## Table of Contents / 目录

1. [Local Development / 本地开发](#local-development--本地开发)
2. [Docker Deployment / Docker 部署](#docker-deployment--docker-部署)
3. [HTTP Transport / HTTP 传输配置](#http-transport--http-传输配置)
4. [WebSocket Transport / WebSocket 传输配置](#websocket-transport--websocket-传输配置)
5. [Health Dashboard / 健康面板](#health-dashboard--健康面板)
6. [Monitoring and Observability / 监控和可观测性](#monitoring-and-observability--监控和可观测性)
7. [Production Checklist / 生产清单](#production-checklist--生产清单)

---

## Local Development / 本地开发

### Prerequisites / 前提条件

- Python 3.10+
- `uv` or `pip` package manager
- (Optional) Docker for containerized deployment / Docker 用于容器化部署

### Installation / 安装

```bash
# Install from PyPI / 从 PyPI 安装
pip install gaiaagent

# Install with HTTP transport support / 安装含 HTTP 传输支持
pip install gaiaagent[http]

# Install with WebSocket transport / 安装含 WebSocket 传输
pip install gaiaagent[websocket]

# Install with Claude integration / 安装含 Claude 集成
pip install gaiaagent[claude]

# Install everything / 安装全部
pip install gaiaagent[all]

# Development install / 开发安装
git clone https://github.com/gaiaagent/gaiaagent
cd gaiaagent
pip install -e ".[dev]"
```

### Minimal Local Setup / 最小本地设置

```python
import asyncio
from gaiaagent.harness.lifecycle import RuntimeHarness
from gaiaagent.sdk.decorators import aurc_agent, skill

@aurc_agent(
    id="aurc:local/my-agent:v1.0",
    display_name="My Agent",
    description="A simple local agent",
)
class MyAgent:
    @skill("echo", description="Echo back the input")
    async def echo(self, text: str) -> dict:
        return {"echo": text}

async def main():
    harness = RuntimeHarness()

    agent = MyAgent()
    await harness.register(agent.aurc_descriptor)
    await harness.start("aurc:local/my-agent:v1.0")

    # Check health / 检查健康
    health = await harness.health_check("aurc:local/my-agent:v1.0")
    print(f"Agent state: {health.state.value}")
    print(f"Health: {health.status.value}")

    await harness.shutdown()

asyncio.run(main())
```

### Running Tests / 运行测试

```bash
# Run all tests / 运行所有测试
pytest

# Run with coverage / 带覆盖率
pytest --cov=gaiaagent

# Type check / 类型检查
mypy src/

# Lint / 代码检查
ruff check src/ tests/
```

---

## Docker Deployment / Docker 部署

### Dockerfile / Dockerfile

```dockerfile
FROM python:3.12-slim AS base

WORKDIR /app

# Install dependencies / 安装依赖
COPY pyproject.toml .
RUN pip install --no-cache-dir gaiaagent[http,websocket,claude]

# Copy source / 复制源码
COPY src/ src/
COPY config/ config/

# Non-root user / 非 root 用户
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Health check / 健康检查
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

EXPOSE 8080

CMD ["python", "-m", "gaiaagent.cli", "serve", "--host", "0.0.0.0", "--port", "8080"]
```

### docker-compose.yml / docker-compose.yml

```yaml
version: "3.9"

services:
  # AURC Agent Host / AURC Agent 主机
  aurc-harness:
    build: .
    ports:
      - "8080:8080"
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - AURC_LOG_LEVEL=info
      - AURC_MAX_AGENTS=50
    volumes:
      - ./config:/app/config
      - audit-data:/app/audit
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 5s
      retries: 3
    restart: unless-stopped

  # MCP Server (example) / MCP 服务器（示例）
  mcp-web-search:
    image: mcp/web-search:latest
    ports:
      - "8081:8080"
    environment:
      - SEARCH_API_KEY=${SEARCH_API_KEY}

  # Monitoring / 监控
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
    volumes:
      - grafana-data:/var/lib/grafana

volumes:
  audit-data:
  grafana-data:
```

### Multi-Agent Docker Compose / 多 Agent Docker Compose

```yaml
version: "3.9"

services:
  # Orchestrator / 编排器
  orchestrator:
    build: ./agents/orchestrator
    ports:
      - "8080:8080"
    environment:
      - AURC_AGENT_ID=aurc:prod/orchestrator:v1.0
      - AURC_ROLE=orchestrator
    depends_on:
      - researcher
      - coder

  # Research Agent / 研究 Agent
  researcher:
    build: ./agents/researcher
    ports:
      - "8081:8080"
    environment:
      - AURC_AGENT_ID=aurc:prod/researcher:v1.0
      - AURC_ROLE=worker

  # Code Agent / 代码 Agent
  coder:
    build: ./agents/coder
    ports:
      - "8082:8080"
    environment:
      - AURC_AGENT_ID=aurc:prod/coder:v1.0
      - AURC_ROLE=worker
```

---

## HTTP Transport / HTTP 传输配置

### Server Configuration / 服务器配置

```python
from gaiaagent.transport.http import HTTPTransportServer
from gaiaagent.harness.lifecycle import RuntimeHarness
from gaiaagent.bus.router import MessageRouter
from gaiaagent.core.message import AURCMessage

# Setup / 设置
harness = RuntimeHarness()
router = MessageRouter()

# Create message handler / 创建消息处理函数
async def handle_message(msg_dict: dict) -> dict:
    """Handle incoming HTTP AURC messages / 处理入站 HTTP AURC 消息"""
    aurc_msg = AURCMessage(**msg_dict)
    result = await router.route(aurc_msg)
    return {"status": "processed", "result": result}

# Start server / 启动服务器
server = HTTPTransportServer(host="0.0.0.0", port=8080)
server.set_handler(handle_message)
await server.start()

# Server exposes:
# POST /aurc  — send AURC messages / 发送 AURC 消息
# GET  /health — health check / 健康检查
```

### Client Configuration / 客户端配置

```python
from gaiaagent.transport.http import HTTPTransportClient

client = HTTPTransportClient(timeout_seconds=30.0)

# Send a message to a remote agent / 向远程 Agent 发送消息
response = await client.send(
    url="http://remote-server:8080/aurc",
    message={
        "aurc_version": "0.1",
        "source": "aurc:local/client:v1.0",
        "target": "aurc:remote/agent:v1.0",
        "type": "request",
        "body": {
            "method": "invoke",
            "skill": "analyze",
            "params": {"data": "sample data"},
        },
    },
)

# Check remote health / 检查远程健康
health = await client.health_check("http://remote-server:8080/aurc")
print(f"Remote status: {health['status']}")
```

### TLS/HTTPS Configuration / TLS/HTTPS 配置

For production, use a reverse proxy (nginx, Caddy) for TLS termination:

生产环境中使用反向代理（nginx、Caddy）进行 TLS 终端:

```nginx
# nginx.conf
server {
    listen 443 ssl http2;
    server_name aurc.example.com;

    ssl_certificate /etc/ssl/certs/aurc.crt;
    ssl_certificate_key /etc/ssl/private/aurc.key;

    location /aurc {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /health {
        proxy_pass http://127.0.0.1:8080;
    }
}
```

---

## WebSocket Transport / WebSocket 传输配置

For real-time, bidirectional, persistent communication, use the built-in WebSocket transport (`gaiaagent.transport.websocket`). Install the optional dependency first:

对于实时、双向、持久化的通信，使用内置 WebSocket 传输（`gaiaagent.transport.websocket`）。先安装可选依赖：

```bash
pip install gaiaagent[websocket]   # included in gaiaagent[all]
```

### Architecture / 架构

```
┌─────────────┐    WebSocket (ws/wss)    ┌──────────────────────┐
│ AURC Agent  │ ←──────────────────────→ │ WebSocketTransport   │
│ (Client)    │    Bidirectional         │ Server               │
└─────────────┘    Persistent            └──────────────────────┘
```

### Server / 服务器

```python
from gaiaagent.transport.websocket import WebSocketTransportServer

async def handle_message(msg: dict) -> dict | None:
    # Route the AURC message and return a response (or None)
    # 路由 AURC 消息并返回响应（或返回 None）
    return {"status": "processed", "echo": msg}

server = WebSocketTransportServer(host="0.0.0.0", port=8765)
server.set_handler(handle_message)
await server.start()              # blocks until stopped / 阻塞直到停止

# Broadcast to every connected client / 向所有已连接客户端广播
await server.broadcast({"event": "shutdown", "reason": "maintenance"})

print(server.client_count)       # connected clients / 已连接客户端数
await server.stop()
```

### Client / 客户端

```python
from gaiaagent.transport.websocket import WebSocketTransportClient

client = WebSocketTransportClient(url="ws://localhost:8765", reconnect=True)
await client.connect()

# Send and receive / 发送与接收
await client.send({"type": "request", "method": "invoke", "skill": "analyze"})
response = await client.receive()

# Background subscription with auto-reconnect (exponential backoff)
# 后台订阅，带指数退避自动重连
async def on_message(msg: dict) -> dict | None:
    print(f"Received: {msg}")
    return None

await client.subscribe(on_message)
# ...
await client.close()
```

The client reconnects automatically with exponential backoff (1s → 30s cap) when `reconnect=True`, making it suitable for long-running agents behind flaky networks.

当 `reconnect=True` 时，客户端会以指数退避（1s → 上限 30s）自动重连，适合网络不稳的长期运行 Agent。

---

## Health Dashboard / 健康面板

### Building a Health Dashboard / 构建健康面板

Use the Harness's health monitoring to build a real-time dashboard.

使用 Harness 的健康监控构建实时面板。

```python
from gaiaagent.harness.lifecycle import RuntimeHarness
from gaiaagent.core.types import AgentState, HealthStatus

harness = RuntimeHarness()

# Get all agent health reports / 获取所有 Agent 健康报告
reports = await harness.health_check_all()

# Build dashboard data / 构建面板数据
dashboard = {
    "total_agents": harness.agent_count,
    "agents": [],
}

for report in reports:
    dashboard["agents"].append({
        "agent_id": report.agent_id,
        "status": report.status.value,
        "state": report.state.value,
        "metrics": {
            "memory_mb": report.metrics.memory_mb,
            "cpu_percent": report.metrics.cpu_percent,
            "active_tasks": report.metrics.active_tasks,
            "tasks_completed": report.metrics.total_tasks_completed,
            "tasks_failed": report.metrics.total_tasks_failed,
            "uptime_seconds": report.metrics.uptime_seconds,
        },
        "last_error": report.last_error,
        "timestamp": report.timestamp.isoformat(),
    })

# Count by state / 按状态计数
state_counts = {}
for report in reports:
    state_counts[report.state.value] = state_counts.get(report.state.value, 0) + 1

print(f"Dashboard: {len(reports)} agents")
print(f"States: {state_counts}")
# {"ready": 3, "running": 2, "paused": 1}
```

### Health Check Endpoint / 健康检查端点

```python
# Expose via HTTP / 通过 HTTP 暴露
async def health_handler(request):
    reports = await harness.health_check_all()
    return {
        "status": "ok" if all(r.status == HealthStatus.HEALTHY for r in reports) else "degraded",
        "agents": [r.model_dump() for r in reports],
        "total": len(reports),
    }
```

### Agent Instance Details / Agent 实例详情

```python
# Get detailed agent information / 获取详细 Agent 信息
instance = harness.get_agent("aurc:gaia/researcher:v1.0")
if instance:
    print(f"State: {instance.state.value}")
    print(f"State history: {instance.state_history}")
    print(f"Metrics: {instance.metrics}")
    print(f"Last error: {instance.last_error}")

# List agents by state / 按状态列出 Agent
ready_agents = harness.list_agents(state=AgentState.READY)
running_agents = harness.list_agents(state=AgentState.RUNNING)
```

---

## Monitoring and Observability / 监控和可观测性

### Router Statistics / 路由器统计

```python
from gaiaagent.bus.router import MessageRouter

router = MessageRouter()

# After processing messages, check stats / 处理消息后检查统计
stats = router.stats.to_dict()
# {
#     "total_routed": 1500,
#     "direct": 800,
#     "bridged": 400,
#     "broadcast": 200,
#     "dead_lettered": 10,
#     "dropped": 5,
#     "errors": 3
# }
```

### Audit Log Monitoring / 审计日志监控

```python
from gaiaagent.security.audit import AuditLog, AuditAction, AuditSeverity

audit = AuditLog()

# Monitor error rates / 监控错误率
auth_failures = audit.query(action=AuditAction.AUTH_FAILURE, limit=100)
denied_requests = audit.query(action=AuditAction.AUTHZ_DENIED, limit=100)

# Monitor bridging activity / 监控桥接活动
bridge_events = audit.query(action=AuditAction.MESSAGE_BRIDGED, limit=100)

# Get action frequency / 获取动作频率
stats = audit.stats()
# {"auth_success": 500, "authz_granted": 1200, "message_bridged": 300, ...}
```

### Session Monitoring / 会话监控

```python
from gaiaagent.bus.session import SessionManager

sessions = SessionManager()

# Active sessions / 活跃会话
active = sessions.get_active_sessions()
print(f"Active: {sessions.active_count}/{sessions.session_count}")

# Cleanup stale sessions / 清理陈旧会话
removed = sessions.cleanup_stale(max_age_seconds=3600)
print(f"Removed {removed} stale sessions")
```

### State Change Monitoring / 状态变化监控

```python
# Add listener for state changes / 添加状态变化监听器
state_events = []

def on_state_change(agent_id, old_state, new_state):
    event = {
        "agent_id": agent_id,
        "from": old_state.value,
        "to": new_state.value,
    }
    state_events.append(event)

    # Alert on failures / 故障告警
    if new_state.value == "failed":
        send_alert(f"Agent {agent_id} has FAILED")

harness.add_listener(on_state_change)
```

### Logging Configuration / 日志配置

```python
import logging

# Configure logging for AURC / 为 AURC 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

# Set specific log levels / 设置特定日志级别
logging.getLogger("gaiaagent.harness").setLevel(logging.DEBUG)
logging.getLogger("gaiaagent.bus.router").setLevel(logging.INFO)
logging.getLogger("gaiaagent.security").setLevel(logging.WARNING)
```

---

## Production Checklist / 生产清单

### Pre-Deployment / 部署前

- [ ] **Agent descriptors validated** / Agent 描述文档已验证
  ```python
  from gaiaagent.core.identity import AgentDescriptor, AURCId
  AURCId.parse("aurc:prod/my-agent:v1.0")  # Validates format
  ```
- [ ] **Recovery policy configured** / 恢复策略已配置
  ```python
  from gaiaagent.core.types import RecoveryPolicy, RecoveryStrategy, RecoveryAction
  policy = RecoveryPolicy(
      max_retries=3,
      backoff_ms=[1000, 5000, 15000],
      strategies=[
          RecoveryStrategy(trigger="timeout", action=RecoveryAction.RETRY_WITH_BACKOFF),
          RecoveryStrategy(trigger="auth", action=RecoveryAction.REFRESH_AND_RETRY),
          RecoveryStrategy(trigger="unrecoverable", action=RecoveryAction.ESCALATE),
      ],
  )
  harness = RuntimeHarness(recovery_policy=policy)
  ```
- [ ] **Resource limits set** / 资源限制已设置
- [ ] **Security policies defined** / 安全策略已定义
- [ ] **Audit logging enabled** / 审计日志已启用
- [ ] **API keys / JWT secrets configured** / API Key / JWT 密钥已配置

### Security / 安全

- [ ] **Authentication enabled** (API Key or JWT) / 认证已启用
- [ ] **Authorization policies set** (CapABAC) / 授权策略已设置
- [ ] **Delegation chain validation enabled** / 委托链验证已启用
- [ ] **Rate limits configured** / 速率限制已配置
- [ ] **TLS termination configured** (if HTTP) / TLS 终端已配置
- [ ] **Audit log export scheduled** / 审计日志导出已安排

### Reliability / 可靠性

- [ ] **Health checks passing** / 健康检查通过
- [ ] **Error recovery tested** / 错误恢复已测试
- [ ] **Graceful shutdown tested** / 优雅关闭已测试
  ```python
  await harness.shutdown(graceful=True)
  ```
- [ ] **Session cleanup configured** / 会话清理已配置
- [ ] **Dead letter queue monitored** / 死信队列已监控

### Observability / 可观测性

- [ ] **Router stats being collected** / 路由器统计正在收集
- [ ] **State change listeners configured** / 状态变化监听器已配置
- [ ] **Audit log being exported** / 审计日志正在导出
- [ ] **Log levels appropriate** / 日志级别适当
- [ ] **Alerting configured** (for agent failures) / 告警已配置

### Performance / 性能

- [ ] **Max concurrency appropriate for hardware** / 最大并发适合硬件
- [ ] **Message TTL configured** / 消息 TTL 已配置
- [ ] **Session max count configured** / 会话最大数量已配置
- [ ] **Context store cleanup scheduled** / 上下文存储清理已安排

### Example Production Entry Point / 生产入口点示例

```python
import asyncio
import logging
from gaiaagent.harness.lifecycle import RuntimeHarness
from gaiaagent.bus.router import MessageRouter
from gaiaagent.bridges.base import MCPBridge, BridgeRegistry
from gaiaagent.bridges.a2a import A2ABridge
from gaiaagent.security.auth import APIKeyAuthenticator
from gaiaagent.security.authz import AuthorizationEngine
from gaiaagent.security.audit import AuditLog
from gaiaagent.transport.http import HTTPTransportServer
from gaiaagent.core.types import RecoveryPolicy, RecoveryStrategy, RecoveryAction

logging.basicConfig(level=logging.INFO)

async def main():
    # 1. Create harness with recovery policy / 创建含恢复策略的 Harness
    harness = RuntimeHarness(
        recovery_policy=RecoveryPolicy(
            max_retries=3,
            backoff_ms=[1000, 5000, 15000],
            strategies=[
                RecoveryStrategy(trigger="timeout", action=RecoveryAction.RETRY_WITH_BACKOFF),
                RecoveryStrategy(trigger="unrecoverable", action=RecoveryAction.ESCALATE),
            ],
        )
    )

    # 2. Setup message router / 设置消息路由器
    router = MessageRouter()

    # 3. Register bridges / 注册桥接器
    bridge_registry = BridgeRegistry()
    bridge_registry.register(MCPBridge())
    bridge_registry.register(A2ABridge())

    # 4. Setup security / 设置安全
    auth = APIKeyAuthenticator()
    authz = AuthorizationEngine()
    audit = AuditLog(max_entries=50000)

    # 5. Register agents / 注册 Agent
    # (Register your agents here / 在此注册你的 Agent)

    # 6. Start HTTP transport / 启动 HTTP 传输
    server = HTTPTransportServer(host="0.0.0.0", port=8080)
    server.set_handler(handle_message)

    logging.info("AURC Harness starting on port 8080...")
    await server.start()

asyncio.run(main())
```

---

*See also / 另请参阅: [Architecture Deep Dive](../architecture.md) | [Security Guide](security.md) | [API Reference](../api-reference.md)*
