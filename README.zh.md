<p align="center">
  <img src="https://raw.githubusercontent.com/gaiaagent/gaiaagent/main/docs/assets/logo.png" alt="GaiaAgent" width="120" />
</p>

<h1 align="center">GaiaAgent</h1>

<p align="center">
  <strong>AI Agent 互操作的通用协议层</strong><br/>
  <em>桥接所有 AI Agent 协议的统一运行时层</em>
</p>

<p align="center">
  <a href="https://github.com/gaiaagent/gaiaagent/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/gaiaagent/gaiaagent/ci.yml?style=flat-square&label=CI" alt="CI" /></a>
  <a href="https://pypi.org/project/gaiaagent/"><img src="https://img.shields.io/pypi/v/gaiaagent?style=flat-square&color=blue" alt="PyPI" /></a>
  <a href="https://pypi.org/project/gaiaagent/"><img src="https://img.shields.io/pypi/pyversions/gaiaagent?style=flat-square&color=blue" alt="Python" /></a>
  <a href="https://github.com/gaiaagent/gaiaagent/blob/main/LICENSE"><img src="https://img.shields.io/github/license/gaiaagent/gaiaagent?style=flat-square&color=blue" alt="License" /></a>
  <a href="https://github.com/gaiaagent/gaiaagent/stargazers"><img src="https://img.shields.io/github/stars/gaiaagent/gaiaagent?style=flat-square" alt="Stars" /></a>
  <a href="https://discord.gg/gaiaagent"><img src="https://img.shields.io/badge/Discord-join-7289DA?style=flat-square&logo=discord" alt="Discord" /></a>
</p>

<p align="center">
  <em>状态：<strong>Alpha (v0.1.0)</strong> —— 规范已冻结，参考实现正在交付，API 仍可能调整。尚未达到生产级健壮性。</em>
</p>

> 🌐 [English](README.md)

---

## 30 秒概览

> **MCP 给了 Agent 工具。A2A 让它们彼此相连。ACP 给了它们一个邮箱。但没有人给它们一个运行时。**
>
> GaiaAgent 是 Agent 时代缺失的那块**连接组织**：一个桥接所有协议、管理 Agent 生命周期、在委托链上强制安全、并编排多 Agent 工作流的统一层 —— 无需你放弃已经写好的任何一行 MCP 或 A2A 代码。

**一个 Agent。一个身份。任意协议。是桥接，而非围墙。**

---

## 为何是现在

2025–2026 年间，Agent 协议经历了寒武纪式爆发 —— **MCP**（Anthropic）、**A2A**（Google）、**ACP**（IBM）、**ANP** —— 每一个都很出色，各自恰好解决了协议栈中的一个切片。结果是：在这个生态中，拥有最佳工具（MCP）的 Agent **无法委托**给最专业的专家（A2A），双方也都无法证明 *谁授权了什么* 跨越这一跳。

我们不需要**第五个协议**。我们需要的是**它们之下的那一层** —— 就像 TCP/IP 成为一百种应用协议之下的共享基底那样。AURC 就是 Agent 的这一基底：一个运行时、一套安全模型，以及一条总线，让现有协议*接入其中*而非彼此竞争。

---

## 一览

| | |
|:---|:---|
| **8 层协议栈** | L0 传输 → L7 发现，面向 Agent 的 OSI 模型，每层可独立测试 |
| **3 个协议桥接** | MCP · A2A · ACP —— 双向、上下文保留、能力映射 |
| **9 态生命周期** | 首个标准化的 Agent 状态机：注册 → 就绪 → 运行 → 恢复 → 完成 |
| **CapABAC 安全** | 能力 + 基于属性的授权，委托链*只收窄*、永不扩大 |
| **5 种编排模式** | 链式 · 路由 · 并行 · 编排者-工作者 · 评估-优化器 |
| **4 种上下文作用域** | session / agent / shared / global，带跨协议关联 ID |
| **Claude 原生** | Agentic 循环由 `claude` CLI 驱动;AURC `@skill` 经内置 MCP server 暴露给 loop(见 [LOOP_ROADMAP.zh.md](LOOP_ROADMAP.zh.md)) |
| **传输层** | HTTP/2 · WebSocket · stdio（gRPC 规划中） |

