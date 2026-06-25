# 部署指南

> 🌐 [English](../../en/guides/deployment.md)
> **[← 返回 README](../../../README.zh.md)** | [架构](../architecture.md) | [协议规范](../../../PROTOCOL.zh.md) | [API 参考](../api-reference.md)
>
> 为本地开发、Docker 容器和生产环境部署 AURC Agent

---

## 目录

1. [本地开发](#本地开发)
2. [Docker 部署](#docker-部署)
3. [HTTP 传输配置](#http-传输配置)
4. [WebSocket 传输配置](#websocket-传输配置)
5. [健康面板](#健康面板)
6. [监控和可观测性](#监控和可观测性)
7. [生产清单](#生产清单)

---

## 本地开发

### 前提条件

- Python 3.10+
- `uv` 或 `pip` 包管理器
- （可选）Docker 用于容器化部署

### 安装

```bash
# 从 PyPI 安装
pip install gaiaagent

# 安装含 HTTP 传输支持
pip install gaiaagent[http]

# 安装含 WebSocket 传输
pip install gaiaagent[websocket]

# 安装含 Claude 集成
pip install gaiaagent[claude]

# 安装全部
pip install gaiaagent[all]

# 开发安装
git clone https://github.com/gaiaagent/gaiaagent
cd gaiaagent
pip install -e ".[dev]"
```

### 最小本地设置

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

    # 检查健康
    health = await harness.health_check("aurc:local/my-agent:v1.0")
    print(f"Agent state: {health.state.value}")
    print(f"Health: {health.status.value}")

    await harness.shutdown()

asyncio.run(main())
```

### 运行测试

```bash
# 运行所有测试
pytest

# 带覆盖率
pytest --cov=gaiaagent

# 类型检查
mypy src/

# 代码检查
ruff check src/ tests/
```

---

## Docker 部署

### Dockerfile

```dockerfile
FROM python:3.12-slim AS base

WORKDIR /app

# 安装依赖
COPY pyproject.toml .
RUN pip install --no-cache-dir gaiaagent[http,websocket,claude]

# 复制源码
COPY src/ src/
COPY config/ config/

# 非 root 用户
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

EXPOSE 8080

CMD ["python", "-m", "gaiaagent.cli", "serve", "--host", "0.0.0.0", "--port", "8080"]
```

### docker-compose.yml

```yaml
version: "3.9"

services:
  # AURC Agent 主机
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

  # MCP 服务器（示例）
  mcp-web-search:
    image: mcp/web-search:latest
    ports:
      - "8081:8080"
    environment:
      - SEARCH_API_KEY=${SEARCH_API_KEY}

  # 监控
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

### 多 Agent Docker Compose

```yaml
version: "3.9"

services:
  # 编排器
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

  # 研究 Agent
  researcher:
    build: ./agents/researcher
    ports:
      - "8081:8080"
    environment:
      - AURC_AGENT_ID=aurc:prod/researcher:v1.0
      - AURC_ROLE=worker

  # 代码 Agent
  coder:
    build: ./agents/coder
    ports:
      - "8082:8080"
    environment:
      - AURC_AGENT_ID=aurc:prod/coder:v1.0
      - AURC_ROLE=worker
```

---

## HTTP 传输配置

### 服务器配置

```python
from gaiaagent.transport.http import HTTPTransportServer
from gaiaagent.harness.lifecycle import RuntimeHarness
from gaiaagent.bus.router import MessageRouter
from gaiaagent.core.message import AURCMessage

# 设置
harness = RuntimeHarness()
router = MessageRouter()

# 创建消息处理函数
async def handle_message(msg_dict: dict) -> dict:
    """处理入站 HTTP AURC 消息"""
    aurc_msg = AURCMessage(**msg_dict)
    result = await router.route(aurc_msg)
    return {"status": "processed", "result": result}

# 启动服务器
server = HTTPTransportServer(host="0.0.0.0", port=8080)
server.set_handler(handle_message)
await server.start()

# 服务器暴露：
# POST /aurc  — 发送 AURC 消息
# GET  /health — 健康检查
```

### 客户端配置

```python
from gaiaagent.transport.http import HTTPTransportClient

client = HTTPTransportClient(timeout_seconds=30.0)

# 向远程 Agent 发送消息
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

# 检查远程健康
health = await client.health_check("http://remote-server:8080/aurc")
print(f"Remote status: {health['status']}")
```

### TLS/HTTPS 配置

生产环境中使用反向代理（nginx、Caddy）进行 TLS 终端：

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

## WebSocket 传输配置

对于实时、双向、持久化的通信，使用内置 WebSocket 传输（`gaiaagent.transport.websocket`）。先安装可选依赖：

```bash
pip install gaiaagent[websocket]   # 包含在 gaiaagent[all] 中
```

### 架构

```
┌─────────────┐    WebSocket (ws/wss)    ┌──────────────────────┐
│ AURC Agent  │ ←──────────────────────→ │ WebSocketTransport   │
│ (Client)    │    双向                  │ Server               │
└─────────────┘    持久化                └──────────────────────┘
```

### 服务器

```python
from gaiaagent.transport.websocket import WebSocketTransportServer

async def handle_message(msg: dict) -> dict | None:
    # 路由 AURC 消息并返回响应（或返回 None）
    return {"status": "processed", "echo": msg}

server = WebSocketTransportServer(host="0.0.0.0", port=8765)
server.set_handler(handle_message)
await server.start()              # 阻塞直到停止

# 向所有已连接客户端广播
await server.broadcast({"event": "shutdown", "reason": "maintenance"})

print(server.client_count)       # 已连接客户端数
await server.stop()
```

### 客户端

```python
from gaiaagent.transport.websocket import WebSocketTransportClient

client = WebSocketTransportClient(url="ws://localhost:8765", reconnect=True)
await client.connect()

# 发送与接收
await client.send({"type": "request", "method": "invoke", "skill": "analyze"})
response = await client.receive()

# 后台订阅，带指数退避自动重连
async def on_message(msg: dict) -> dict | None:
    print(f"Received: {msg}")
    return None

await client.subscribe(on_message)
# ...
await client.close()
```

当 `reconnect=True` 时，客户端会以指数退避（1s → 上限 30s）自动重连，适合网络不稳的长期运行 Agent。

---

## 健康面板

### 构建健康面板

使用 Harness 的健康监控构建实时面板。

```python
from gaiaagent.harness.lifecycle import RuntimeHarness
from gaiaagent.core.types import AgentState, HealthStatus

harness = RuntimeHarness()

# 获取所有 Agent 健康报告
reports = await harness.health_check_all()

# 构建面板数据
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

# 按状态计数
state_counts = {}
for report in reports:
    state_counts[report.state.value] = state_counts.get(report.state.value, 0) + 1

print(f"Dashboard: {len(reports)} agents")
print(f"States: {state_counts}")
# {"ready": 3, "running": 2, "paused": 1}
```

### 健康检查端点

```python
# 通过 HTTP 暴露
async def health_handler(request):
    reports = await harness.health_check_all()
    return {
        "status": "ok" if all(r.status == HealthStatus.HEALTHY for r in reports) else "degraded",
        "agents": [r.model_dump() for r in reports],
        "total": len(reports),
    }
```

### Agent 实例详情

```python
# 获取详细 Agent 信息
instance = harness.get_agent("aurc:gaia/researcher:v1.0")
if instance:
    print(f"State: {instance.state.value}")
    print(f"State history: {instance.state_history}")
    print(f"Metrics: {instance.metrics}")
    print(f"Last error: {instance.last_error}")

# 按状态列出 Agent
ready_agents = harness.list_agents(state=AgentState.READY)
running_agents = harness.list_agents(state=AgentState.RUNNING)
```

---

### Prometheus 抓取

仪表盘在 `/metrics` 端点暴露 Prometheus 文本展示格式指标，可直接抓取，无需 sidecar：

```python
from gaiaagent.observability import (
    HealthDashboard, DashboardAPI, PrometheusMetricsExporter,
)

dashboard = HealthDashboard(harness, audit=audit, router=router)
api = DashboardAPI(dashboard)
# 将 api.handle_request 挂载到 ASGI 服务器；GET /metrics 返回
# Prometheus 文本（content-type: text/plain; version=0.0.4）。

# 或直接渲染
print(PrometheusMetricsExporter(dashboard).render())
```

```yaml
# prometheus.yml
scrape_configs:
  - job_name: "aurc"
    metrics_path: /metrics
    static_configs:
      - targets: ["aurc-harness:8080"]
```

指标族包括 `aurc_messages_total{route=...}`（direct / bridged / broadcast / dead_lettered / dropped）、`aurc_agent_state{state=...}`、`aurc_health{status=...}` 与 `aurc_audit_events_total{action=...}`。

---

## 监控和可观测性

### 路由器统计

```python
from gaiaagent.bus.router import MessageRouter

router = MessageRouter()

# 处理消息后检查统计
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

### 审计日志监控

```python
from gaiaagent.security.audit import AuditLog, AuditAction, AuditSeverity

audit = AuditLog()

# 监控错误率
auth_failures = audit.query(action=AuditAction.AUTH_FAILURE, limit=100)
denied_requests = audit.query(action=AuditAction.AUTHZ_DENIED, limit=100)

# 监控桥接活动
bridge_events = audit.query(action=AuditAction.MESSAGE_BRIDGED, limit=100)

# 获取动作频率
stats = audit.stats()
# {"auth_success": 500, "authz_granted": 1200, "message_bridged": 300, ...}
```

### 会话监控

```python
from gaiaagent.bus.session import SessionManager

sessions = SessionManager()

# 活跃会话
active = sessions.get_active_sessions()
print(f"Active: {sessions.active_count}/{sessions.session_count}")

# 清理陈旧会话
removed = sessions.cleanup_stale(max_age_seconds=3600)
print(f"Removed {removed} stale sessions")
```

### 状态变化监控

```python
# 添加状态变化监听器
state_events = []

def on_state_change(agent_id, old_state, new_state):
    event = {
        "agent_id": agent_id,
        "from": old_state.value,
        "to": new_state.value,
    }
    state_events.append(event)

    # 故障告警
    if new_state.value == "failed":
        send_alert(f"Agent {agent_id} has FAILED")

harness.add_listener(on_state_change)
```

### 日志配置

```python
import logging

# 为 AURC 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

# 设置特定日志级别
logging.getLogger("gaiaagent.harness").setLevel(logging.DEBUG)
logging.getLogger("gaiaagent.bus.router").setLevel(logging.INFO)
logging.getLogger("gaiaagent.security").setLevel(logging.WARNING)
```

---

## 生产清单

### 部署前

- [ ] **Agent 描述文档已验证**
  ```python
  from gaiaagent.core.identity import AgentDescriptor, AURCId
  AURCId.parse("aurc:prod/my-agent:v1.0")  # 验证格式
  ```
- [ ] **恢复策略已配置**
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
- [ ] **资源限制已设置**
- [ ] **安全策略已定义**
- [ ] **审计日志已启用**
- [ ] **API Key / JWT 密钥已配置**

### 安全

- [ ] **认证已启用**（API Key 或 JWT）
- [ ] **授权策略已设置**（CapABAC）
- [ ] **委托链验证已启用**
- [ ] **速率限制已配置**
- [ ] **TLS 终端已配置**（若使用 HTTP）
- [ ] **审计日志导出已安排**

### 可靠性

- [ ] **健康检查通过**
- [ ] **错误恢复已测试**
- [ ] **优雅关闭已测试**
  ```python
  await harness.shutdown(graceful=True)
  ```
- [ ] **会话清理已配置**
- [ ] **死信队列已监控**

### 可观测性

- [ ] **路由器统计正在收集**
- [ ] **状态变化监听器已配置**
- [ ] **审计日志正在导出**
- [ ] **日志级别适当**
- [ ] **告警已配置**（针对 Agent 故障）

### 性能

- [ ] **最大并发适合硬件**
- [ ] **消息 TTL 已配置**
- [ ] **会话最大数量已配置**
- [ ] **上下文存储清理已安排**

### 生产入口点示例

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
    # 1. 创建含恢复策略的 Harness
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

    # 2. 设置消息路由器
    router = MessageRouter()

    # 3. 注册桥接器
    bridge_registry = BridgeRegistry()
    bridge_registry.register(MCPBridge())
    bridge_registry.register(A2ABridge())

    # 4. 设置安全
    auth = APIKeyAuthenticator()
    authz = AuthorizationEngine()
    audit = AuditLog(max_entries=50000)

    # 5. 注册 Agent
    # （在此注册你的 Agent）

    # 6. 启动 HTTP 传输
    server = HTTPTransportServer(host="0.0.0.0", port=8080)
    server.set_handler(handle_message)

    logging.info("AURC Harness starting on port 8080...")
    await server.start()

asyncio.run(main())
```

---

*另请参阅：[架构深入解析](../architecture.md) | [安全指南](security.md) | [API 参考](../api-reference.md)*
