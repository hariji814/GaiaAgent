# GaiaAgent 推广落地执行计划

> 目标:把「AGPL + Alpha + 内存态」三道墙变成可执行清单,让项目在两周内变成**许可证友好、一键可跑、有杀手级 demo、不撒谎**的可推广状态。
>
> 评审依据:四维度并行评审(可行性 6/10、推广 6.5/10、可落地 3/10、优化 34 项)的交叉验证结论。

---

## 执行进度（截至 2026-06-26）

| 阶段 | 状态 | 实证 |
|---|---|---|
| **Phase 0** 信任地基 | ✅ 完成 | license Apache-2.0（LICENSE/pyproject/10 文档/decorators 默认）；spec 状态自洽；CI 去假绿、加 Windows 矩阵；spec/AURC_SPEC.md 已归档 |
| **Phase 1** 一键 demo | ✅ 完成 | `_cmd_serve` 接 `AURCServer.http_handler` 真路由；`gaiaagent demo` + `examples/e2e_cross_process.py` 跨进程真 HTTP（add→42、multiply→42，correlation_id 端到端） |
| **Phase 2** 堵空壳 | ✅ 完成 | `_invoke_skill` 真路由修复；lifecycle/orchestrator/router 空壳补齐（commit c2e0633）；行为测试覆盖 |
| **Phase 3** 推广物料 | ✅ 完成 | why-gaiaagent.md/SECURITY/GOVERNANCE/ADOPTERS/CODE_OF_CONDUCT/CHANGELOG/issue 模板齐备 |
| **Phase 4** 生产持久化 | ✅ 完成 (4.1-4.4) | 4.1 AgentRegistry/MessageBus Protocol + TTL 驱逐;4.2 AuditSink/TraceSink Protocol + FileAuditSink/FileTraceSink 实时持久化+轮转;4.3 HTTP 连接池+重试+超时、WebSocket 心跳、HTTPServer 优雅排空+超时强退+SIGTERM 钩子;4.4 BridgeAuthzGuard fail-closed 桥接授权 + Ed25519 委托签名 + DelegationValidator 验签 |

**验证门槛**：469 passed / 2 skipped；ruff 0 错；mypy strict 0 错（48 源文件）；`uv build` 0.1.1 sdist+wheel 双产物干净。

**发版阻塞项（唯一外部动作）**：gaiaagent 未上 PyPI（404）。已 bump 0.1.0→0.1.1、本地构建通过。需：① GitHub→Settings→Secrets 配置 PyPI trusted publisher；② 合并 `loop-cli-integration`→`main`；③ 推 `v0.1.1` tag 触发 `release.yml`（test job 已 gate publish）。

## 三根支柱

| 支柱 | 一句话 | 衡量标准 |
|---|---|---|
| **A. 去掉采纳闸门** | 许可证 + spec 状态 + CI 不再撒谎 | 企业法务不秒拒、CI 真绿、文档自洽 |
| **B. 一键可跑 + 杀手 demo** | 60 秒看到跨协议消息流过 dashboard | `make demo` 一条命令打开浏览器看到活流程 |
| **C. 不再是空壳** | 路线图标 done 的项名实相符 | pause 真挂起、listener 真触发、serve 真路由 |

生产持久化(内存态 -> SQLite/Redis)列为 Phase 4,不阻塞推广与 demo,但在计划内排期。

---

## Phase 0 - 信任地基(1 天,纯机械改动)

> 投入极小、信任回报最大。先做这批。

### 0.1 许可证改 Apache-2.0
- **为什么**:AGPL 强 copyleft + 网络使用条款是企业法务高频否决项,直接卡死最高价值受众(企业平台团队)。Apache-2.0 是 Kubernetes/gRPC/etcd/Envoy 等基础设施与协议项目的行业惯例,带专利授权、无 copyleft 传染,法务通过率高。
- **改动**:
  - 替换 LICENSE 全文为 Apache-2.0
  - pyproject.toml:license = "AGPL-3.0-or-later" -> "Apache-2.0";classifier 改 License :: OSI Approved :: Apache Software License
  - 各源文件头如有 AGPL 声明,统一改 Apache SPDX 头
  - spec 许可(PROTOCOL.md 底部)从 CC BY-SA 改 Apache-2.0(宽松规范许可,方便厂商引用)