---

## 问题所在

2026 年的 AI Agent 生态**碎片化为互不兼容的协议孤岛**：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│   MCP (Anthropic)       A2A (Google)        ACP (IBM)       ANP         │
│   ┌───────────┐        ┌───────────┐       ┌───────────┐   ┌───────┐   │
│   │ Agent↔Tool│        │ Agent↔Agent│      │ REST Msg  │   │Identity│  │
│   │           │   ✗    │           │  ✗    │           │ ✗ │       │  │
│   │ No A2A    │        │ No Tools  │       │ Minimal   │   │No Msg │  │
│   │ No Runtime│        │ No Bridge │       │ No Runtime│   │No Run │  │
│   └───────────┘        └───────────┘       └───────────┘   └───────┘  │
│                                                                         │
│   每个协议只解决一层。没有一个能桥接全部。                              │
│   没有统一的生命周期。没有跨协议安全。没有上下文流转。                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

使用 MCP 获取工具的 Agent **无法无缝委托给 A2A Agent**。两个协议都不管理 Agent 状态、错误恢复或跨边界的上下文持久化。**行业需要的是连接组织 —— 而非又一个竞争协议。**

---

## GaiaAgent：解决方案

GaiaAgent 实现了 **AURC**（Agent 统一运行时与通信）—— 一种**元协议**，它不取代 MCP、A2A 或 ACP，而是**连接它们**。

```
┌──────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│                    你的应用                                              │
│                                                                          │
│         @aurc_agent    @skill    ClaudeAgent    WorkflowEngine           │
│                                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│                         G A I A A G E N T                                │
│                                                                          │
│   ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  ┌────────────┐ │
│   │   Runtime    │  │   Unified    │  │   Protocol    │  │  Security  │ │
│   │   Harness    │  │  Message Bus │  │   Bridges     │  │   Layer    │ │
│   │              │  │              │  │               │  │            │ │
│   │ • Lifecycle  │  │ • Router     │  │ ┌───┐ ┌───┐  │  │ • CapABAC  │ │
│   │ • State      │  │ • Session    │  │ │MCP│ │A2A│  │  │ • Delegation│ │
│   │ • Health     │  │ • Codec      │  │ └───┘ └───┘  │  │ • Audit    │ │
│   │ • Recovery   │  │ • WebSocket  │  │ ┌───┐ ┌───┐  │  │ • Auth     │ │
│   │ • Context    │  │              │  │ │ACP│ │Custom│ │  │            │ │
│   │ • HITL       │  │              │  │ └───┘ └───┘  │  │            │ │
│   └─────────────┘  └──────────────┘  └───────────────┘  └────────────┘ │
│                                                                          │
│   ┌──────────────────────┐  ┌─────────────────────────────────────────┐ │
│   │  Workflow Engine     │  │  Claude Integration                     │ │
│   │  5 Orchestration     │  │  ClaudeLLM + Agentic Loop              │ │
│   │  Patterns            │  │  + Tool Use + Dynamic Workflows        │ │
│   └──────────────────────┘  └─────────────────────────────────────────┘ │
│                                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   MCP Servers       A2A Agents       ACP Services     Future Protocols  │
│   (Tools)           (Agent-to-Agent) (Lightweight)    (gRPC, Custom)    │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**一个 Agent。一个身份。任意协议。**

---

## 为何选择 GaiaAgent？

| 其他协议缺失的 | GaiaAgent 提供的 |
|:---|:---|
| **无生命周期管理**（任何协议都没有） | **9 态生命周期引擎**，自带自动错误恢复、暂停/恢复与优雅关闭 |
| **协议孤岛** —— Agent 锁定在单一协议 | **协议桥接**，无缝翻译 MCP ↔ A2A ↔ ACP ↔ AURC |
| **无安全模型**（MCP 的混淆代理问题） | **CapABAC 授权** —— 基于能力 + 基于属性，带委托链校验 |
| **无跨协议上下文** | **4 作用域上下文系统**（session / agent / shared / global），带关联追踪 |
| **无人在回路**标准 | **标准化的 HITL 协议**，带审批门、选项与超时处理 |
| **无可观测性** | **内置审计日志**、健康监控与路由统计 |
| **无编排模式** | **5 种经典模式**，由 Claude 驱动：链式、路由、并行、编排者-工作者、评估-优化 |

---

## 快速开始

### 安装

```bash
pip install gaiaagent

