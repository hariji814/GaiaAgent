# GaiaAgent 快速上手

> 一篇文档讲明白 GaiaAgent 是什么、为什么需要它、怎么用、怎么搭自己的 Agent。
>
> 馃寪 [English](../../en/guides/getting-started.md) | [5 分钟代码走查](quickstart.md) | [架构总览](../architecture/overview.md) | [API 参考](../api-reference.md)

## GaiaAgent 是什么

GaiaAgent 实现了 **AURC（Agent Unified Runtime & Communication）**——一个位于 MCP / A2A / ACP 之上的桥接协议层。它解决一个真实痛点：今天你为 MCP 写的 Agent 没法委派给 A2A Agent，A2A Agent 也调不了 MCP 工具，而且三者都没有 Agent **生命周期**管理。

AURC 用一个规范消息格式（`AURCMessage`）把三者统一起来，并补上了缺失的部分：

1. **生命周期状态机**：9 个状态（REGISTERING →READY →RUNNING →PAUSED →COMPLETED / FAILED / STOPPED，含 RECOVERING），带错误恢复、退避重试、优雅停机。
2. **协议桥接**：MCP / A2A / ACP 消息互译为规范格式，一条审计链路横跨所有协议边界。
3. **可观测性**：防篡改审计日志、实时 HTML 健康仪表盘、Prometheus metrics、跨协议桥接链路追踪。
4. **安全**：基于能力的访问控制（CapABAC）、scope 收窄的委派链防 confused deputy、消息只携带 token 引用而非原始 token。

一句话：**GaiaAgent 是让不同框架的 Agent 互操作的协议层，不是又一个 Agent 框架。**

## 安装

需要 Python 3.10+，用 `uv` 或 `pip` 均可：

```bash
pip install "gaiaagent[http]"
# 或
uv add "gaiaagent[http]"
```

`[http]` 额外依赖会装上 HTTP 传输层（仪表盘、/metrics 端点需要它）。

## 60 秒体验：零配置 Demo

最快了解 AURC 的方式是跑官方 demo——**不需要 API key、不需要任何配置**：

```bash
gaiaagent demo
```

它会启动 3 个 Agent（研究员、分析师、作者），跑一条链式工作流（研究 →分析 →写作），跨越 MCP →A2A →ACP 协议边界，并在浏览器里打开实时仪表盘。所有 LLM 响应来自内置 stub，所以永远跑得起来。

## 接入真实 LLM

想让 demo 调真实模型？加一个 `--api-key`：

```bash
# OpenAI（默认）
gaiaagent demo --api-key sk-xxxx

# Anthropic
gaiaagent demo --api-key sk-ant-xxxx --llm-provider anthropic

# 指定模型
gaiaagent demo --api-key sk-xxxx --model gpt-4o
```

内部用零依赖的 `urllib` 客户端（OpenAI / Anthropic 兼容）。没有 key 或调用失败时会自动回退到 stub 响应，demo 永远不会因为网络问题挂掉。

## 一键创建项目

`gaiaagent init` 会生成一个可直接运行的 Agent 脚手架：

```bash
gaiaagent init myproject
cd myproject
python agent.py
```

生成的 `agent.py` 已经是一个带生命周期、可注册、可调用 skill 的最小 AURC Agent，改一改就是你的第一个 Agent。

## 写第一个 Agent

脚手架生成的结构长这样（手动写也一样）：

```python
from typing import Any
from gaiaagent.sdk.decorators import aurc_agent, skill

@aurc_agent(
    id="aurc:myproject/translator:v1.0",
    display_name="Translator Agent",
    description="翻译文本",
    protocols=["mcp/2025-06-18"],
    tags=["translation", "nlp"],
)
class TranslatorAgent:

    @skill("translate", description="把文本翻译成目标语言")
    async def translate(self, text: str, target_lang: str = "en") -> dict[str, Any]:
        return {"original": text, "translated": f"[{target_lang}] {text}"}

if __name__ == "__main__":
    import asyncio
    from gaiaagent import RuntimeHarness

    async def main() -> None:
        harness = RuntimeHarness()
        agent = TranslatorAgent()
        await harness.register(agent.aurc_descriptor)
        await harness.start(agent.aurc_descriptor.aurc_id)
        print(await agent.translate("你好", "en"))
        await harness.complete(agent.aurc_descriptor.aurc_id)

    asyncio.run(main())
```

