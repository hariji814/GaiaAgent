# Loop 路线图 — GaiaAgent × Claude Code CLI

> 🌐 [English](LOOP_ROADMAP.md)
> **[← 返回 README](README.zh.md)** | [路线图](ROADMAP.zh.md) | [协议规范](PROTOCOL.zh.md)
>
> 将 **Claude Code CLI**(`claude`)——参考实现 agentic loop——作为 AURC 运行时内层执行引擎的指导文档。不引 Python SDK 依赖;大家本机都有的 CLI 即引擎。

---

## 状态

| | |
|:---|:---|
| **当前状态** | ✅ **已发布。** `ClaudeLLM.agentic_loop` 在 `claude` CLI 在 PATH 时委托给 `claude -p --output-format stream-json`,带安全子进程包装(并发 stdout/stderr 排空、超时、取消即 kill)与防御性 stream-json 解析;否则降级到内置 `anthropic` 循环。✅ **MCP server 已发布**(`gaiaagent.mcp.server`)——把 AURC `@skill` agent 暴露为 MCP 工具,CLI 的工具调用在协议层进入总线。2322 测试通过。`codex` CLI(`codex exec --json`)现为第二个参考后端,通过同一适配器形状;参数 `backend`(`claude` / `codex` / `auto`)使可插拔缝变为真实,而非仅愿景。 |
| **诚实评估** | README 的"Claude-native"对*循环委托*与 skill 的 *MCP 暴露*已是实质承诺。**现已接通**:`backend` 参数使可插拔 loop 缝变为真实 — `claude` 与 `codex` CLI 后端可互换,`auto` 选择 PATH 上第一个可用 CLI。**尚未接通**:生命周期(harness 不驱动 `agentic_loop`)、CLI 工具调用的 CapABAC 鉴权、session/resume 与 `ContextStore` 绑定。概念映射表标注了每行状态。 |
| **依赖状态** | **不新增 Python 依赖。** `claude` CLI 是外部运行时要求,运行时在 PATH 上探测。`pyproject.toml` 的 `claude` extra 保留 `anthropic>=0.40` 作降级路径。 |

> 本文档**持续更新**,状态反映 HEAD 处代码。CLI 的 `stream-json` 事件 schema 采用防御性解析(全用 `.get()`、`isinstance` 守卫、空流 → 报错而非静默成功)。

---

## 为什么

2025–2026 产出了 **agentic loop** 这一标准执行范式:模型自主决定"下一步调哪个工具",执行,把结果喂回,继续直到完成。**Claude Code CLI** 是该循环的生产级参考实现——本项目用户本就运行同一引擎——带 streaming、extended thinking、subagent、hooks、权限模式、原生 MCP。

GaiaAgent/AURC 是**另一层**:它不决定"下一步调哪个工具"——它管 agent 身份、生命周期、跨协议桥接(MCP/A2A/ACP)、安全/委派、编排。这些在 loop 内部都不存在。

两者**互补,不竞争**:

| | 职责 | 层级 |
|:---|:---|:---|
| **Claude Code CLI agentic loop** | 单个 agent 内部"下一步调哪个工具"的执行循环 | 内层 / 执行引擎 |
| **GaiaAgent / AURC** | 围绕该 loop 的身份、生命周期、跨协议桥、安全、编排 | 外层 / 运行时与协议层 |

结合方式:**AURC 运行时包住 CLI loop**。在 `RUNNING` 状态内,`claude -p` 驱动推理;CLI 的工具调用(原生或经 `--mcp-config`)流经 AURC 的 MCPBridge → MessageRouter → skills,委派链、CapABAC 授权、审计日志自动生效,loop 无需感知协议存在。

---

## 架构:外层 AURC,内层 CLI Loop