# 按需安装
pip install gaiaagent[http]        # HTTP/2 transport
pip install gaiaagent[websocket]   # real-time bidirectional transport
pip install gaiaagent[claude]      # Claude integration

# 全量安装
pip install gaiaagent[all]
```

### 30 秒定义一个 Agent

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
        return {
            "report": f"Research report for: {query}",
            "confidence": 0.85,
            "sources": ["arxiv", "web"],
        }

    @skill("summarize", description="Summarize research findings")
    async def summarize(self, text: str, max_length: int = 500) -> dict:
        return {"summary": text[:max_length]}
```

### 启动运行时

```python
import asyncio
from gaiaagent import RuntimeHarness

async def main():
    harness = RuntimeHarness()

    agent = ResearchAgent()
    await harness.register(agent.aurc_descriptor)
    await harness.start("aurc:myproject/researcher:v1.0")

    # 完整的生命周期管理
    health = await harness.health_check("aurc:myproject/researcher:v1.0")
    print(f"Status: {health.status.value}")  # "healthy"

asyncio.run(main())
```

### 桥接任意协议

```python
from gaiaagent.bridges.base import MCPBridge, BridgeRegistry
from gaiaagent.bridges.a2a import A2ABridge
from gaiaagent.bridges.acp import ACPBridge

bridges = BridgeRegistry()
bridges.register(MCPBridge())    # MCP tools/call ↔ AURC request
bridges.register(A2ABridge())    # A2A tasks/send ↔ AURC delegation
bridges.register(ACPBridge())    # ACP invoke ↔ AURC delegation

# 将任意协议消息翻译为 AURC 的规范格式
aurc_msg = await bridges.get("mcp").translate_to_aurc(mcp_tool_call)
```

### 用 5 种模式编排

```python
from gaiaagent.workflows.orchestrator import DynamicWorkflowEngine

engine = DynamicWorkflowEngine()

# 1. 提示词链 —— 顺序流水线
result = await engine.chain([translate, summarize, format_output], initial_input="Hello")

# 2. 智能路由 —— 分类器挑选最佳处理器
result = await engine.route(input_data=request, routes={"code": handle_code, "research": handle_research})

# 3. 并行扇出 —— 并发执行 + 聚合
result = await engine.parallel([search_arxiv, search_web, search_patents], input_data="AI agents")

# 4. 编排者-工作者 —— Claude 动态分解任务
result = await engine.orchestrate(orchestrator=claude_decomposer, workers={"research": researcher, "code": coder})

# 5. 评估-优化器 —— 迭代精炼循环
result = await engine.optimize(generator=draft, evaluator=quality_check, quality_threshold=0.9)
```

---

## 架构：8 层协议栈

GaiaAgent 引入了首个完整的 **8 层 AI Agent 通信协议栈** —— 灵感来自 OSI 模型，但为 Agent 时代量身打造。

```
 ┌─────────────────────────────────────────────────────────────────────────┐
 │                                                                         │
 │  L7  DISCOVERY        Agent registry · capability matching              │
 │       发现层            health-based routing · mDNS · federation         │
 │  ─────────────────────────────────────────────────────────────────────  │
 │  L6  SECURITY         CapABAC auth · delegation chains                  │
 │       安全层            audit logging · permission attenuation           │
 │  ─────────────────────────────────────────────────────────────────────  │
 │  L5  CONTEXT          Cross-protocol context tracking                   │
 │       上下文关联层       permission propagation · W3C trace context      │
 │  ─────────────────────────────────────────────────────────────────────  │
 │  L4  BRIDGES          MCP Bridge · A2A Bridge · ACP Bridge             │
 │       协议桥接层         Custom Bridge · capability mapping              │
 │  ─────────────────────────────────────────────────────────────────────  │
 │  L3  MESSAGE BUS      Canonical JSON format · routing · session mgmt   │
 │       统一消息总线        NDJSON streaming · message framing              │
 │  ─────────────────────────────────────────────────────────────────────  │
 │  L2  HARNESS          Lifecycle state machine · health monitoring       │
 │       运行时引擎          context/memory · error recovery · HITL          │
 │  ─────────────────────────────────────────────────────────────────────  │
 │  L1  IDENTITY         AURC ID (URN) · capability declaration           │
 │       Agent 身份          Agent Descriptor · protocol binding           │
 │  ─────────────────────────────────────────────────────────────────────  │
 │  L0  TRANSPORT        HTTP/2 · WebSocket · stdio · gRPC                │
 │       传输层              transport negotiation · TLS                     │
 │                                                                         │
 └─────────────────────────────────────────────────────────────────────────┘
```

