# GaiaAgent 待办项

> 基于 2026-06 代码审查，按严重度排序的可执行改进清单。每条标注影响层与目标版本。

## P0 安全叙事与实现落差

- [x] **授权接入路由热路径**（影响：安全/正确性，目标：当前迭代）
  - 现状：`MessageRouter.route()` 与 `AURCServer.http_handler` 全程无授权；`BridgeAuthzGuard` 仅守 inbound 桥接且为 opt-in。
  - 动作：新增 `security/message_authz.py` 共享 `derive_authz_request` + `RouteAuthzGuard`；router 加 `set_authorizer` 在 TTL 后派发前调用；server 把 deny 映射为 `forbidden` 错误信封；补 `test_router_authz.py` / `test_server_authz.py`。
  - 约束：无 authorizer 时行为零变化（480 测试须全绿）。
  - 状态（2026-06-26）：已完成。MessageRouter.set_authorizer + RouteAuthzGuard 接入热路径；AURCServer 接 authz_engine/authorizer 并把 AuthzDeniedError 映射为 forbidden 信封；BridgeAuthzGuard 复用共享派生；新增 10 测试，全套 490 passed / ruff / mypy strict 全绿。
- [x] **授权决策可审计/可观测**（影响：治理/合规，目标：当前迭代）
  - 状态（2026-06-28 复核）：审计侧已完成。`RouteAuthzGuard.authorize_message` 在 deny/grant 均经 `_record_audit` 写 `AuditLog`（`AUTHZ_DENIED` WARNING / `AUTHZ_GRANTED` INFO），`AURCServer` 经 `attach_audit` 共享同一日志；`test_authz_audit.py` 24 项测试覆盖。可观测性经 `aurc_audit_events_total{action=...}` 已可读出 deny 维度。
  - 残留（可选）：未单独新增 `aurc_authz_decisions_total{decision,...}` 计数器；当前 `aurc_audit_events_total{action=AUTHZ_DENIED}` 已覆盖 deny 维度，是否新增独立计数器视需要而定。

## P1 工程质量与可信度

- [x] **全量乱码修复**（影响：可信度/可读性，目标：当前迭代）
  - 状态（2026-06-28 复核）：已完成。按字节扫描 `src/**/*.py` 与全部 `*.md`：0 个非 UTF-8 文件、0 个 mojibake 嫌疑文件；`.gitattributes` 与 pre-commit 编码守卫已就位（见 `CLAUDE.md` 编码守卫段）。此前控制台所见乱码为 PowerShell cp936 渲染 UTF-8 的显示问题，非文件损坏。
- [x] **ingress 加固**（影响：安全/DoS，目标：当前迭代）
  - 现状：HTTP/WS 读 body 无大小上限、无连接数限制、无入口限流。
  - 动作：max body / max frame、连接数上限、入口令牌桶、超时强制；错误出口走结构化映射层不泄漏 `str(exc)`。
  - 状态（2026-06-28）：已完成。HTTPTransportServer 引入 IngressLimits（默认 1 MiB body、1024 并发、30s 超时、100 req/s 全局令牌桶 burst 200），经 set_ingress_limits() 可覆盖；uvicorn limit_concurrency、ASGI 顶部门控 429 rate_limited、_read_bounded() 413 payload_too_large、asyncio.wait_for(request_timeout) 强制超时。WebSocketTransportServer/Client 加 max_frame_bytes（默认 10 MB）传入 websockets max_size，心跳保留。错误出口统一走 _send_error/_ws_error_envelope 结构化信封 {error:{code,message}}，不泄 str(exc)；server.http_handler 的 bad_message/route_error 同步收口，forbidden 保留 exc.reason。transport/__init__.py 导出 IngressLimits/TokenBucketLimiter；transport/CLAUDE.md 契约更新。新增 tests/test_ingress_limits.py 6 项（413/429/超时/不泄密/extra route/正常通过），并改 test_transport_routes.py 断言为结构化信封。全套 522 passed / 2 skipped；ruff 0 错；mypy strict 0 错（57 源文件）。

## P2 健壮性与并发

- [x] **`asyncio.get_event_loop()` 弃用与未跟踪 task**（影响：正确性/告警，目标：当前迭代）
  - 状态（2026-06-28）：已完成。`RuntimeHarness._fire_listeners` 改用 `get_running_loop()`；新增 `_pending_listener_tasks` 集合跟踪 fire-and-forget task 并经 done-callback `_discard_listener_task` 释放引用、上报异常；无运行循环时关闭协程避免 'coroutine was never awaited' 警告。新增 `tests/test_lifecycle_listeners.py` 6 项测试；全套 516 passed / ruff / mypy strict 全绿。
- [ ] **广播并发上限 + 通配符索引**（影响：性能/可扩展性，目标：v0.2）
  - 现状：组播 `gather` 无界扇出；通配符未命中时 O(n) 全量扫描。
  - 动作：`asyncio.Semaphore` 分批；通配符改前缀索引。

## P3 持久化与多语言

- [ ] **可插拔存储抽象**（影响：持久化/合规，目标：v0.2）
  - 现状（2026-06-28 复核）：部分完成。`AuditSink` Protocol + `FileAuditSink`（Phase 4.2）、`TraceSink` Protocol + `FileTraceSink` 已落地并测试；死信队列、`SessionStore`、策略与限流窗仍全内存，重启即丢。
  - 动作：补 `DeadLetterStore`/`SessionStore`/`PolicyStore` 接口，先内存后 Redis/对象存储。
- [x] **冻结线缆格式 JSON Schema**（影响：生态/polyglot，目标：v0.4）
  - 状态（2026-06-28）：已完成。`spec/aurc-message.schema.json` 为从 `AURCMessage` 模型生成的冻结 JSON Schema（2020-12，带 `$id`/`$schema`）；`gaiaagent.conformance.schema.generate_message_schema()` 为唯一真源，`published_schema_matches_model()` 做漂移检测，`scripts/generate_schema.py` / `aurc conformance --schema` 发布或校验；`jsonschema` 列为 `conformance` extra。
- [x] **AURC 一致性测试集**（影响：标准化/生态，目标：v0.1→v1.0 门槛）
  - 状态（2026-06-28）：已完成。`gaiaagent.conformance` 包定义「AURC-compatible」：结构层（按冻结 schema 校验原始线缆 JSON）+ 语义层（JSON Schema 无法表达的不变式：correlation 传播、委托链 scope 只收窄、TTL 正、error/result 互斥、流式块索引、响应 source/target 对称）。`run_conformance() -> ConformanceReport` 为第三方可调入口；`aurc conformance <file>` CLI 子命令。全套 553 passed / 2 skipped。
