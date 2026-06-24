# GaiaAgent — AURC Protocol

**Agent Unified Runtime & Communication Protocol**
**Agent 统一运行时与通信协议**

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

---

## What is AURC? / 什么是 AURC?

**EN:** AURC is a unified bridging protocol for AI agents. It doesn't replace MCP, A2A, or ACP — it connects them. AURC provides a runtime harness for agent lifecycle management and protocol bridges for seamless interoperability.

**中文:** AURC 是一个 AI Agent 统一桥接协议。它不取代 MCP、A2A 或 ACP，而是连接它们。AURC 提供 Agent 生命周期管理的运行时 Harness 和实现无缝互操作的协议桥接器。

```
┌─────────────────────────────────────────────────────┐
│                  AURC Protocol                        │
│  ┌─────────────┐ ┌─────────────┐ ┌───────────────┐  │
│  │   Runtime    │ │  Unified    │ │   Protocol    │  │
│  │   Harness    │ │  Message    │ │   Bridges     │  │
│  │  (运行时)     │ │  Bus (消息)  │ │  (协议桥接)    │  │
│  └─────────────┘ └─────────────┘ └───────────────┘  │
├─────────┬───────────────┬───────────────┬────────────┤
│  MCP    │      A2A      │     ACP       │   Future   │
│ (Tools) │  (Agent-Agt)  │  (Lightweight)│  Protocols │
└─────────┴───────────────┴───────────────┴────────────┘
```

## Key Features / 核心特性

| Feature | Description / 描述 |
|---------|-------------------|
| **Runtime Harness** | Agent lifecycle state machine with error recovery / Agent 生命周期状态机与错误恢复 |
| **Protocol Bridges** | MCP, A2A, ACP adapters / MCP、A2A、ACP 协议适配器 |
| **Unified Identity** | Cross-protocol agent identity (AURC ID) / 跨协议 Agent 身份 |
| **Capability Matching** | Automatic agent-to-task matching / 自动 Agent 与任务匹配 |
| **Security** | Delegation chain validation + CapABAC authorization / 委托链验证 + 能力属性访问控制 |
| **Context Management** | Multi-scope agent memory (session/agent/shared/global) / 多作用域 Agent 内存 |
| **Human-in-the-Loop** | Standardized approval gates / 标准化的人类审批门 |
| **WebSocket Transport** | Real-time bidirectional messaging / 实时双向消息传输 |
| **Health Dashboard** | Live monitoring with HTML + JSON API / 实时监控仪表板 |
| **CLI Tool** | `aurc` command-line interface / `aurc` 命令行工具 |
| **Workflow Engine** | 5 orchestration patterns + Claude integration / 5 种编排模式 + Claude 集成 |

## Quick Start / 快速开始

### Install / 安装

```bash
pip install gaiaagent
```

### Define an Agent / 定义 Agent

```python
from gaiaagent.sdk.decorators import aurc_agent, skill

@aurc_agent(
    id="aurc:myproject/researcher:v1.0",
    display_name="Research Agent",
    description="Deep research with multi-source analysis",
    protocols=["mcp/2025-06-18", "a2a/1.0"],
    tags=["research", "analysis"],
)
class ResearchAgent:

    @skill("deep-research", description="Multi-source research and synthesis")
    async def research(self, query: str, depth: str = "medium") -> dict:
        # Your research logic here / 你的研究逻辑
        return {
            "report": f"Research report for: {query}",
            "confidence": 0.85,
            "sources": ["arxiv", "web"],
        }

    @skill("summarize", description="Summarize research findings")
    async def summarize(self, text: str, max_length: int = 500) -> dict:
        return {"summary": text[:max_length]}
```

### Start the Harness / 启动 Harness

```python
import asyncio
from gaiaagent import RuntimeHarness
from gaiaagent.bridges import MCPBridge, A2ABridge

async def run():
    harness = RuntimeHarness()

    # Register your agent / 注册 Agent
    agent = ResearchAgent()
    await harness.register(agent.aurc_descriptor)

    # Start the agent / 启动 Agent
    await harness.start("aurc:myproject/researcher:v1.0")

    # Check health / 检查健康
    report = await harness.health_check("aurc:myproject/researcher:v1.0")
    print(report.status.value)  # "healthy"

asyncio.run(run())
```

## Architecture / 架构

```
L7  Discovery      — Agent registry, capability matching
L6  Security       — CapABAC auth, delegation chains
L5  Context        — Cross-protocol context tracking
L4  Bridges        — MCP / A2A / ACP adapters
L3  Message Bus    — Unified message format, routing
L2  Harness        — Lifecycle, health, memory, recovery
L1  Identity       — AURC ID, capability declaration
L0  Transport      — HTTP/2, WebSocket, stdio, gRPC
```

See [PROTOCOL.md](PROTOCOL.md) for the full specification.
查看 [PROTOCOL.md](PROTOCOL.md) 获取完整规范。

## Protocol Comparison / 协议对比

| Capability | MCP | A2A | ACP | **AURC** |
|---|:---:|:---:|:---:|:---:|
| Agent Identity | ✗ | Agent Card | ✗ | **AURC ID** |
| Tool Invocation | ✓ | ✗ | ✓ | **via Bridge** |
| Agent-to-Agent | ✗ | ✓ | ✓ | **via Bridge** |
| Runtime Lifecycle | ✗ | Task only | ✗ | **✓ (core)** |
| Context/Memory | Resources | ✗ | ✗ | **✓ (multi-scope)** |
| Cross-Protocol | ✗ | ✗ | ✗ | **✓ (core)** |
| Permission Enforcement | ✗ | ✗ | ✗ | **✓ (CapABAC)** |
| Delegation Audit | ✗ | ✗ | ✗ | **✓** |
| Error Recovery | ✗ | ✗ | ✗ | **✓ (policy engine)** |

## Development / 开发

```bash
# Clone / 克隆
git clone https://github.com/gaiaagent/gaiaagent
cd gaiaagent

# Install dev dependencies / 安装开发依赖
pip install -e ".[dev]"

# Run tests / 运行测试
pytest

# Type check / 类型检查
mypy src/

# Lint / 代码检查
ruff check src/ tests/
```

## Roadmap / 路线图

- [x] **Phase 1**: Protocol spec + core types + Harness + Registry + SDK
- [x] **Phase 2**: Message Bus + routing + session management + codecs + WebSocket transport
- [x] **Phase 3**: MCP/A2A/ACP bridges + HTTP/WebSocket transport + end-to-end demos
- [x] **Phase 4**: Security (CapABAC + auth + delegation + audit) + Health Dashboard
- [x] **Phase 5**: Claude integration + dynamic workflow orchestration (5 patterns) + CLI + comprehensive docs
- [x] **Phase 6**: Production hardening + Docker + CI/CD + community

## License / 许可证

- **Code / 代码**: [AGPL-3.0](LICENSE)
- **Protocol Spec / 协议规范**: [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)

## Contributing / 贡献

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
欢迎贡献！请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解指南。