- **验收**:pyproject license 字段为 Apache-2.0;pip install 元数据正确;无残留 AGPL 字样

### 0.2 修 spec 状态自相矛盾
- README/ROADMAP 称「spec frozen」,PROTOCOL.md:8 标 Status: Draft -> 统一为分层表述:**「v0.1 spec 冻结(语义不再大改)、v1.0 才承诺向后兼容冻结」**,PROTOCOL.md 头部 status 改 Stable (v0.1 frozen)
- README.md:558 测试数 299 -> 实际 352
- 将 108KB 废弃 spec/AURC_SPEC.md 移入 spec/archive/,避免误导
- **验收**:全仓库 grep frozen/Draft 无矛盾;测试数与 pytest --co -q 一致

### 0.3 CI 不再假绿
- ruff check --fix 清 44 个自动修复项
- 修 66 个 mypy 错误到 0(含 lifecycle.py:436 Awaitable 未导入真 bug),然后 ci.yml 去掉 continue-on-error: true
- release.yml publish-pypi 加 needs: test(堵住打 tag 发坏包)
- 加 windows-latest 到 CI 矩阵(项目明确支持 Windows)
- **验收**:CI mypy 阻断合并;ruff 0 错;release 依赖 test 通过

---

## Phase 1 - 一键可跑 + 杀手 demo(3 天,核心)

> 这是「看到即信」的时刻。利用已有资产(dashboard.py 真实可用、observability_demo.py 无依赖可跑、5 种编排、三桥双向翻译),缺口只有 CLI serve 是 echo 占位。

### 1.1 修 CLI serve 接真实处理链
- cli.py _cmd_serve 的 echo handler 换成:接收 AURC 消息 -> MessageRouter.route() -> harness 调度 agent -> 返回结果
- --dashboard flag 真正挂载 DashboardAPI 到 ASGI app(它已有 /metrics、JSON API、暗色 UI)
- HTTP 层加最小 API Key 中间件(可选开关,默认本地不限)
- **验收**:aurc serve --dashboard 起来后,POST /aurc 能路由到已注册 agent 并返回真实结果,浏览器看到 dashboard

### 1.2 杀手 demo:跨协议消息流
- 新增 aurc demo 子命令(或 make demo),一键:
  1. 起 RuntimeHarness,预注册 3 个 agent:Researcher(MCP 风格 skill)、Analyst(A2A 风格)、Writer(ACP 风格)
  2. 发一个任务「research -> analyze -> write」,走 Chain 编排
  3. 每一跳跨协议桥接(MCP->AURC->A2A->AURC->ACP),单一 correlation_id 贯穿
  4. 自动打开浏览器到 dashboard,实时看到 agent 卡片依次亮起、消息 trace、audit 日志
  5. 无需 API key(纯进程内路由 + stub 响应;LLM 后端用内置 stub,不调外部)
- **验收**:陌生机器 pip install gaiaagent[all] && gaiaagent demo,60 秒内浏览器出现活的跨协议流程;README 首屏放该 demo 的 GIF

### 1.3 Dockerfile 装全 extras
- Dockerfile pip install 加 [websocket,anthropic],与 deployment.md 文档对齐(python 版本、curl/urllib 一致)
- **验收**:docker build 后容器内 gaiaagent demo 可跑

---

## Phase 2 - 堵空壳,让 demo 不撒谎(2 天)

> 路线图标 done 但名实不符的项,在 demo 上镜前必须补真。

### 2.1 生命周期三处空壳
- lifecycle.py:526 _notify_listeners 在 transition_to 末尾接通(dashboard 才能实时反映状态变化)
- pause/resume:在执行点补 await self._pause_event.wait()(目前只有 set/clear 无 wait,pause 不真挂起)
- restart() 改走 transition_to 或给终态->READY 一条显式合法通道(目前直接赋值绕过校验)
- 补行为级测试:断言 listener 被触发、pause 后 loop 真阻塞
- **验收**:demo 运行时 dashboard agent 卡片状态实时跳变;新测试覆盖三处行为

