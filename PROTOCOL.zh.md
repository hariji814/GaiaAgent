# AURC 协议规范 v0.1

**Agent 统一运行时与通信协议**

> 🌐 [English](PROTOCOL.md)
> **[← 返回 README](README.zh.md)** | [架构](docs/zh/architecture.md) | [API 参考](docs/zh/api-reference.md) | [快速开始](docs/zh/guides/quickstart.md)
>
> 状态：稳定（v0.1 冻结；向后兼容承诺于 v1.0）
> 版本：0.1.0
> 许可证：CC BY-SA 4.0（规范）/ Apache-2.0（实现）

---

## 目录

1. [介绍](#1-introduction)
2. [设计原则](#2-design-principles)
3. [架构概览](#3-architecture)
4. [L1：Agent 身份](#4-l1-agent-identity)
5. [L2：运行时 Harness](#5-l2-runtime-harness)
6. [L3：统一消息总线](#6-l3-unified-message-bus)
7. [L4：协议桥接](#7-l4-protocol-bridges)
8. [L5：上下文关联](#8-l5-context-correlation)
9. [L6：安全](#9-l6-security)
10. [L7：发现](#10-l7-discovery)
11. [L0：传输](#11-l0-transport)
12. [与现有协议对比](#12-comparison)
13. [使用场景](#13-use-cases)
14. [SDK 设计](#14-sdk-design)
15. [路线图](#15-roadmap)
16. [术语表](#16-glossary)

---

## 1. 介绍

### 1.1 动机

2025-2026 年的 AI Agent 生态系统产生了多种通信协议，各自解决特定层级：

- **MCP**（Anthropic）：Agent 与工具之间的通信
- **A2A**（Google）：Agent 之间的任务委派
- **ACP**（IBM）：轻量级 REST 消息
- **ANP**（社区）：去中心化身份

**问题：** 没有任何一种方案能够桥接这些协议，或提供 Agent 运行时生命周期管理。使用 MCP 调用工具的 Agent 无法无缝委派给 A2A Agent，而两种协议都不管理 Agent 状态、错误恢复或上下文持久化。

**AURC 通过以下方式解决该问题：**
1. 用于 Agent 生命周期管理的**运行时 Harness**
2. 用于在 MCP、A2A 和 ACP 之间翻译的**协议桥接**
3. 跨所有协议通用的**统一身份**系统
4. 协议层面的**安全强制执行**

### 1.2 范围

本规范定义：
- AURC 消息格式与协议语义
- 运行时 Harness 状态机与接口
- MCP 与 A2A 的协议桥接接口
- 安全模型（CapABAC）与委派链校验
- Agent 发现与能力匹配

本规范不定义：
- AI Agent 的内部实现
- LLM 模型选择或推理逻辑
- Agent 交互的 UI/UX
- 具体传输实现（仅定义接口）

---

## 2. 设计原则

| # | 原则 | 含义 |
|---|---|---|
| 1 | **桥接优先** | 不发明新的通信原语；统一现有协议 |
| 2 | **运行时为核心** | Agent = 模型 + Harness；Harness 是一等公民 |
| 3 | **渐进复杂度** | 核心简单，企业特性作为可选模块 |
| 4 | **协议无关身份** | 一个 Agent，一个跨所有协议通用的身份 |
| 5 | **安全第一** | 权限可在协议层面强制执行，而非仅声明 |

---

## 3. 架构

### 3.1 分层模型

```
┌──────────────────────────────────────────────────────────────┐
│ L7  发现层                                                     │
│     Agent 注册、能力匹配、基于健康的路由                        │
├──────────────────────────────────────────────────────────────┤
│ L6  安全层                                                     │
│     认证、CapABAC 授权、委派链、审计                            │
├──────────────────────────────────────────────────────────────┤
│ L5  上下文关联层                                               │
│     跨协议上下文追踪、权限传播                                  │
├──────────────────────────────────────────────────────────────┤
│ L4  协议桥接层                                                 │
│     MCP Bridge / A2A Bridge / ACP Bridge / 自定义 Bridge      │
├──────────────────────────────────────────────────────────────┤
│ L3  统一消息总线                                               │
│     规范消息格式、路由、会话管理                                │
├──────────────────────────────────────────────────────────────┤
│ L2  运行时 Harness                                            │
│     生命周期、健康监控、上下文/记忆、恢复                       │
├──────────────────────────────────────────────────────────────┤
│ L1  Agent 身份                                                │
│     AURC ID、能力声明、协议绑定                                 │
├──────────────────────────────────────────────────────────────┤
│ L0  传输层                                                    │
│     HTTP/2、WebSocket、stdio、gRPC                            │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 角色

| 角色 | 描述 |
|------|------|
| **AURC Host** | 运行 Harness、管理 Agent 生命周期的主进程 |
| **AURC Agent** | 在 Harness 中注册、拥有 AURC ID 的 AI Agent |
| **AURC Router** | 在 Agent 之间投递消息的消息路由器 |
| **Protocol Bridge** | 在 AURC 消息与外部协议之间翻译的适配器 |
| **AURC Registry** | 具备能力匹配的 Agent 发现服务 |

---

## 4. L1：Agent 身份

### 4.1 AURC ID 格式

AURC 采用**分层 URN** 格式实现全局唯一、人类可读的 Agent 标识：

```
aurc:{namespace}/{agent_name}:{version}

Examples:
  aurc:gaia/researcher:v1.2
  aurc:mycompany/code-reviewer:v2.0
  aurc:community/translator:v1.0
```

**设计理由：**
- URN 比 DID 更简单（无区块链依赖）
- 命名空间提供去中心化唯一性（类似 Docker Hub org/image）
- 版本固定确保可复现性
- DID 的 `did:wba` 方法可作为可选的补充身份层

### 4.2 Agent Descriptor

Agent Descriptor 是 AURC Agent 的身份文档。它是身份、能力、协议、运行时要求与安全的唯一事实来源。

```json
{
  "schema_version": "aurc://spec/v0.1/agent-descriptor.json",
  "aurc_id": "aurc:gaia/researcher:v1.2",
  "display_name": "Research Agent",
  "description": "Deep research with multi-source analysis",
  "version": "1.2.0",
  "author": "GaiaAgent Team",
  "license": "Apache-2.0",
  "capabilities": {
    "provides": [
      {
        "skill_id": "deep-research",
        "name": "Deep Research",
        "description": "Multi-source research and synthesis",
        "input_schema": {
          "type": "object",
          "properties": {
            "query": {"type": "string"},
            "depth": {"type": "string", "enum": ["shallow", "medium", "deep"]}
          },
          "required": ["query"]
        },
        "output_schema": {"type": "object"}
      }
    ],
    "consumes": ["web-search", "document-reader"]
  },
  "protocols": {
    "native": "aurc/0.1",
    "bridges": ["mcp/2025-06-18", "a2a/1.0"]
  },
  "runtime": {
    "max_concurrency": 10,
    "supports_streaming": true,
    "supports_pause": true,
    "timeout_seconds": 3600
  },
  "auth": {
    "methods": ["api_key", "oauth2"],
    "scopes": ["research:read", "research:write"]
  }
}
```

---

## 5. L2：运行时 Harness

这是 AURC 的**核心创新**——MCP、A2A 与 ACP 均不提供 Agent 生命周期管理。

### 5.1 状态机

```
REGISTERING → READY ⇄ RUNNING → COMPLETED
                           ↕         ↕
                        PAUSED    FAILING → RECOVERING → READY
                                                ↕
                                             FAILED / STOPPED
```

| 状态 | 描述 |
|-------|------|
| `REGISTERING` | Agent 正在注册其 descriptor 与能力 |
| `READY` | Agent 已注册，等待任务 |
| `RUNNING` | Agent 正在执行任务 |
| `PAUSED` | Agent 执行已暂停（人工审批、资源等待等） |
| `FAILING` | Agent 遇到错误，尝试自动恢复 |
| `RECOVERING` | Agent 正在从失败中恢复 |
| `COMPLETED` | 任务成功完成（终态） |
| `FAILED` | 任务失败且无法恢复（终态） |
| `STOPPED` | Agent 被外部停止（终态） |

### 5.2 错误恢复策略

| 触发条件 | 动作 | 描述 |
|---------|------|------|
| `timeout` | `retry_with_backoff` | 指数退避重试（1s、5s、15s） |
| `tool_error` | `retry_alternative` | 尝试替代工具/技能 |
| `context_overflow` | `compact_and_retry` | 摘要最旧的上下文后重试 |
| `auth_expired` | `refresh_and_retry` | 刷新凭据后重试 |
| `unrecoverable` | `escalate` | 升级至人工操作员 |

### 5.3 上下文作用域

| 作用域 | 生命周期 | 可见性 | 用例 |
|-------|----------|--------|------|
| `session` | 单个任务 | 仅当前 Agent | 临时计算状态 |
| `agent` | Agent 生命周期 | 仅当前 Agent | 学习偏好、历史 |
| `shared` | 跨 Agent | 已授权的 Agent 组 | 共享知识库 |
| `global` | Harness 生命周期 | 所有 Agent（需权限） | 系统配置 |

### 5.4 人工介入（Human-in-the-Loop）

AURC 通过 HITL 协议标准化人工干预：

```json
{
  "hitl_request": {
    "id": "hitl-20260624-001",
    "agent_id": "aurc:gaia/researcher:v1.2",
    "type": "approval",
    "priority": "normal",
    "context": {
      "question": "Found 3 conflicting data sources, need human judgment",
      "options": [
        {"id": "trust-source-a", "label": "Trust Source A (academic journals)"},
        {"id": "investigate-further", "label": "Investigate further"}
      ],
      "timeout_seconds": 3600,
      "timeout_action": "pause_and_wait"
    }
  }
}
```

---

## 6. L3：统一消息总线

### 6.1 消息格式

JSON 是规范格式（人类可读、生态广泛）。MessagePack 作为可选的高性能编码受支持。

```json
{
  "aurc_version": "0.1",
  "message_id": "msg-20260624-a1b2c3",
  "correlation_id": "corr-xyz-789",
  "trace_id": "trace-dist-456",
  "timestamp": "2026-06-24T10:30:00.000Z",
  "source": "aurc:gaia/orchestrator:v1.0",
  "target": "aurc:gaia/researcher:v1.2",
  "type": "request",
  "protocol_context": {
    "origin_protocol": "aurc",
    "bridged_from": null,
    "bridge_chain": []
  },
  "session": {
    "session_id": "session-20260624-001",
    "conversation_id": "conv-abc",
    "turn": 5
  },
  "body": {
    "method": "invoke",
    "skill": "deep-research",
    "params": {
      "query": "2026 AI Agent protocol interoperability",
      "depth": "deep"
    }
  },
  "routing": {
    "ttl_hops": 5,
    "priority": "normal",
    "timeout_ms": 30000
  },
  "security": {
    "scopes": ["research:read"],
    "delegation_chain": [
      {
        "from": "aurc:user/alice:v1.0",
        "to": "aurc:gaia/orchestrator:v1.0",
        "scopes": ["research:read", "web:search"],
        "timestamp": "2026-06-24T10:00:00.000Z"
      }
    ]
  }
}
```

### 6.2 消息类型

| 类型 | 方向 | 描述 |
|------|------|------|
| `request` | 发起方 → 目标方 | 请求某项操作，需要响应 |
| `response` | 目标方 → 发起方 | 对请求的回复 |
| `notification` | 单向 | 事件通知，无需响应 |
| `stream` | 目标方 → 发起方 | 流式数据块 |
| `delegation` | Agent → Agent | 携带完整上下文的任务委派 |
| `handoff` | Agent → Agent | 任务所有权转移 |
| `heartbeat` | 双向 | 保活信号 |

---

## 7. L4：协议桥接

### 7.1 Bridge 接口

每个 Bridge 必须实现：

```python
class ProtocolBridge(Protocol):
    source_protocol: str              # 例如 "mcp/2025-06-18"
    def can_bridge(src, tgt) -> bool
    async def translate_to_aurc(msg) -> AURCMessage
    async def translate_from_aurc(msg) -> ExternalMessage
    async def map_capabilities(caps) -> list[AURCCapability]
```

### 7.2 MCP Bridge 映射

| MCP 方法 | AURC 等价 |
|------------|----------------|
| `tools/call` | `request`（method=invoke） |
| `tools/list` | `request`（method=list_capabilities） |
| `resources/read` | `request`（method=load_context） |
| `initialize` | `notification`（event=mcp_server_initialized） |

### 7.3 A2A Bridge 映射

| A2A 方法 | AURC 等价 |
|------------|----------------|
| `tasks/send` | `delegation` |
| `tasks/get` | `request`（method=query_task_status） |
| `tasks/cancel` | `notification`（event=task_cancelled） |
| 任务状态变更 | `notification` / `stream` |

### 7.4 能力映射

| AURC 概念 | MCP | A2A | ACP |
|-------------|-----|-----|-----|
| Skill | Tool | Skill | Endpoint |
| Agent Descriptor | Server Capabilities | Agent Card | Service Registration |
| Request | tools/call | tasks/send | POST /tasks |
| Context | Resources | Messages/Artifacts | Payload |

---

## 8. L5：上下文关联

### 8.1 跨协议追踪

每条消息携带 `correlation_id` 与 `bridge_chain`，追踪其跨协议边界的路径：

```json
{
  "correlation_id": "corr-xyz-789",
  "bridge_chain": [
    {"hop": 1, "from": "a2a/1.0", "to": "aurc/0.1"},
    {"hop": 2, "from": "aurc/0.1", "to": "mcp/2025-06-18"}
  ]
}
```

### 8.2 权限传播规则

1. **权限范围只能收窄，绝不放宽**——每一跳委派只能减少权限
2. **跨 Bridge 权限取交集**——桥接后权限 = AURC ∩ 外部协议
3. **委派链可审计**——每一跳都被记录且可校验

---

## 9. L6：安全

### 9.1 认证方式

| 方式 | 用例 | 安全级别 |
|--------|------|:---:|
| API Key | 开发、内部服务 | ★★☆ |
| OAuth 2.1 | 用户授权场景 | ★★★★ |
| mTLS | 企业级 Agent 互联 | ★★★★★ |
| JWT + JWKS | 跨组织联邦 | ★★★★ |

### 9.2 CapABAC 授权

AURC 将基于能力的安全与基于属性的访问控制相结合：

```json
{
  "policy": {
    "subject": "aurc:gaia/researcher:v1.2",
    "conditions": [
      {
        "resource_type": "web-search",
        "actions": ["execute"],
        "constraints": {
          "max_queries_per_hour": 100,
          "allowed_domains": ["*.edu", "*.gov", "arxiv.org"]
        }
      }
    ],
    "delegation": {
      "allowed": true,
      "max_depth": 3,
      "scope_reduction_required": true
    }
  }
}
```

### 9.3 解决 MCP 的混淆代理问题

MCP 的核心安全问题：服务器代表用户执行操作，却无法区分或强制执行用户被授权可做的事。

**AURC 的解决方案：**

1. 每次调用携带记录完整权限路径的**委派链**
2. Bridge 层**强制执行权限映射**——校验每一跳的合法性
3. **不可变审计日志**——所有跨协议调用均被记录，以满足合规要求

---

## 10. L7：发现

### 10.1 发现模式

| 模式 | 用例 | 机制 |
|------|------|------|
| Local | 单机开发 | 内存中的 Agent 列表 |
| File | 小型团队 | YAML/JSON 配置 |
| HTTP Registry | 生产环境 | REST API 注册服务 |
| mDNS | 局域网发现 | 多播 DNS 自动发现 |
| Federation | 跨组织 | 注册表同步协议 |

### 10.2 发现流程

```
1. 查询注册表 → 按能力、标签、协议检索
2. 能力匹配 → 按技能契合度评分
3. 健康路由 → 优先选择健康、低延迟实例
4. 协议协商 → 确认双方支持的协议
5. 建立连接 → 完成认证握手
```

---

## 11. L0：传输

| 传输方式 | 用例 | 特性 |
|-----------|------|------|
| HTTP/2 | 生产、跨网络 | 可靠、通用、多路复用 |
| WebSocket | 实时双向 | 低延迟、持久连接 |
| stdio | 本地开发、CLI | 最快、零网络开销 |
| gRPC | 高性能内部 | 二进制编码、强类型、流式 |

传输在连接建立阶段协商：

```json
{
  "offered": [
    {"type": "http2", "url": "https://agent.example.com/aurc"},
    {"type": "websocket", "url": "wss://agent.example.com/aurc/ws"}
  ],
  "preferred": "http2"
}
```

---

## 12. 与现有协议对比

| 能力 | MCP | A2A | ACP | ANP | **AURC** |
|---|:---:|:---:|:---:|:---:|:---:|
| Agent 身份 | ✗ | Agent Card | ✗ | DID | **AURC ID** |
| 工具调用 | ✓ | ✗ | ✓ | ✗ | **经 Bridge** |
| Agent 间通信 | ✗ | ✓ | ✓ | ✓ | **经 Bridge** |
| 运行时生命周期 | ✗ | 任务状态 | ✗ | ✗ | **✓（核心）** |
| 上下文/记忆 | Resources | ✗ | ✗ | ✗ | **✓（多作用域）** |
| 跨协议互通 | ✗ | ✗ | ✗ | ✗ | **✓（核心）** |
| 权限强制执行 | ✗ | ✗ | ✗ | ✗ | **✓（CapABAC）** |
| 委派链审计 | ✗ | ✗ | ✗ | ✗ | **✓** |
| 错误恢复 | ✗ | ✗ | ✗ | ✗ | **✓（策略引擎）** |
| 人工介入 | ✗ | Input-Required | ✗ | ✗ | **✓（标准化）** |
| 去中心化身份 | ✗ | ✗ | ✗ | ✓ | **可选（DID 兼容）** |

---

## 13. 使用场景

### 场景 1：AURC Agent 调用 MCP 工具

```
1. AURC Orchestrator 需要网络搜索
2. 查询注册表 → 找到 MCP Web Search Server
3. 经 MCP Bridge 建立连接
4. AURC 消息 → 翻译为 MCP tools/call
5. MCP Server 返回结果 → 翻译回 AURC
6. 结果交付给 Researcher Agent
```

### 场景 2：AURC Agent 委派给 A2A Agent

```
1. AURC Orchestrator 收到复杂研究任务
2. 发现外部专家 Agent（仅支持 A2A）
3. 经 A2A Bridge 创建 A2A Task
4. AURC 消息 → 翻译为 A2A tasks/send
5. A2A Agent 通过 SSE 流式推送进度
6. A2A 事件 → 翻译为 AURC stream 消息
7. 任务完成 → AURC 上下文与追踪更新
```

### 场景 3：多协议混合工作流

```
1. 用户请求 → AURC Orchestrator
2. Orchestrator 委派子任务：
   ├─ 子任务 A → AURC Agent（原生，直接通信）
   ├─ 子任务 B → MCP Agent（经 MCP Bridge 调用工具）
   └─ 子任务 C → A2A Agent（经 A2A Bridge 委派）
3. 所有子任务通过 correlation_id 关联
4. 权限通过 delegation_chain 统一
5. 结果聚合 → 返回用户
```

---

## 14. SDK 设计

### 14.1 声明式 Agent 定义

```python
@aurc_agent(
    id="aurc:gaia/researcher:v1.2",
    capabilities=["deep-research", "summarize"]
)
class ResearchAgent:
    @skill("deep-research")
    async def research(self, query: str, depth: str = "medium") -> dict:
        context = await self.harness.load_context("previous_searches", scope="agent")
        result = await self.search_web(query)
        await self.harness.save_context("previous_searches", context + [result])
        return result
```

### 14.2 设计原则

| 原则 | 描述 |
|-----------|------|
| 装饰器驱动 | 使用 Python 装饰器实现零样板 Agent 声明 |
| 自动注入 | Harness 自动管理生命周期 |
| 协议透明 | Agent 代码无需感知使用的是 MCP 还是 A2A |
| 类型安全 | Python 类型提示 + Pydantic 进行 schema 校验 |
| 可测试 | 提供 MockHarness 用于单元测试 |

---

## 15. 路线图

**AURC v0.1** 的协议范围即本文档所述全部内容（L0–L7、MCP/A2A/ACP 桥接、CapABAC、9 态生命周期），为实现者提供冻结的参考。

项目的持续演进路线图——版本里程碑（v0.2 → v1.0）、六大赛道（运行时、互通、安全、可观测性、生态、标准化）、验收标准与非目标——单独维护：

➡️ **[ROADMAP.zh.md](ROADMAP.zh.md)**

协议级变更（新消息类型、生命周期状态、安全模型修订、Bridge 接口要求）受 [AURC-RFC 流程](CONTRIBUTING.zh.md#protocol-changes) 治理，需 ≥2 名维护者批准及 2 周公开评议。当**第二个独立实现**通过一致性测试集时，AURC 即成为公认标准。

---

## 16. 术语表

| 术语 | 定义 |
|------|------------|
| **Harness** | Agent 运行时管理层——生命周期、上下文、错误恢复 |
| **Bridge** | 在 AURC 与外部协议之间翻译的协议适配器 |
| **Skill** | Agent 提供的某项具体能力 |
| **Delegation Chain** | 从发起者到执行者的完整权限路径 |
| **CapABAC** | 基于能力与属性的访问控制——AURC 的混合授权模型 |
| **AURC ID** | URN 格式的全局唯一 Agent 标识符 |
| **HITL** | 人工介入——标准化的人工干预协议 |