```
AURC Runtime Harness(9态生命周期、CapABAC、桥、审计)
│  RUNNING 状态把控制权交给 ──┐
└────────────────────────────►│
                              ▼
        claude -p "<prompt>" --output-format stream-json   ← 参考 loop
        (--model --max-turns --system-prompt --permission-mode
         --allowed-tools --mcp-config …)
                   │  NDJSON 事件流
                   ▼
        claude_cli.py 适配器解析事件 → ClaudeResponse
                   │
        tool_use 事件 ──► _execute_tool()   ← 唯一缝点(Step 3 覆写)
                   │
        ┌──────────┴──────────┐          ┌──────────────────────┐
        ▼                     ▼          │  AURC 消息总线        │
   CLI 原生工具           AURCMessage ◄───┤  MessageRouter.route │
   (Read/Bash/…,或        method=invoke   │  mcp:/a2a:/acp: 前缀  │
   经 --mcp-config)       target=mcp:...  │  → bridge forwarder  │
                                          └──────────────────────┘
                   │
        correlation_id + bridge_chain + delegation_chain 全程贯穿
```

---

## 概念映射 — Claude Code CLI → AURC

这是*目标*设计契约。**状态**列标注当前是否已接通——仅 skill→tool 与 `--mcp-config` 两行已实现,其余为 Step 3+ 工作。

| Claude Code CLI | AURC 对应 | 结合方式 | 状态 |
|:---|:---|:---|:---:|
| `--resume <session>` / 会话 ID | 4-scope `ContextStore` | CLI 会话 id 存入 AURC session scope;跨协议 agent 恢复同一 loop。 | 🔜 |
| subagent(`.claude/agents`) | AURC delegation hop | 派生 CLI subagent = 一次委派跳转;CapABAC 强制 scope 只收窄。 | 🔜 |
| `--permission-mode` | CapABAC `AuthorizationEngine.authorize` | 权限模式映射到 CapABAC 策略;拒绝工具 → `is_error` 回灌。 | 🔜 |
| hooks(`settings.json` Pre/PostToolUse) | state-change listeners + HITL gate | CLI hook 桥接到 AURC 的 HITL、审计、指标。 | 🔜 |
| `--output-format json` + 输出 schema | `SkillDeclaration.output_schema` | CLI 结构化输出对齐 AURC skill 返回 schema。 | 🔜 |
| `--allowed-tools` / 原生工具 | `ClaudeTool` ← `@skill` 方法 | `ClaudeTool.from_aurc_skill` 把 AURC skill 暴露为工具定义;`--allowed-tools` 端到端接通。 | ✅ |
| `--mcp-config` | L4 MCP Bridge + `gaiaagent.mcp.server` | CLI 指向 AURC MCP server;`tools/call` 经 `MCPBridge` → `MessageRouter` 进入总线。 | ✅ |

---

## 已验证的代码缝点

以下均经读码确认(非假设),是集成的挂接点:

- **被替换的 loop**:`ClaudeLLM.agentic_loop` — `src/gaiaagent/integrations/claude.py:258-352`。
- **唯一"按名执行工具"点**:`tool_map.get(block.name)` → `await tool.handler(**block.input)` — `claude.py:286-316`。它收口为 `_execute_tool()`。
- **skill→tool 转换**:`ClaudeTool.from_aurc_skill` 读 `SkillDeclaration.skill_id/.description/.name/.input_schema.properties/.input_schema.required` — `claude.py:99-114`;`SkillDeclaration` 定义于 `src/gaiaagent/core/identity.py:122-132`。
- **agent 工具暴露**:`ClaudeAgent.get_claude_tools()` — `claude.py:475-487`(遍历 `aurc_descriptor.capabilities.provides`)。
- **按协议前缀的总线路由**:`MessageRouter.route` — `src/gaiaagent/bus/router.py:128`;`mcp:`/`a2a:`/`acp:` target 触发 `bridge_forwarder`(`router.py:166-175`);直接 target 命中已注册 handler(`router.py:152-163`)。
- **单次调用鉴权**:`AuthorizationEngine.authorize(agent_id, resource_type, action, attributes) -> AuthzResult` — `src/gaiaagent/security/authz.py:194`。
- **委派跳转记录**:`DelegationBuilder.add_hop(from_agent, to_agent, scopes)` 后把 `build()` 附到 `message.security.delegation_chain` — `src/gaiaagent/security/delegation.py:189-194`。
- **context store API**:`ContextStore.save/load/delete/list_keys/clear_scope`,带 `ContextScope` 枚举 — `src/gaiaagent/harness/context.py:58-249`。
- **生命周期**:`RuntimeHarness.start` 把 `READY → RUNNING` 后返回 — `src/gaiaagent/harness/lifecycle.py:274-299`。harness **不**分发 skill 调用;skill 执行由 workflow 层或 loop 驱动。

