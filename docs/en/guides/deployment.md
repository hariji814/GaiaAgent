# Deployment Guide

> 🌐 [中文版](../../zh/guides/deployment.md)
> **[← Back to README](../../../README.md)** | [Architecture](../architecture.md) | [Protocol Spec](../../../PROTOCOL.md) | [API Reference](../api-reference.md)
>
> Deploy AURC agents for local development, Docker containers, and production

---

## Table of Contents

1. [Local Development](#local-development)
2. [Docker Deployment](#docker-deployment)
3. [HTTP Transport](#http-transport)
4. [WebSocket Transport](#websocket-transport)
5. [Health Dashboard](#health-dashboard)
6. [Monitoring and Observability](#monitoring-and-observability)
7. [Production Checklist](#production-checklist)

---

## Local Development

### Prerequisites

- Python 3.10+
- `uv` or `pip` package manager
- (Optional) Docker for containerized deployment

### Installation

```bash
# Install from PyPI
pip install gaiaagent

# Install with HTTP transport support
pip install gaiaagent[http]

# Install with WebSocket transport
pip install gaiaagent[websocket]

# Install with Claude integration
pip install gaiaagent[claude]

# Install everything
pip install gaiaagent[all]

# Development install
git clone https://github.com/gaiaagent/gaiaagent
cd gaiaagent
pip install -e ".[dev]"
```

### Minimal Local Setup

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

    # Check health
    health = await harness.health_check("aurc:local/my-agent:v1.0")
    print(f"Agent state: {health.state.value}")
    print(f"Health: {health.status.value}")

    await harness.shutdown()

asyncio.run(main())
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=gaiaagent

# Type check
mypy src/

# Lint
ruff check src/ tests/
```

---

## Docker Deployment

### Dockerfile

```dockerfile
FROM python:3.12-slim AS base

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir gaiaagent[http,websocket,claude]

# Copy source
COPY src/ src/
COPY config/ config/

# Non-root user
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

EXPOSE 8080

CMD ["python", "-m", "gaiaagent.cli", "serve", "--host", "0.0.0.0", "--port", "8080"]
```

### docker-compose.yml

```yaml
version: "3.9"

services:
  # AURC Agent Host
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

  # MCP Server (example)
  mcp-web-search:
    image: mcp/web-search:latest
    ports:
      - "8081:8080"
    environment:
      - SEARCH_API_KEY=${SEARCH_API_KEY}

  # Monitoring
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

### Multi-Agent Docker Compose

```yaml
version: "3.9"

services:
  # Orchestrator
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

  # Research Agent
  researcher:
    build: ./agents/researcher
    ports:
      - "8081:8080"
    environment:
      - AURC_AGENT_ID=aurc:prod/researcher:v1.0
      - AURC_ROLE=worker

  # Code Agent
  coder:
    build: ./agents/coder
    ports:
      - "8082:8080"
    environment:
      - AURC_AGENT_ID=aurc:prod/coder:v1.0
      - AURC_ROLE=worker
```

---

## HTTP Transport

### Server Configuration

```python
from gaiaagent.transport.http import HTTPTransportServer
from gaiaagent.harness.lifecycle import RuntimeHarness
from gaiaagent.bus.router import MessageRouter
from gaiaagent.core.message import AURCMessage

# Setup
harness = RuntimeHarness()
router = MessageRouter()

# Create message handler
async def handle_message(msg_dict: dict) -> dict:
    """Handle incoming HTTP AURC messages"""
    aurc_msg = AURCMessage(**msg_dict)
    result = await router.route(aurc_msg)
    return {"status": "processed", "result": result}

# Start server
server = HTTPTransportServer(host="0.0.0.0", port=8080)
server.set_handler(handle_message)
await server.start()

# Server exposes:
# POST /aurc  — send AURC messages
# GET  /health — health check
```

### Client Configuration

```python
from gaiaagent.transport.http import HTTPTransportClient

client = HTTPTransportClient(timeout_seconds=30.0)

# Send a message to a remote agent
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

# Check remote health
health = await client.health_check("http://remote-server:8080/aurc")
print(f"Remote status: {health['status']}")
```

### TLS/HTTPS Configuration

For production, use a reverse proxy (nginx, Caddy) for TLS termination:

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

## WebSocket Transport

For real-time, bidirectional, persistent communication, use the built-in WebSocket transport (`gaiaagent.transport.websocket`). Install the optional dependency first:

```bash
pip install gaiaagent[websocket]   # included in gaiaagent[all]
```

### Architecture

```
┌─────────────┐    WebSocket (ws/wss)    ┌──────────────────────┐
│ AURC Agent  │ ←──────────────────────→ │ WebSocketTransport   │
│ (Client)    │    Bidirectional         │ Server               │
└─────────────┘    Persistent            └──────────────────────┘
```

### Server

```python
from gaiaagent.transport.websocket import WebSocketTransportServer

async def handle_message(msg: dict) -> dict | None:
    # Route the AURC message and return a response (or None)
    return {"status": "processed", "echo": msg}

server = WebSocketTransportServer(host="0.0.0.0", port=8765)
server.set_handler(handle_message)
await server.start()              # blocks until stopped

# Broadcast to every connected client
await server.broadcast({"event": "shutdown", "reason": "maintenance"})

print(server.client_count)       # connected clients
await server.stop()
```

### Client

```python
from gaiaagent.transport.websocket import WebSocketTransportClient

client = WebSocketTransportClient(url="ws://localhost:8765", reconnect=True)
await client.connect()

# Send and receive
await client.send({"type": "request", "method": "invoke", "skill": "analyze"})
response = await client.receive()

# Background subscription with auto-reconnect (exponential backoff)
async def on_message(msg: dict) -> dict | None:
    print(f"Received: {msg}")
    return None

await client.subscribe(on_message)
# ...
await client.close()
```

The client reconnects automatically with exponential backoff (1s → 30s cap) when `reconnect=True`, making it suitable for long-running agents behind flaky networks.

---

## Health Dashboard

### Building a Health Dashboard

Use the Harness's health monitoring to build a real-time dashboard.

```python
from gaiaagent.harness.lifecycle import RuntimeHarness
from gaiaagent.core.types import AgentState, HealthStatus

harness = RuntimeHarness()

# Get all agent health reports
reports = await harness.health_check_all()

# Build dashboard data
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

# Count by state
state_counts = {}
for report in reports:
    state_counts[report.state.value] = state_counts.get(report.state.value, 0) + 1

print(f"Dashboard: {len(reports)} agents")
print(f"States: {state_counts}")
# {"ready": 3, "running": 2, "paused": 1}
```

### Health Check Endpoint

```python
# Expose via HTTP
async def health_handler(request):
    reports = await harness.health_check_all()
    return {
        "status": "ok" if all(r.status == HealthStatus.HEALTHY for r in reports) else "degraded",
        "agents": [r.model_dump() for r in reports],
        "total": len(reports),
    }
```

### Agent Instance Details

```python
# Get detailed agent information
instance = harness.get_agent("aurc:gaia/researcher:v1.0")
if instance:
    print(f"State: {instance.state.value}")
    print(f"State history: {instance.state_history}")
    print(f"Metrics: {instance.metrics}")
    print(f"Last error: {instance.last_error}")

# List agents by state
ready_agents = harness.list_agents(state=AgentState.READY)
running_agents = harness.list_agents(state=AgentState.RUNNING)
```

---

### Prometheus Scraping

The dashboard exposes a `/metrics` endpoint in Prometheus text exposition format, scrape-ready with no sidecar:

```python
from gaiaagent.observability import (
    HealthDashboard, DashboardAPI, PrometheusMetricsExporter,
)

dashboard = HealthDashboard(harness, audit=audit, router=router)
api = DashboardAPI(dashboard)
# Mount `api.handle_request` in your ASGI server; GET /metrics returns
# Prometheus text (content-type: text/plain; version=0.0.4).

# Or render directly (e.g. for a sidecar or ad-hoc check)
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

Metric families include `aurc_messages_total{route=...}` (direct / bridged / broadcast / dead_lettered / dropped), `aurc_agent_state{state=...}`, `aurc_health{status=...}`, and `aurc_audit_events_total{action=...}`.

---

## Monitoring and Observability

### Router Statistics

```python
from gaiaagent.bus.router import MessageRouter

router = MessageRouter()

# After processing messages, check stats
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

### Audit Log Monitoring

```python
from gaiaagent.security.audit import AuditLog, AuditAction, AuditSeverity

audit = AuditLog()

# Monitor error rates
auth_failures = audit.query(action=AuditAction.AUTH_FAILURE, limit=100)
denied_requests = audit.query(action=AuditAction.AUTHZ_DENIED, limit=100)

# Monitor bridging activity
bridge_events = audit.query(action=AuditAction.MESSAGE_BRIDGED, limit=100)

# Get action frequency
stats = audit.stats()
# {"auth_success": 500, "authz_granted": 1200, "message_bridged": 300, ...}
```

### Session Monitoring

```python
from gaiaagent.bus.session import SessionManager

sessions = SessionManager()

# Active sessions
active = sessions.get_active_sessions()
print(f"Active: {sessions.active_count}/{sessions.session_count}")

# Cleanup stale sessions
removed = sessions.cleanup_stale(max_age_seconds=3600)
print(f"Removed {removed} stale sessions")
```

### State Change Monitoring

```python
# Add listener for state changes
state_events = []

def on_state_change(agent_id, old_state, new_state):
    event = {
        "agent_id": agent_id,
        "from": old_state.value,
        "to": new_state.value,
    }
    state_events.append(event)

    # Alert on failures
    if new_state.value == "failed":
        send_alert(f"Agent {agent_id} has FAILED")

harness.add_listener(on_state_change)
```

### Logging Configuration

```python
import logging

# Configure logging for AURC
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

# Set specific log levels
logging.getLogger("gaiaagent.harness").setLevel(logging.DEBUG)
logging.getLogger("gaiaagent.bus.router").setLevel(logging.INFO)
logging.getLogger("gaiaagent.security").setLevel(logging.WARNING)
```

---

## Production Checklist

### Pre-Deployment

- [ ] **Agent descriptors validated**
  ```python
  from gaiaagent.core.identity import AgentDescriptor, AURCId
  AURCId.parse("aurc:prod/my-agent:v1.0")  # Validates format
  ```
- [ ] **Recovery policy configured**
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
- [ ] **Resource limits set**
- [ ] **Security policies defined**
- [ ] **Audit logging enabled**
- [ ] **API keys / JWT secrets configured**

### Security

- [ ] **Authentication enabled** (API Key or JWT)
- [ ] **Authorization policies set** (CapABAC)
- [ ] **Delegation chain validation enabled**
- [ ] **Rate limits configured**
- [ ] **TLS termination configured** (if HTTP)
- [ ] **Audit log export scheduled**

### Reliability

- [ ] **Health checks passing**
- [ ] **Error recovery tested**
- [ ] **Graceful shutdown tested**
  ```python
  await harness.shutdown(graceful=True)
  ```
- [ ] **Session cleanup configured**
- [ ] **Dead letter queue monitored**

### Observability

- [ ] **Router stats being collected**
- [ ] **State change listeners configured**
- [ ] **Audit log being exported**
- [ ] **Log levels appropriate**
- [ ] **Alerting configured** (for agent failures)

### Performance

- [ ] **Max concurrency appropriate for hardware**
- [ ] **Message TTL configured**
- [ ] **Session max count configured**
- [ ] **Context store cleanup scheduled**

### Example Production Entry Point

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
    # 1. Create harness with recovery policy
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

    # 2. Setup message router
    router = MessageRouter()

    # 3. Register bridges
    bridge_registry = BridgeRegistry()
    bridge_registry.register(MCPBridge())
    bridge_registry.register(A2ABridge())

    # 4. Setup security
    auth = APIKeyAuthenticator()
    authz = AuthorizationEngine()
    audit = AuditLog(max_entries=50000)

    # 5. Register agents
    # (Register your agents here)

    # 6. Start HTTP transport
    server = HTTPTransportServer(host="0.0.0.0", port=8080)
    server.set_handler(handle_message)

    logging.info("AURC Harness starting on port 8080...")
    await server.start()

asyncio.run(main())
```

---

*See also: [Architecture Deep Dive](../architecture.md) | [Security Guide](security.md) | [API Reference](../api-reference.md)*
