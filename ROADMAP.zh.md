# GaiaAgent 路线图

> 🌐 [English](ROADMAP.md)
> **[← 返回 README](README.zh.md)** | [协议规范](PROTOCOL.zh.md) | [贡献指南](CONTRIBUTING.zh.md)
>
> GaiaAgent 与 AURC 协议的公开、持续演进计划。

---

## 北极星

> **让 AURC 成为所有 AI Agent 协议之下的共享基底——如同 TCP/IP 之于一百种应用协议。**

当一个协议拥有**两个独立的实现**达成一致，它才成为标准。GaiaAgent 是*参考实现*；本路线图是从"单一实现、alpha"走向"规范冻结、多语言、生产级、多厂商"的路径。

---

## 状态图例

| 标记 | 含义 |
|:---:|---|
| ✅ | 已发布（`v0.1.0` alpha，端到端可用，API 仍可能变动） |
| 🚧 | 进行中 |
| 🔜 | 已规划，未开始 |
| 💡 | RFC 讨论中或征集实现 |
| ❌ | 明确不做（见[非目标](#非目标)） |

---

## 版本里程碑

| 版本 | 主题 | 解锁能力 | 状态 |
|:---:|---|---|:---:|
| **v0.1** | 单进程参考实现 | 3 个桥接 · 9 态生命周期 · CapABAC · 5 种工作流模式 · CLI · Claude | ✅ Alpha |
| **v0.2** | 单租户生产可用 | gRPC 传输 · 分布式注册中心 · OpenTelemetry · 持久化审计 | 🚧 下一个 |
| **v0.3** | 多租户与联邦 | 联邦发现 · 租户隔离 · 限流策略 · 背压 | 🔜 |
| **v0.4** | 多语言 SDK | TypeScript · Go · Rust 客户端 SDK · 规范一致性测试集 | 🔜 |
| **v1.0** | 标准级 | 第二个独立实现 · 规范冻结 · 向后兼容保证 · 安全审计 | 🔜 |

> 版本日期有意不固定——达到验收标准才发布，而非按日历。进展见 [Discussions](https://github.com/gaiaagent/gaiaagent/discussions) 与 [Issues](https://github.com/gaiaagent/gaiaagent/issues)。

---

## 工作流赛道

工作分为六个并行赛道。每项列出**做什么**、**为什么**、**验收标准**。

### 🧠 赛道 1 — 运行时与生命周期

| 事项 | 状态 | 为什么 |
|:---|:---:|---|
| 9 态生命周期状态机 | ✅ | AURC 之前没有协议标准化 Agent 生命周期 |
| 基于策略的错误恢复（5 种策略） | ✅ | Agent 必须能自愈，而非直接崩溃 |
| 4 作用域上下文存储（session/agent/shared/global） | ✅ | 跨任务与跨 Agent 的内存隔离 |
| 通过 `asyncio.Event` 实现暂停/恢复 | ✅ | HITL 卡点与资源等待 |
| **持久化生命周期**（扛住宿主重启） | 🔜 | 需要超越进程生命周期的长时 Agent |
| **检查点与回溯** | 💡 | 调试并重放多 Agent 运行 |
| **资源配额与背压** | 🔜 | 多租户安全 |

### 🌉 赛道 2 — 互操作（桥接）

| 事项 | 状态 | 为什么 |
|:---|:---:|---|
| MCP 桥接（JSON-RPC ↔ AURC） | ✅ | 工具是采用最广的层 |
| A2A 桥接（tasks/send ↔ AURC） | ✅ | Agent 间委托 |
| ACP 桥接（HTTP envelope ↔ AURC） | ✅ | 轻量级 REST 消息 |
| 双向上下文保留（`correlation_id`、`bridge_chain`） | ✅ | 跨跳的可追溯性 |
| **gRPC 桥接** | 🔜 | 高性能内部网格 |
| **GraphQL 桥接** | 💡 | Schema 优先生态 |
| **NATS / Kafka / AMQP 桥接** | 💡 | 事件驱动的 Agent 主干 |
| **桥接一致性测试集** | 🔜 | 第三方桥接必须可被证明正确 |

### 🔒 赛道 3 — 安全与治理

| 事项 | 状态 | 为什么 |
|:---|:---:|---|
| API Key + JWT + mTLS 就绪认证 | ✅ | 从开发到生产的灵活性 |
| CapABAC 授权引擎 | ✅ | 细粒度、基于约束的访问 |
| 委托链验证（仅可收窄 scope） | ✅ | 解决 MCP 的 confused deputy 问题 |
| 只追加审计日志 | ✅ | 合规与取证 |
| **可插拔审计落地**（S3、SIEM、opaque token） | 🔜 | 企业合规管线 |
| **租户级授权与限流** | 🔜 | 多租户隔离 |
| **签名委托链**（密码学） | 💡 | 跨组织的不可抵赖 |
| **第三方安全审计** | 🔜 | v1.0 之前的信任基础 |

### 📊 赛道 4 — 可观测与运维

| 事项 | 状态 | 为什么 |
|:---:|:---:|---|
| 健康面板（HTML + JSON） | ✅ | 运维可见性 |
| 路由统计与死信队列 | ✅ | 调试无法投递的消息 |
| 状态变化监听 | ✅ | 告警与指标导出 |
| HTTP/2 + WebSocket 传输 | ✅ | 生产 + 实时 |
| **Prometheus 指标导出**（`/metrics`） | ✅ | 用任意 Prometheus 兼容采集器抓取 AURC |
| **结构化 `bridge_chain` 追踪** | ✅ | 通过 `correlation_id` 还原请求的跨协议路径 |
| **OpenTelemetry 追踪** | 🔜 | 将 span 上报至分布式后端（追踪记录器为进程内基础） |
| **gRPC 传输** | 🔜 | 高吞吐内部部署 |

### 🌐 赛道 5 — 生态与 SDK

| 事项 | 状态 | 为什么 |
|:---:|:---:|---|
| `@aurc_agent` / `@skill` Python 装饰器 | ✅ | 30 秒定义一个 Agent |
| Claude 集成（agentic loop、tool use） | ✅ | 参考 LLM 后端 |
| `claude` CLI 作 loop 后端（`agentic_loop` 委托给 `claude -p --output-format stream-json`，安全子进程，防御性解析） | ✅ | Loop Roadmap Step 2 —— 见 [LOOP_ROADMAP.zh.md](LOOP_ROADMAP.zh.md) |
| AURC MCP server（`gaiaagent.mcp` —— 把 `@skill` agent 暴露为 CLI 可调的 MCP 工具） | ✅ | Loop Roadmap Step 1 基石 —— 协议层总线路由 |
| `aurc` CLI（serve/validate/bridge test/registry export） | ✅ | 无需写代码的开发体验 |
| 端到端示例 + 多 Agent 示例 | ✅ | 可复制粘贴的起点 |
| **可插拔 LLM 后端**（不限于 Claude） | 🔜 | 不锁定厂商 |
| **TypeScript SDK** | 🔜 | Node/浏览器 Agent 生态 |
| **Go SDK** | 🔜 | 基础设施侧 Agent |
| **Rust SDK** | 🔜 | 嵌入式 / 边缘 Agent |
| **桥接与插件市场** | 💡 | 可被发现的社区扩展 |

### 📜 赛道 6 — 标准化

| 事项 | 状态 | 为什么 |
|:---:|:---:|---|
| AURC v0.1 规范（PROTOCOL.md，CC BY-SA 4.0） | ✅ | 面向实现者的冻结参考 |
| AURC-RFC 流程 | ✅ | 受治理的协议演进 |
| **一致性测试集** | 🔜 | "AURC-compatible" 必须有明确含义 |
| **第二个独立实现** | 🔜 | 让 AURC 成为真正标准的门槛 |
| **W3C 风格的 trace-context 互操作** | 💡 | 与更广泛的追踪标准对齐 |
| **规范 v1.0 冻结 + 兼容保证** | 🔜 | 为生产采用者提供稳定性 |

---

## 近期已完成（v0.1.0 alpha）

一份面向可信度的快照，展示今天已经端到端跑通的内容（`python main.py` 会运行其中的全部）：

- ✅ 8 层栈：L0 传输 → L7 发现，每层可独立测试
- ✅ `AURCId` URN 身份 + `AgentDescriptor` 身份文档
- ✅ 9 态生命周期引擎 + 5 策略错误恢复
- ✅ 统一消息总线：`MessageRouter`（direct/bridge/broadcast/dead-letter）、`SessionManager`、JSON/NDJSON 编解码
- ✅ 针对 **MCP、A2A、ACP** 的双向桥接，含能力映射
- ✅ HTTP/2 + WebSocket 传输
- ✅ CapABAC：API Key/JWT 认证、授权引擎、委托链验证、只追加审计日志
- ✅ `LocalRegistry`，支持按能力/标签/协议匹配
- ✅ 5 种编排模式 + `DynamicWorkflowEngine`
- ✅ Claude 集成：`ClaudeLLM`、agentic loop、tool use、`ClaudeAgent` 基类
- ✅ `aurc` CLI + 健康面板
- ✅ Prometheus 指标导出（`/metrics`）+ 结构化 `bridge_chain` 追踪

---

## 非目标

明确"不做什么"与"做什么"同等重要。以下为刻意排除项：

| 非目标 | 理由 |
|:---|:---|
| ❌ **又一个竞争协议** | AURC *桥接* MCP/A2A/ACP，而非取代它们。"Bridge First, Don't Replace." |
| ❌ **自研大模型 / 模型训练** | Claude 只是其中一个可插拔后端。GaiaAgent 对模型保持协议无关。 |
| ❌ **闭源 SaaS 运行时** | 参考实现为 Apache-2.0；规范为 CC BY-SA 4.0。天生开放。 |
| ❌ **绑定单一语言** | Python 是参考实现；TS/Go/Rust SDK 列入路线图正是为了避免这一点。 |
| ❌ **区块链/DID 依赖** | AURC ID 是简单的 URN——无需账本、无需密钥恢复仪式即可上手。 |
| ❌ **v1.0 后破坏性变更** | 1.0 之后，向后兼容是硬性契约，由 RFC 治理。 |

---

## 如何参与推动

- **挑选一个 `💡` 或 `🔜` 事项** —— 这些是开放前沿。在 [Discussions](https://github.com/gaiaagent/gaiaagent/discussions) 评论认领。
- **提议新桥接**（gRPC、GraphQL、NATS、Kafka……）——见[桥接开发者指南](docs/zh/architecture/bridge-guide.md)。
- **修改协议** —— 任何规范性变更都走 [AURC-RFC 流程](CONTRIBUTING.zh.md#protocol-changes)。
- **构建第二个实现** —— 让 AURC 成为标准的最高杠杆贡献。

### 适合入手

- 一个针对 ACP 桥接的 `map_capabilities` 往返测试
- 一个 `SlackBridge` 参考实现（见[桥接指南](docs/zh/guides/bridges.md)）
- 一个基于 `BridgeTraceRecorder` 的 OpenTelemetry 导出器（赛道 4）
- 一个针对 AURC HTTP 传输的 TypeScript 客户端

---

*本路线图是一份持续演进的文档。欢迎通过 PR 编辑——请打上 `roadmap` 标签，以便在正式落地前讨论范围。*