### 运行时引擎 —— 核心创新

**没有任何现有协议提供 Agent 生命周期管理。** GaiaAgent 的运行时引擎是首个标准化的 Agent 生命周期引擎，带 9 态状态机：

```
                    ┌──────────────────────────────────┐
                    │                                  │
                    ▼                                  │
              ┌──────────────┐                        │
              │ REGISTERING  │────────────────┐       │
              └──────────────┘                │       │
                    │                         │       │
               registered                     │       │
                    │                         │       │
                    ▼                         ▼       │
              ┌──────────┐              ┌──────────┐  │
        ┌────▶│  READY   │              │  FAILED  │  │
        │     └────┬─────┘              └──────────┘  │
        │          │                                   │
        │     start│                                   │
        │          ▼                                   │
        │   ┌──────────────┐    error    ┌──────────┐ │
        │   │   RUNNING    │────────────▶│ FAILING  │─┘
        │   └──┬──┬────┬───┘             └────┬─────┘
        │      │  │    │                      │
  pause()│  complete  │  error          recover│
        │      │  │    │                      │
        │      │  │    │                      ▼
        │      │  │    │              ┌──────────────┐
        │      │  │    │              │  RECOVERING  │
        │      │  │    │              └──────┬───────┘
        │      ▼  │    ▼                     │
        │  ┌──────────┐ ┌──────────┐    recovered
        │  │COMPLETED │ │ PAUSED   │         │
        │  └──────────┘ └────┬─────┘         │
        │                     │               │
        │               resume│               │
        │                     └───────────────┘
        │
        └──── (back to READY for next task)
```

### 真正可用的错误恢复

| 触发条件 | 策略 | 行为 |
|:---|:---|:---|
| `timeout` | 退避重试 | 指数退避：1s → 5s → 15s |
| `tool_error` | 备选工具 | 尝试不同的工具/技能 |
| `context_overflow` | 压缩并重试 | 摘要最早的上下文后重试 |
| `auth_expired` | 刷新并重试 | 刷新凭证后重试 |
| `unrecoverable` | 上报人工 | 带完整上下文的 HITL 干预 |

---

## 安全：解决 MCP 的混淆代理问题

MCP 存在一个根本性安全缺陷：**服务器代表用户行动，却无法区分或强制用户被授权做什么。** GaiaAgent 用 **CapABAC** 解决了这个问题 —— 一种混合授权模型，结合了基于能力的安全与基于属性的访问控制。