### 2.2 编排与路由正确性
- orchestrator.py OrchestratorWorkers 改 asyncio.gather 真并行(目前注释写 parallel 实为串行)
- router.py TTL 每跳递减(目前从不递减,可无限转发);广播改 gather 并行;死信队列 list.pop(0) -> deque
- **验收**:demo 多 worker 场景真并发;TTL 耗尽后停止转发

### 2.3 恢复策略文案对齐
- RecoveryAction 实际 3 个(RETRY/ESCALATE/FAIL),路线图称「5 strategies」-> 改文案为「3 strategies」或补 RESTART/FAILOVER
- ESCALATE 接一个可插拔 HITL 回调接口(不强制实现真实审批,但留 hook)
- **验收**:路线图数字与枚举一致

---

## Phase 3 - 推广物料(1-2 天,与 Phase 1-2 并行)

### 3.1 决策页 + 首屏证据
- 新增 docs/why-gaiaagent.md:一页面向决策者的「为什么选 GaiaAgent 而非直接用 MCP/A2A」(build-vs-buy-vs-bridge),集中现在散落的论证
- README 首屏放 demo GIF + 一行安装命令
- 修 quickstart.md 三处断链(multi-agent.md / mcp-integration.md / http-deployment.md -> 补文件或改链接)

### 3.2 社区基础设施
- 新增 SECURITY.md、GOVERNANCE.md、ADOPTERS.md、CHANGELOG.md、.github/ISSUE_TEMPLATE/(bug/feature)、CODE_OF_CONDUCT.md
- CONTRIBUTING.md 引用的 CHANGELOG/issue 模板落地为真实文件
- **验收**:CONTRIBUTING 内所有链接无 404

---

## Phase 4 - 生产持久化路径(v0.2,不阻塞推广)

> 内存态 -> 可持久化。这是从「demo 可跑」到「受限生产试点」的桥。计划内排期,但放推广之后。

### 4.1 抽象先行
- 抽 AgentRegistry Protocol、MessageBus Protocol(目前只有内存实现,无统一契约)
- registry/local.py 心跳补 TTL/驱逐(stale agent 不应永久可发现)

### 4.2 持久化三件套
- API key / CapABAC 策略落 SQLite(单机)或 Redis(多副本)
- audit.py 实时写文件 + 轮转(或接 OTel logs)
- trace recorder 持久化或直连 OTel(目前手动 flush)

### 4.3 传输可靠性
- httpx client 长生命连接池 + 重试 + 超时外部化
- stop() 加在途 drain + SIGTERM 钩子(优雅关闭)
- WebSocket 补 ping/pong 心跳

### 4.4 安全收口
- A2A/ACP 桥接接入 authz 强制(补 spec 9.3「Bridge 层强制权限映射」核心承诺,目前仅 MCP 出站兑现)
- 委托链实现 Ed25519 签名(require_signatures),chain hash 改 HMAC 防篡改
- authz evaluate 加 fail-closed 异常包裹(类型不匹配时拒绝而非抛异常)

**Phase 4 完成门槛**:可在「内网、单租户、有反代、有 API key」的受限环境试点。

---

## 执行顺序与依赖

```
Phase 0 (信任地基) --无依赖,先做
   |
   |---> Phase 1 (一键 demo) -- 依赖 0.1/0.2 不撒谎
   |        |
   |        |---> Phase 2 (堵空壳) -- 让 demo 上镜前名实相符
   |
   |---> Phase 3 (推广物料) -- 与 1/2 并行
   |
   |---> Phase 4 (生产持久化) -- 推广之后,v0.2 排期
```

**两周里程碑**:Phase 0-3 完成 = 许可证友好 + 一键 demo + 不撒谎 + 推广物料齐备 -> 具备「发出去让人试用」的条件。Phase 4 随后推进到受限生产试点。

---

## 建议编码分工(并行)

编码阶段可拆成不冲突的写域并行推进:
- **流 A**:cli.py serve 真实化 + demo 子命令 + Dockerfile(Phase 1)
- **流 B**:lifecycle 三处空壳 + orchestrator/router 正确性 + 测试(Phase 2)
- **流 C**:许可证 + spec 状态 + CI/ruff/mypy + 社区文件(Phase 0 + 3)

三条流写域不重叠,可同时开工。