要点：

- `@aurc_agent` 装饰器自动生成 `agent.aurc_descriptor`（AgentDescriptor），声明身份、能力、协议支持。
- `@skill` 把方法注册为可被路由调用的技能。
- 生命周期由 `RuntimeHarness` 驱动：`register` →`start` →(运行) →`complete`。

## 桥接协议

桥接器把外部协议消息翻译成规范 `AURCMessage`，反之亦然：

```python
from gaiaagent.bridges.base import MCPBridge

mcp_bridge = MCPBridge()

mcp_request = {
    "jsonrpc": "2.0",
    "id": "req-1",
    "method": "tools/call",
    "params": {"name": "web-search", "arguments": {"query": "AI protocols"}},
}

aurc_message = await mcp_bridge.translate_to_aurc(mcp_request)
print(aurc_message.body.skill)   # "web-search"

# 反向：AURC -> MCP
external = await mcp_bridge.translate_from_aurc(aurc_message)
```

三座桥各有对应类：`MCPBridge`、`A2ABridge`（`gaiaagent.bridges.a2a`）、`ACPBridge`（`gaiaagent.bridges.acp`）。注册到路由器后，发往 `mcp:...` / `a2a:...` / `acp:...` 前缀的消息会自动走对应桥接转发器。

## 消息路由

`MessageRouter` 负责把消息送到正确的处理器或桥接转发器：

```python
from gaiaagent.bus.router import MessageRouter
from gaiaagent.core.message import AURCMessage, MessageBody
from gaiaagent.core.types import MessageDirection

router = MessageRouter()

async def handle(msg: AURCMessage):
    return {"status": "ok", "skill": msg.body.skill}

router.register_handler("aurc:myproject/translator:v1.0", handle)

# 发一条直连消息
msg = AURCMessage(
    source="aurc:myproject/orchestrator:v1.0",
    target="aurc:myproject/translator:v1.0",
    type=MessageDirection.REQUEST,
    body=MessageBody(method="invoke", skill="translate", params={"text": "Hello"}),
)
result = await router.route(msg)
print(router.stats.direct)   # 1
```

路由支持直连、桥接、广播（订阅组）、通配符、TTL 跳数限制、死信队列。

## 可观测性

```python
from gaiaagent.observability.dashboard import HealthDashboard, DashboardAPI
from gaiaagent.security.audit import AuditLog

audit = AuditLog(max_entries=10_000)
dashboard = HealthDashboard(harness, audit=audit, router=router)
api = DashboardAPI(dashboard)

print(dashboard.get_system_health())      # 系统级健康
print(await harness.health_check_all())   # 所有 Agent 健康报告
```

`gaiaagent demo` 会把仪表盘挂在 HTTP 上：`/dashboard`（HTML）、`/health`（JSON）、`/metrics`（Prometheus 文本格式）。

## 下一步

- [5 分钟代码走查](quickstart.md)：完整代码片段（含安全授权）
- [架构总览](../architecture/overview.md)：核心抽象与数据流
- [桥接开发指南](../architecture/bridge-guide.md)：怎么写自己的协议桥
- [工作流](workflows.md)：PromptChain / 并行 fan-out / orchestrator-workers
- [部署](deployment.md)：HTTP 传输与生产部署
- [API 参考](../api-reference.md)

## 为什么是 Apache-2.0

AURC 早期是 AGPL-3.0。为了让协议真正被采纳，我们迁移到了 **Apache-2.0**——足够宽松，企业可以无顾虑接入，兼容专有和 GPL 项目，也是业界最被理解信任的开源协议之一。详见 [Why GaiaAgent](../../why-gaiaagent.md)。