```
┌──────────────────────────────────────────────────────────────────────┐
│                                                                      │
│  User [read, write, admin]                                           │
│    │                                                                 │
│    │  Delegation Hop 1                                               │
│    ▼                                                                 │
│  Orchestrator [read, write]          ← narrowed ✓                   │
│    │                                                                 │
│    │  Delegation Hop 2                                               │
│    ▼                                                                 │
│  Researcher [read]                   ← narrowed ✓                   │
│    │                                                                 │
│    │  Delegation Hop 3                                               │
│    ▼                                                                 │
│  MCP Tool [read, execute]            ← WIDENED ✗ REJECTED!         │
│                                                                      │
│  Rules:                                                              │
│  • Scopes only narrow, never widen                                   │
│  • No circular delegations                                           │
│  • Timestamps must be monotonically ordered                          │
│  • Max delegation depth enforced                                      │
│  • Every hop is cryptographically auditable                          │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

**多层安全栈：**

| 层 | 机制 | 用途 |
|:---|:---|:---|
| 认证 | API Key · JWT · OAuth 2.1 · mTLS | 校验 Agent 身份 |
| 授权 | CapABAC 引擎 | 细粒度、基于约束的访问控制 |
| 委托 | 链式校验 | 防止跨跳的权限提升 |
| 审计 | 不可变日志 | 记录每个安全事件以满足合规 |

---

## 跨协议通信

GaiaAgent 的桥接在协议语义之间翻译，同时保留上下文、权限与可追踪性：

### 场景：多协议混合工作流

```
                              ┌───────────────┐
                              │  User Request  │
                              └───────┬───────┘
                                      │
                                      ▼
                         ┌────────────────────────┐
                         │   AURC Orchestrator     │
                         │   (Claude-powered)      │
                         └────┬──────┬──────┬──────┘
                              │      │      │
                    ┌─────────┘      │      └──────────┐
                    ▼                ▼                  ▼
          ┌──────────────┐ ┌──────────────┐  ┌──────────────┐
          │  AURC Agent  │ │  MCP Server  │  │  A2A Agent   │
          │  (native)    │ │  (via Bridge)│  │  (via Bridge)│
          │              │ │              │  │              │
          │  Direct      │ │  tools/call  │  │  tasks/send  │
          │  Communication│ │  ← translated│  │  ← translated│
          └──────┬───────┘ └──────┬───────┘  └──────┬───────┘
                 │                │                  │
                 └────────────────┼──────────────────┘
                                  │
                          correlation_id
                          delegation_chain
                                  │
                                  ▼
                         ┌────────────────────────┐
                         │  Results Aggregated     │
                         │  All steps traced       │
                         │  Permissions unified     │
                         └────────────────────────┘
```

---

## 协议对比

AURC 与现有协议的对比 —— 不是作为竞争者，而是作为它们都需要的**连接层**：

| 能力 | MCP | A2A | ACP | ANP | **GaiaAgent/AURC** |
|:---|:---:|:---:|:---:|:---:|:---:|
| Agent 身份 | ✗ | Agent Card | ✗ | DID | **AURC ID (URN)** |
| 工具调用 | ✓ | ✗ | ✓ | ✗ | **经由桥接** |
| Agent 间通信 | ✗ | ✓ | ✓ | ✓ | **经由桥接** |
| **运行时生命周期** | ✗ | 仅 Task | ✗ | ✗ | **✓（9 态引擎）** |
| **上下文/记忆** | Resources | ✗ | ✗ | ✗ | **✓（4 作用域系统）** |
| **跨协议** | ✗ | ✗ | ✗ | ✗ | **✓（核心特性）** |
| **权限强制** | ✗ | ✗ | ✗ | ✗ | **✓（CapABAC）** |
| **委托审计** | ✗ | ✗ | ✗ | ✗ | **✓（链式校验）** |
| **错误恢复** | ✗ | ✗ | ✗ | ✗ | **✓（5 种策略）** |
| **人在回路** | ✗ | 基础 | ✗ | ✗ | **✓（标准化）** |
| **工作流模式** | ✗ | ✗ | ✗ | ✗ | **✓（5 种模式 + Claude）** |

---

## 项目结构

```
gaiaagent/
├── core/                   # Foundation types, identity, messages, capabilities
│   ├── identity.py         #   AURC ID format, Agent Descriptor
│   ├── message.py          #   Canonical message format
│   ├── capability.py       #   Capability matching engine
│   └── types.py            #   State machine types, recovery policies
│
├── sdk/                    # Developer-facing SDK
│   └── decorators.py       #   @aurc_agent, @skill decorators
│
├── harness/                # Runtime Harness (L2)
│   ├── lifecycle.py        #   9-state lifecycle engine
│   └── context.py          #   Multi-scope context store
│
├── bus/                    # Unified Message Bus (L3)
│   ├── router.py           #   Message routing + statistics
│   ├── session.py          #   Session/conversation management
│   └── codec.py            #   JSON/NDJSON/MessagePack codecs
│
├── bridges/                # Protocol Bridges (L4)
│   ├── base.py             #   Bridge interface + MCP Bridge
│   ├── a2a.py              #   A2A Bridge
│   └── acp.py              #   ACP Bridge
│
├── security/               # Security Layer (L6)
│   ├── auth.py             #   API Key + JWT Authentication
│   ├── authz.py            #   CapABAC Authorization Engine
│   ├── delegation.py       #   Delegation chain validation
│   └── audit.py            #   Immutable audit log
│
├── registry/               # Discovery (L7)
│   └── local.py            #   Local agent registry + capability matching
│
├── transport/              # Transport (L0)
│   ├── http.py             #   HTTP/2 transport server + client
│   └── websocket.py        #   WebSocket transport
│
├── workflows/              # Orchestration Patterns
│   └── orchestrator.py     #   5 patterns + DynamicWorkflowEngine
│
├── integrations/           # LLM 集成
│   ├── claude.py           #   Claude LLM + Agentic Loop + Tool Use
│   └── claude_cli.py       #   `claude` CLI 后端(Loop Roadmap Step 2)
│
├── mcp/                    # AURC MCP server(Loop Roadmap Step 1 基石)
│   └── server.py           #   把 @skill agent 暴露为 CLI 可调的 MCP 工具
│
├── observability/          # 监控与追踪
│   ├── dashboard.py        #   Health dashboard (HTML + JSON + ASGI API)
│   ├── metrics.py          #   Prometheus /metrics exporter
│   └── tracing.py          #   Bridge-chain trace recorder (correlation by ID)
│
└── cli.py                  # `aurc` CLI tool
```

---

## 开发

```bash
# 克隆仓库
git clone https://github.com/gaiaagent/gaiaagent
cd gaiaagent