---

## 三步路线图

Step 1、2 已发布。Step 3(剩余治理接通)重新定调:原"覆写 `_execute_tool` 走总线"方案**已弃**——该缝点在 CLI 路径上是死的(子进程自己跑工具)。CLI 路径的总线路由在 MCP 层做(Step 1),不靠覆写 `_execute_tool`。Step 3 现为围绕 loop 的*剩余* AURC 治理接通。

### Step 1 — AURC MCP Server(总线路由)  ✅

把 AURC `@skill` agent 暴露为 MCP 工具,`claude` CLI 经 `--mcp-config` 调用。实现为 `gaiaagent.mcp.server.AURCMCPStdioServer`(stdio JSON-RPC):`tools/list` 枚举 `aurc_descriptor.capabilities.provides`;`tools/call` 经 `MCPBridge.translate_to_aurc`(铸 `correlation_id` + `bridge_chain`)→ `MessageRouter.route` → skill。运行:`python -m gaiaagent.mcp --agent myproj:Agent`。子进程边界变得无关紧要——总线穿越在协议层,正是 AURC L4 桥本就干的事。

反方向(CLI 原生工具作为 AURC skill 给非 Claude agent)仍 🔜。

**验收(已达成):** CLI 以 `--mcp-config` 指向 AURC MCP server 时调用一个 AURC `@skill` 并拿到结果;`correlation_id` + `bridge_chain` 由 bridge 设置、`BridgeTraceRecorder` 记录。由 `tests/test_mcp_server.py` 覆盖。

### Step 2 — `claude` CLI 作 loop 引擎  ✅

`ClaudeLLM.agentic_loop` 在 CLI 在 PATH 且无调用方传入的 Python tool handler 需进程内执行时委托给 `claude -p … --output-format stream-json`;否则降级到内置循环。公开 API 不变。子进程安全:`communicate()`(并发排空、无死锁)、可选 `timeout`、超时/取消 `try/finally` kill(无泄漏 `ANTHROPIC_API_KEY` 的孤儿 `claude`)。防御性解析:空流 → `stop_reason="error"`(非静默成功)、`isinstance` 守卫、正确的 `stop_reason` 优先级。接通 `stop_reason → RecoveryAction` 映射 + 可选 `usage → BridgeTraceRecorder` 追踪。由 `tests/test_claude_integration.py::TestClaudeCLIBackend` 覆盖。

### Step 3 — 剩余 AURC 治理接通  🔜

loop 已委托、工具调用已在协议层路由(Step 1、2)。尚未接通的是围绕 loop 的 AURC 运行时:

- **生命周期**:`RuntimeHarness` 尚不驱动 `agentic_loop`——`READY → RUNNING` 转换与 `report_error` 恢复未在 CLI 路径触发。把已映射的 `stop_reason → RecoveryAction` 接入 `RuntimeHarness.report_error`。
- **CapABAC 鉴权**:`--permission-mode` 透传但每次工具调用未调 `AuthorizationEngine.authorize`。在 MCP server 内对 `tools/call` 加鉴权门。
- **session/resume**:未发 `--resume`,CLI 会话 id 未存入 `ContextStore` session scope。
- **CLI 原生工具作为 AURC skill**(Step 1 的反方向)。

