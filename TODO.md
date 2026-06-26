# GaiaAgent 待办项

> 基于 2026-06 代码审查，按严重度排序的可执行改进清单。每条标注影响层与目标版本。

## P0 安全叙事与实现落差

- [x] **授权接入路由热路径**（影响：安全/正确性，目标：当前迭代）
  - 现状：`MessageRouter.route()` 与 `AURCServer.http_handler` 全程无授权；`BridgeAuthzGuard` 仅守 inbound 桥接且为 opt-in。
  - 动作：新增 `security/message_authz.py` 共享 `derive_authz_request` + `RouteAuthzGuard`；router 加 `set_authorizer` 在 TTL 后派发前调用；server 把 deny 映射为 `forbidden` 错误信封；补 `test_router_authz.py` / `test_server_authz.py`。
  - 约束：无 authorizer 时行为零变化（480 测试须全绿）。
  - 状态（2026-06-26）：已完成。MessageRouter.set_authorizer + RouteAuthzGuard 接入热路径；AURCServer 接 authz_engine/authorizer 并把 AuthzDeniedError 映射为 forbidden 信封；BridgeAuthzGuard 复用共享派生；新增 10 测试，全套 490 passed / ruff / mypy strict 全绿。
- [ ] **授权决策可审计/可观测**（影响：治理/合规，目标：当前迭代）
  - 现状：deny 只 `logger.warning`，无审计 sink 写入，无 `authz_denied_total` 指标。
  - 动作：`RouteAuthzGuard` 在 deny 时写 `AuditLog`；`PrometheusMetricsExporter` 加 `aurc_authz_decisions_total{decision,...}`。

## P1 工程质量与可信度

- [ ] **全量乱码修复**（影响：可信度/可读性，目标：当前迭代）
  - 现状：56/56 源文件中文注释损坏（UTF-8 被 GBK 双重编码烤入文件），含 `pyproject.toml` description 与所有 README。
  - 动作：跑一次 UTF-8 归一化重写；加 `.gitattributes` 与 CI 编码守卫防复发。
- [ ] **ingress 加固**（影响：安全/DoS，目标：v0.2）
  - 现状：HTTP/WS 读 body 无大小上限、无连接数限制、无入口限流。
  - 动作：max body / max frame、连接数上限、入口令牌桶、超时强制；错误出口走结构化映射层不泄漏 `str(exc)`。

## P2 健壮性与并发

- [ ] **`asyncio.get_event_loop()` 弃用与未跟踪 task**（影响：正确性/告警，目标：当前迭代）
  - 现状：`lifecycle.py _fire_listeners` 用已弃用 API 且 `create_task` 结果未持引用，可能被 GC。
  - 动作：改 `get_running_loop()` 并把 task 收集到集合。
- [ ] **广播并发上限 + 通配符索引**（影响：性能/可扩展性，目标：v0.2）
  - 现状：组播 `gather` 无界扇出；通配符未命中时 O(n) 全量扫描。
  - 动作：`asyncio.Semaphore` 分批；通配符改前缀索引。

## P3 持久化与多语言

- [ ] **可插拔存储抽象**（影响：持久化/合规，目标：v0.2）
  - 现状：死信队列、审计、策略、限流窗全内存，重启即丢。
  - 动作：`DeadLetterStore`/`AuditSink`/`SessionStore` 接口，先内存后 Redis/对象存储。
- [ ] **冻结线缆格式 JSON Schema**（影响：生态/polyglot，目标：v0.4）
  - 动作：发布 `AURCMessage` JSON Schema 作为 TS/Go/Rust SDK 与桥接一致性测试的共同契约。