# 安装全部开发依赖
pip install -e ".[all]"

# 运行完整的端到端演示（展示全部 13 个组件）
python main.py

# 运行测试
pytest

# 运行并生成覆盖率报告
pytest --cov=src/gaiaagent --cov-report=term-missing

# 类型检查（严格模式）
mypy src/

# Lint
ruff check src/ tests/

# 或使用 make 提升便利
make all      # lint + type-check + test
make demo     # run the end-to-end demo
make serve    # start server with dashboard
```

### Docker

```bash
# 构建并运行
docker compose up -d

# 或单独构建
docker build -t gaiaagent .
docker run -p 8080:8080 gaiaagent
```

---

## 路线图

> GaiaAgent 当前为 **v0.1.0 alpha**：规范已冻结，参考实现交付了下述各层，但 API 仍在稳定中，生产化加固仍在推进。完整且持续更新的计划见 **[ROADMAP.zh.md](ROADMAP.zh.md)** —— 北极星、六条工作流、版本里程碑、验收标准与明确的非目标。

| 版本 | 主题 | 状态 |
|:---:|:---|:---:|
| **v0.1** | 单进程参考实现（3 个桥接 · 9 态生命周期 · CapABAC · 5 种模式 · CLI · Claude） | ✅ Alpha |
| **v0.2** | 生产就绪单租户（gRPC · 分布式注册中心 · OpenTelemetry · 持久化审计） | 🚧 下一步 |
| **v0.3** | 多租户与联邦 | 🔜 |
| **v0.4** | 多语言 SDK（TypeScript · Go · Rust）+ 一致性测试套件 | 🔜 |
| **v1.0** | 标准级：第二套独立实现 · 规范冻结 · 安全审计 | 🔜 |

**此处 "alpha" 的含义：** 模块已存在、已通过单元测试（299 个用例通过），并能在 `python main.py` 中端到端运行 —— 但边界情况、性能，以及*第二套独立实现*（让 AURC 称得上真正标准的门槛）仍在路上。冻结的规范见 [PROTOCOL.zh.md](PROTOCOL.zh.md)，后续规划见 [ROADMAP.zh.md](ROADMAP.zh.md)。

> 📌 **杠杆最高的贡献：** 构建第二套 AURC 的独立实现 —— 仅此一举即可让协议从"我们的规范"毕业为"一项标准"。

---

## 文档

| 文档 | 说明 |
|:---|:---|
| [ROADMAP.zh.md](ROADMAP.zh.md) | **持续更新的路线图** —— 北极星、六条工作流、里程碑、非目标 |
| [PROTOCOL.zh.md](PROTOCOL.zh.md) | **完整的 AURC 协议规范** —— 权威参考 |
| [LOOP_ROADMAP.zh.md](LOOP_ROADMAP.zh.md) | **GaiaAgent × Anthropic agentic loop** —— 接入 Claude Agent SDK 作为内层执行引擎的指导 |
| [架构总览](docs/zh/architecture/overview.md) | 系统地图、模块依赖、设计决策 |
| [安全模型](docs/zh/architecture/security-model.md) | 威胁模型、CapABAC 深入解析、委托规则 |
| [桥接开发者指南](docs/zh/architecture/bridge-guide.md) | 如何编写自定义协议桥接 |
| [快速开始](docs/zh/guides/quickstart.md) | 5 分钟上手你的第一个 Agent |
| [工作流模式](docs/zh/guides/workflows.md) | 5 种编排模式 + Claude 集成 |
| [部署指南](docs/zh/guides/deployment.md) | 本地、Docker 与生产部署 |
| [API 参考](docs/zh/api-reference.md) | 完整的 API 文档 |

---

## 适用人群

- **AI 平台工程师**：构建需跨协议边界通信的多 Agent 系统
- **企业架构师**：需要受治理、可审计且具备正规安全的 Agent 交互
- **框架作者**：构建 Agent 框架，希望获得互操作性而不被锁定
- **研究者**：探索 Agent 协作、委托与涌现式多 Agent 行为
- **任何人**：厌倦在 MCP、A2A 和 ACP 之间二选一 —— 通过 GaiaAgent 一起使用它们

---

## 采用者与生态

> 一项协议只有在**两套独立实现**达成一致时才成为标准。GaiaAgent 是 AURC 的参考实现 —— 第二套是你的。

**正在使用 GaiaAgent 或实现 AURC？** 提交 PR 把自己加到下方，或在 [Discussions](https://github.com/gaiaagent/gaiaagent/discussions) 中告诉我们。我们会重点推荐社区构建的桥接、注册中心与语言移植。

| 项目 | 层 | 链接 |
|:---|:---|:---|
| _成为此处首个上榜者。_ | _桥接 / 注册中心 / SDK / 应用_ | _—_ |

**需求：** gRPC · GraphQL · NATS · Kafka 桥接 · TypeScript/Go/Rust 移植 · 分布式注册中心后端。每一项都是很好的 [good first issue](https://github.com/gaiaagent/gaiaagent/contribute)，也是通向 maintainer 身份的路径。

---

## 贡献

GaiaAgent 由日益壮大的开发者、研究者与 AI 爱好者社区共同构建。我们欢迎各种形式的贡献：

- 🐛 **Bug 报告** —— 发现了问题？[提交一个 issue](https://github.com/gaiaagent/gaiaagent/issues)
- 💡 **特性建议** —— 有我们应该桥接的协议？[发起一个讨论](https://github.com/gaiaagent/gaiaagent/discussions)
- 🔧 **代码贡献** —— 参见 [CONTRIBUTING.zh.md](CONTRIBUTING.zh.md) 了解指南
- 📝 **协议变更** —— 需要一份 [AURC-RFC](CONTRIBUTING.zh.md#protocol-changes)

```bash
# 快速开发环境搭建
git clone https://github.com/gaiaagent/gaiaagent
cd gaiaagent
pip install -e ".[dev]"
pytest  # verify everything works
```

---

## 理念

> **"先桥接，不取代"**
>
> 我们不相信 AI Agent 生态需要又一个竞争协议。
> 它需要的是一层**连接层** —— 既尊重在 MCP、A2A 与 ACP 上的既有投入，
> 又提供它们单独都无法提供的运行时、安全与编排能力。
>
> GaiaAgent 就是这一层。

---

## 许可证

| 组件 | 许可证 |
|:---|:---|
| **代码** | [AGPL-3.0](LICENSE) |
| **协议规范** | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) |

---

<p align="center">
  <strong>如果 GaiaAgent 与你对 AI Agent 未来的愿景契合，请给我们一个 ⭐</strong><br/>
  <em>每一颗星都在帮助社区成长。</em>
</p>

<p align="center">
  <a href="https://github.com/gaiaagent/gaiaagent">GitHub</a> ·
  <a href="https://gaiaagent.dev/docs">Documentation</a> ·
  <a href="https://discord.gg/gaiaagent">Discord</a> ·
  <a href="https://pypi.org/project/gaiaagent/">PyPI</a>
</p>