**注:** 原"覆写 `_execute_tool` 走总线"方案**已弃**——该缝点仅存在于降级路径;CLI 路径的总线路由是 MCP server 的职责(Step 1,已完成)。

### 端到端接通

```bash
# 1. 把一个 AURC agent 作为 MCP server 跑(CLI 调它):
python -m gaiaagent.mcp --agent myproj:ResearchAgent &

# 2. CLI 指向它并跑 loop:
claude -p "Research AI agent protocols" \
  --output-format stream-json \
  --mcp-config '{"mcpServers":{"aurc":{"command":"python","args":["-m","gaiaagent.mcp","--agent","myproj:ResearchAgent"]}}}'
```

或从 Python(委托 + MCP 接通一次调用):

```python
from gaiaagent.integrations.claude import ClaudeLLM
llm = ClaudeLLM(
    mcp_config='{"mcpServers":{"aurc":{"command":"python","args":["-m","gaiaagent.mcp","--agent","myproj:ResearchAgent"]}}}',
    trace_recorder=recorder, agent_id="aurc:myproj/researcher:v1.0",
)
resp = await llm.agentic_loop(prompt="Research AI agent protocols", correlation_id="req-1")
```

---

## 不做(当前范围外)

| 非目标 | 原因 |
|:---|:---|
| ❌ 改写 `ask()` / `converse()` 委托 | 限制影响面;它们日后可同样采纳。 |
| ❌ 对外 streaming API(`agentic_loop_stream`) | 代码库当前无 async-generator 先例;CLI 流在内部聚合成单个 `ClaudeResponse`。streaming 暴露是单独的 opt-in 变更。 |
| ❌ 修改 `MessageRouter` / 桥 / harness / security 代码 | Step 3 只经 `_execute_tool` 缝*用*它们,不改它们。 |
| ❌ 锁定 Claude | **已解决**:`backend` 参数(`claude` / `codex` / `auto`)使可插拔缝变为真实。`codex` CLI 后端为第二个参考;额外后端同样镜像该适配器形状。 |
| ❌ 新增 Python SDK 依赖 | `claude` CLI 即引擎;不引入 `claude-agent-sdk` pip 依赖。 |

---

## 风险与缓解

| 风险 | 缓解 |
|:---|:---|
| **CLI `stream-json` schema 漂移**(事件/字段名跨版本变化) | 适配器防御性解析(全用 `.get()`,容忍缺字段);实现时抓一次 trace 钉 schema;降级 loop 覆盖 CLI 缺失。 |
| **调用方传入的 Python tool handler 无法被子进程 CLI 调用** | Step 2 在传入带 handler 的 `tools` 时降级到手写 loop;把 handler 暴露给 CLI 正是 Step 1 的 MCP 桥。 |
| **测试触网/需登录** | 测试全 monkeypatch 子进程;真实 CLI 冒烟是单独手动脚本,不进 CI。 |
| **向后兼容破坏** | 签名与私有属性(`_model`、`_api_key`、`_max_tokens`、`_system_prompt`、`_conversation_history`)保持;既有 `tests/test_claude_integration.py` 是回归网;`main.py` 不用 Claude。 |

---

## 如何参与

- **认领一步** — 在 [Discussions](https://github.com/gaiaagent/gaiaagent/discussions) 评论认领 Step 1 或 Step 3。
- **提议一项映射** — 若某 CLI 概念尚无 AURC 对应,开 issue 打 `loop-integration` 标签。
- **移植到其他 loop 后端** — **已示范**:`codex_cli.py` 镜像 `claude_cli.py`,通过 `backend` 参数接入。额外后端同模式。

---

*本指导文档持续更新。欢迎 PR 修改——打 `loop-roadmap` 标签,以便提交前讨论范围。*
