# GaiaAgent 推广就绪差距清单

> 评估时间：2026-06-27 · 版本 0.1.1 · 状态 Alpha
> 本文件区分「已在代码/文档中补掉的坑」与「只能靠外部动作才能补的坑」。

---

## A. 已在本轮补掉（代码/文档级，实证可验）

| # | 坑 | 修复 | 验证 |
|---|---|---|---|
| 1 | README 顶部挂 PyPI badge，但包未发布到 PyPI（死链/误导） | 改为 PyPI: not yet published badge；底部 footer 去掉 PyPI/Discord/gaiaagent.dev 死链，只留 GitHub/Discussions | README 顶部 + 底部 |
| 2 | Discord badge 指向 discord.gg/gaiaagent，域名无法验证 | 改为 Discord: planned badge | README 顶部 |
| 3 | 版本号不一致：README 写 v0.1.0，pyproject 是 0.1.1 | README 统一为 v0.1.1 | README 状态行 + roadmap |
| 4 | 推广措辞过度：Production-ready single-tenant（v0.2 表） | 改为 Production hardening (single-tenant target)，与 Alpha 自洽 | README roadmap 表 |
| 5 | README 无诚实现状与限制声明，买家易误判成熟度 | 新增顶部 One-line status：523 passing、未上 PyPI、零采用、demo 用 stub LLM | README 中文链接下方 |
| 6 | 核心卖点真跨进程 HTTP 轮次无回归保护 | 新增 tests/test_e2e_cross_process.py，子进程跑 demo 断言真路由 + 真网络轮次 + correlation 端到端 | pytest 523 passed |
| 7 | 真实 MCP server + 真实 A2A 跨进程联调缺证据（见 C4） | 新增 examples/e2e_mcp_a2a_interop.py：spec-compliant A2A tasks/send 客户端 -> AURC /a2a -> 真实 MCP server（官方 mcp SDK FastMCP + ClientSession/stdio），算术在真实 MCP server 内完成、correlation 端到端；配套 examples/_real_mcp_server.py 与回归测试 | pytest 523 passed |
| 8 | 规范状态中英自相矛盾：PROTOCOL.zh.md 标「草案」、PROTOCOL.md 标「Stable (v0.1 frozen)」；README.zh.md 版本仍 v0.1.0（英文已 v0.1.1）—— item 3 只改了英文，中文漏改 | PROTOCOL 中英状态统一为分层表述「稳定（v0.1 冻结；向后兼容承诺于 v1.0）」；README.zh.md 状态行 + roadmap 段同步为 v0.1.1 | grep：两版 PROTOCOL 均无「草案」、状态行语义一致；两版 README 均为 v0.1.1 |
| 9 | ACP 侧无等价真网络联调（见 C4） | 新增 examples/e2e_acp_interop.py：spec-compliant ACP invoke 客户端经 HTTP 打到 AURC /acp，AURC 翻译为 skill 调用，skill 用官方 mcp SDK（FastMCP server + ClientSession/stdio）调用真实 MCP server，算术在真实 MCP server 内完成、correlation 端到端；配套回归测试 tests/test_e2e_acp_interop.py | pytest 523 passed |

全量回归：pytest 523 passed / 2 skipped；ruff check 0 错；mypy --strict 0 错（57 源文件）。

---

## B. 只能靠外部动作补的坑（不在代码里，需运营/发布）

1. 未发布到 PyPI。现状只能 pip install -e . 本地装。进 B 端采购/CI 引用需 uv build 后 twine upload。产物已干净。
2. 零真实采用方。ADOPTERS.md 仅占位行。协议价值取决于网络效应，需一个真实外部案例。最高杠杆动作（本地已具备）：examples/e2e_mcp_a2a_interop.py 已打通真实 A2A 客户端 -> AURC -> 真实 MCP server 的跨进程联调，可作为录屏/公开演示的素材；差的是公开发布 + 真实外部采用方背书。
3. 域名 gaiaagent.dev / Discord 未落地。README 已降级为 planned 避免误导；推销前需注册域名建 Discord，或彻底移除。
4. 单人 + 4 天开发史。git 历史显示 hariji814 一人 + Codex 辅助，4 天密集提交。评审方会质疑多端联调深度。只能靠时间和第二个贡献者/采用方稀释。
5. 第二个独立实现缺失。ROADMAP 未 second independent implementation 列为 v1.0 门槛——这是协议与个人项目的分界线。只能靠社区，无法自证。

---

## C. 仍存在的工程债（影响可信度，可补但本轮未做）

1. “乱码”已澄清：本地 PowerShell 用 GBK 代码页渲染 UTF-8 文件会显示乱码（如 鈕?/瑠?/路），但用 Python 以 UTF-8 读取 README.md/TODO.md 内容完好（零西里尔字符、零损坏）。文件本身未损坏，无需重写。仅需提醒：在 GBK 终端查看时以 Python 读或设置 chcp 65001 避免误判。此条不再是可信度硬伤。
2. demo 用 stub LLM。demo.py 注释明示 No API key required - uses stub LLM responses。跨协议流是真的，AI 推理是假的。演示可接受但需口头说明，或补 --real-llm 开关走真 Anthropic API（代码已支持，缺示例）。
3. ingress 加固已完成（2026-06-28，TODO P1-2）。HTTPTransportServer 引入 IngressLimits（默认 1 MiB body、1024 并发、30s 超时、100 req/s 全局令牌桶 burst 200）：uvicorn limit_concurrency、ASGI 顶门 429 rate_limited、_read_bounded() 413 payload_too_large、asyncio.wait_for 超时强制；WebSocketTransportServer/Client 加 max_frame_bytes（默认 10 MB）传入 websockets max_size，心跳保留；错误出口统一走 _send_error/_ws_error_envelope 结构化信封不泄 str(exc)。tests/test_ingress_limits.py 6 项覆盖。
4. 桥接已补真实跨进程联调（MCP+A2A+ACP）。A2A 侧：新增 examples/e2e_mcp_a2a_interop.py，spec-compliant A2A tasks/send 客户端经 HTTP 打到 AURC /a2a，AURC 翻译为 skill 调用，skill 用官方 mcp SDK（FastMCP server + ClientSession/stdio）调用真实 MCP server，算术在真实 MCP server 内完成、correlation 端到端。ACP 侧：新增 examples/e2e_acp_interop.py，spec-compliant ACP invoke 客户端经 HTTP 打到 AURC /acp，同样翻译为 skill 调用真实 MCP server、correlation 端到端；配套 examples/_real_mcp_server.py 与回归测试。A2A 客户端因 a2a-sdk 在本环境无法安装而手写，但完全符合 tasks/send JSON-RPC 2.0 线协议。三条桥（MCP/A2A/ACP）现均有等价真网络联调证据。

---

## 推销姿势建议

诚实定位：Apache-2.0 的 agent 协议桥接参考实现，Alpha，欢迎试点共建。
能演示：跨协议消息流、9 态生命周期、CapABAC 委托链、一键 dashboard、真 HTTP 轮次。
不要说：生产级/企业级/统一标准——这三点项目自身都还没敢声明。

下一步最高价值不是加功能，而是 B2：把已跑通的真实跨协议联调（examples/e2e_mcp_a2a_interop.py：真实 A2A 客户端调通真实 MCP server）录屏并公开，再争取一个真实外部采用方。一次公开的真实联调录屏，比任何文档都管用。
