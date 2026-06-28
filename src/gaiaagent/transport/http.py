"""AURC HTTP Transport — HTTP/2 based message transport.
AURC HTTP 传输 — 基于 HTTP/2 的消息传输

Provides an HTTP server and client for AURC message exchange.
Uses JSON over HTTP POST for request/response patterns.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

# Type for message handlers / 消息处理函数类型
HTTPMessageHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class HTTPTransportError(Exception):
    """HTTP transport error. HTTP 传输错误"""
    pass


class IngressLimits:
    """Bounded ingress policy for the HTTP server. HTTP 入口限制策略

    Caps the resources a single inbound request may consume so a hostile or
    buggy peer cannot exhaust the node by sending oversized bodies, opening
    many connections, or flooding requests. Defaults are conservative; tune
    per deployment.
    """

    def __init__(
        self,
        *,
        max_body_bytes: int = 1 * 1024 * 1024,
        max_connections: int | None = 1024,
        request_timeout: float = 30.0,
        rate_limit: float | None = 100.0,
        rate_burst: float = 200.0,
    ) -> None:
        # 1 MiB default: an AURC message carries params, not payloads.
        self.max_body_bytes = max_body_bytes
        # Passed to uvicorn as limit_concurrency (simultaneous connections).
        self.max_connections = max_connections
        # Whole-request wall clock, enforced via asyncio.wait_for on the handler.
        self.request_timeout = request_timeout
        # Global token-bucket ingress limiter. None disables rate limiting.
        self.rate_limit = rate_limit
        self.rate_burst = rate_burst


class TokenBucketLimiter:
    """Global async token-bucket rate limiter. 全局令牌桶限流器

    Refills ``rate`` tokens per second up to ``burst`` capacity. acquire()
    returns True when a token is available (consumes one), False when the
    bucket is empty. Intended for the ASGI ingress hot path where every
    request acquires before dispatch.
    """

    def __init__(self, rate: float, burst: float) -> None:
        self._rate = rate
        self._capacity = burst
        self._tokens = float(burst)
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def acquire(self) -> bool:
        async with self._lock:
            now = asyncio.get_running_loop().time()
            if self._last == 0.0:
                self._last = now
            elapsed = now - self._last
            self._last = now
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False


class HTTPTransportServer:
    """HTTP server for receiving AURC messages.
    接收 AURC 消息的 HTTP 服务器

    Implements a simple HTTP endpoint that:
    1. Accepts JSON-encoded AURC messages via POST / 通过 POST 接收 JSON 编码的 AURC 消息
    2. Routes them to the local handler / 路由到本地处理函数
    3. Returns JSON-encoded responses / 返回 JSON 编码的响应

    Usage / 用法:
        server = HTTPTransportServer(host="0.0.0.0", port=8080)
        server.set_handler(handle_aurc_message)
        await server.start()
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8080) -> None:
        self._host = host
        self._port = port
        self._handler: HTTPMessageHandler | None = None
        self._dashboard_api: Any = None  # DashboardAPI ASGI app
        self._server: Any = None  # Will hold the actual server instance
        self._serve_task: asyncio.Task[None] | None = None  # tracked for graceful drain
        self._running = False
        # Extra POST routes: path -> handler (for bridge endpoints, etc.)
        self._routes: dict[str, HTTPMessageHandler] = {}
        # Ingress hardening (TODO P1-2): body cap, connection cap, request
        # timeout, and a global token-bucket rate limiter.
        self._ingress = IngressLimits()
        self._limiter: TokenBucketLimiter | None = (
            TokenBucketLimiter(self._ingress.rate_limit, self._ingress.rate_burst)
            if self._ingress.rate_limit is not None
            else None
        )

    @property
    def ingress_limits(self) -> IngressLimits:
        """The active ingress policy (read-only view). 当前入口策略"""
        return self._ingress

    def set_ingress_limits(self, limits: IngressLimits) -> None:
        """Replace the ingress policy. Must be called before start().
        替换入口策略，须在 start() 前调用。"""
        self._ingress = limits
        self._limiter = (
            TokenBucketLimiter(limits.rate_limit, limits.rate_burst)
            if limits.rate_limit is not None
            else None
        )

    def set_handler(self, handler: HTTPMessageHandler) -> None:
        """Set the message handler. 设置消息处理函数"""
        self._handler = handler

    def set_dashboard_api(self, api: Any) -> None:
        """Mount a DashboardAPI ASGI app for /dashboard and /api/* routes.
        挂载仪表盘 ASGI 应用"""
        self._dashboard_api = api

    def set_route(self, path: str, handler: HTTPMessageHandler) -> None:
        """Register an extra POST route (e.g. an A2A/ACP bridge endpoint).
        注册额外的 POST 路由（如桥接端点）"""
        self._routes[path] = handler

    async def start(self) -> None:
        """Start the HTTP server and block until it stops.

        启动 HTTP 服务器并阻塞直到其停止。

        The uvicorn Server.serve() runs in a tracked task so that
        stop() can await the graceful drain of in-flight requests.
        """
        try:
            from uvicorn import Config, Server

            # Create ASGI app / 创建 ASGI 应用
            app = self._create_app()
            config = Config(
                app=app,
                host=self._host,
                port=self._port,
                log_level="info",
                limit_concurrency=self._ingress.max_connections,
            )
            self._server = Server(config)
            self._running = True
            logger.info("HTTP transport server starting on %s:%d", self._host, self._port)
            # Run serve in a tracked task so stop() can await graceful drain
            # / 在可追踪任务中运行 serve，使 stop() 能等待优雅排空
            self._serve_task = asyncio.create_task(self._server.serve())
            try:
                await self._serve_task
            finally:
                self._running = False
        except ImportError:
            logger.error("uvicorn not installed. Install with: pip install gaiaagent[http]")
            raise HTTPTransportError("uvicorn is required for HTTP transport")

    async def stop(self, timeout: float = 5.0) -> None:
        """Stop the HTTP server, awaiting graceful drain of in-flight requests.

        停止 HTTP 服务器，等待在途请求优雅排空。

        Sets should_exit so uvicorn finishes active connections, then waits
        up to timeout seconds; on timeout it flips force_exit for a hard
        shutdown so callers are never blocked indefinitely.
        """
        server = self._server
        task = self._serve_task
        if server is not None:
            server.should_exit = True
            if task is not None and not task.done():
                try:
                    # shield() keeps serve alive if wait_for times out
                    # / shield() 保证超时时不取消 serve 任务
                    await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
                except asyncio.TimeoutError:
                    logger.warning(
                        "HTTP server did not drain within %.1fs; forcing exit",
                        timeout,
                    )
                    server.force_exit = True
                    await task
            self._running = False
            logger.info("HTTP transport server stopped")

    def install_signal_handlers(self) -> None:
        """Best-effort SIGINT/SIGTERM hooks for graceful drain on signal.

        尽力安装 SIGINT/SIGTERM 钩子，收到信号时优雅排空。

        uvicorn installs its own handlers in the main thread by default; call
        this when running outside the main thread, or when you want GaiaAgent
        drain-on-signal behavior. Silently no-ops on platforms lacking support.
        """
        import signal

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        def _drain() -> None:
            logger.info("Received shutdown signal; draining HTTP server")
            if self._server is not None:
                self._server.should_exit = True

        for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
            if sig is None:
                continue
            try:
                loop.add_signal_handler(sig, _drain)
            except (NotImplementedError, RuntimeError, ValueError):
                # Windows ProactorEventLoop / non-main thread unsupported
                # / Windows 或非主线程下不支持，安全跳过
                continue

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def endpoint_url(self) -> str:
        return f"http://{self._host}:{self._port}/aurc"

    def _create_app(self) -> Any:
        """Create the ASGI application. 创建 ASGI 应用"""
        handler = self._handler

        async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
            if scope["type"] != "http":
                return

            method = scope.get("method", "")
            path = scope.get("path", "")
            limiter = self._limiter
            if limiter is not None and not await limiter.acquire():
                await _send_error(send, 429, "rate_limited", "Too many requests")
                return

            # Route dashboard requests to the DashboardAPI ASGI app
            # / 将仪表盘请求路由到 DashboardAPI
            if path.startswith("/dashboard") or path.startswith("/api/") or path == "/metrics":
                if self._dashboard_api is not None:
                    await self._dashboard_api.handle_request(scope, receive, send)
                    return
                # No dashboard configured / 仪表盘未配置
                await send({
                    "type": "http.response.start",
                    "status": 404,
                    "headers": [[b"content-type", b"application/json"]],
                })
                await send({
                    "type": "http.response.body",
                    "body": json.dumps({"error": "Dashboard not enabled"}).encode(),
                })
                return

            # Extra registered routes (bridge endpoints, etc.)
            if method == "POST" and path in self._routes:
                route_handler = self._routes[path]
                body = await _read_bounded(receive, self._ingress.max_body_bytes, send)
                if body is None:
                    return  # oversized -> already responded
                try:
                    request_data = json.loads(body)
                    response_data = await asyncio.wait_for(
                        route_handler(request_data),
                        timeout=self._ingress.request_timeout,
                    )
                    response_body = json.dumps(response_data, default=str).encode()
                    await send({
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [
                            [b"content-type", b"application/json"],
                            [b"x-protocol", b"aurc/0.1"],
                        ],
                    })
                    await send({"type": "http.response.body", "body": response_body})
                except Exception:
                    logger.exception("Ingress route handler error on %s", path)
                    await _send_error(send, 500, "internal_error", "Internal error")
                return

            # Only handle POST /aurc / 只处理 POST /aurc
            if method == "POST" and path in ("/aurc", "/aurc/"):
                # Read request body / 读取请求体
                body = await _read_bounded(receive, self._ingress.max_body_bytes, send)
                if body is None:
                    return  # oversized -> already responded

                try:
                    request_data = json.loads(body)
                    if handler:
                        response_data = await asyncio.wait_for(
                            handler(request_data),
                            timeout=self._ingress.request_timeout,
                        )
                    else:
                        response_data = {"error": "No handler configured"}

                    response_body = json.dumps(response_data, default=str).encode()
                    await send({
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [
                            [b"content-type", b"application/json"],
                            [b"x-protocol", b"aurc/0.1"],
                        ],
                    })
                    await send({
                        "type": "http.response.body",
                        "body": response_body,
                    })
                except Exception:
                    logger.exception("Ingress handler error on /aurc")
                    await _send_error(send, 500, "internal_error", "Internal error")
                return

            elif method == "GET" and path in ("/health", "/health/"):
                health = json.dumps({"status": "ok", "protocol": "aurc/0.1"}).encode()
                await send({
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [[b"content-type", b"application/json"]],
                })
                await send({
                    "type": "http.response.body",
                    "body": health,
                })

            else:
                await send({
                    "type": "http.response.start",
                    "status": 404,
                    "headers": [[b"content-type", b"application/json"]],
                })
                await send({
                    "type": "http.response.body",
                    "body": json.dumps({"error": "Not found"}).encode(),
                })

        return app


async def _read_bounded(
    receive: Any, max_bytes: int, send: Any
) -> bytes | None:
    """Read the ASGI request body, capped at ``max_bytes``.

    Returns the body, or None when the body exceeds the cap (in which case a
    413 envelope has already been sent and the caller must return).
    """
    body = b""
    while True:
        message = await receive()
        chunk: bytes = message.get("body", b"")
        body += chunk
        if max_bytes > 0 and len(body) > max_bytes:
            await _send_error(send, 413, "payload_too_large", "Request body too large")
            return None
        if not message.get("more_body", False):
            break
    return body


async def _send_error(
    send: Any, status: int, code: str, message: str
) -> None:
    """Send a structured JSON error envelope, never leaking raw exceptions.

    Single error-exit for the transport layer: {code, message} with a stable
    shape that callers can branch on. Internal exception text stays in the
    server log, not on the wire.
    """
    body = json.dumps({"error": {"code": code, "message": message}}).encode()
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [[b"content-type", b"application/json"]],
    })
    await send({"type": "http.response.body", "body": body})


class HTTPTransportClient:
    """HTTP client for sending AURC messages.

    Uses a long-lived httpx.AsyncClient (connection pooling) with
    configurable connect/read timeouts and exponential-backoff retry on
    transient failures. Falls back to urllib when httpx is unavailable.

    Usage / 用法:
        client = HTTPTransportClient()
        response = await client.send("http://localhost:8080/aurc", message_dict)
        await client.close()  # close the pooled client when done
    """

    def __init__(
        self,
        timeout_seconds: float = 30.0,
        *,
        connect_timeout: float = 5.0,
        read_timeout: float | None = None,
        max_retries: int = 3,
        retry_backoff: float = 0.5,
    ) -> None:
        self._timeout = timeout_seconds
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout if read_timeout is not None else timeout_seconds
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff
        self._client: Any = None  # lazily-created long-lived httpx.AsyncClient

    async def _get_client(self) -> Any:
        """Return the long-lived pooled client, creating it on first use."""
        if self._client is not None:
            return self._client
        try:
            import httpx

            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=self._connect_timeout,
                    read=self._read_timeout,
                    write=self._timeout,
                    pool=self._timeout,
                ),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            )
        except ImportError:
            self._client = None  # signal urllib fallback
        return self._client

    async def send(self, url: str, message: dict[str, Any]) -> dict[str, Any]:
        """Send an AURC message via HTTP POST, retrying transient failures.

        通过 HTTP POST 发送 AURC 消息，对瞬时故障指数退避重试。

        Args:
            url: Target URL / 目标 URL
            message: Message as dict / 消息字典

        Returns:
            Response dict / 响应字典

        Raises:
            HTTPTransportError: If all retries are exhausted or the server
                returns a non-transient error.
        """
        client = await self._get_client()
        if client is None:
            return self._send_urllib(url, message)

        import asyncio

        headers = {"Content-Type": "application/json", "X-Protocol": "aurc/0.1"}
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await client.post(url, json=message, headers=headers)
                response.raise_for_status()
                result: dict[str, Any] = response.json()
                return result
            except Exception as exc:
                last_exc = exc
                if not self._is_retryable(exc) or attempt == self._max_retries:
                    break
                backoff = self._retry_backoff * (2 ** attempt)
                logger.warning(
                    "HTTP send attempt %d failed (%s); retrying in %.2fs",
                    attempt + 1, type(exc).__name__, backoff,
                )
                await asyncio.sleep(backoff)
        raise HTTPTransportError(
            f"send to {url} failed after {self._max_retries + 1} attempt(s): {last_exc}"
        ) from last_exc

    def _send_urllib(self, url: str, message: dict[str, Any]) -> dict[str, Any]:
        """urllib fallback (no retry, no pooling). urllib 回退。"""
        import urllib.request

        data = json.dumps(message, default=str).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "X-Protocol": "aurc/0.1"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            result: dict[str, Any] = json.loads(resp.read())
        return result

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        """True for transient (connection/timeout/5xx) failures, False for 4xx."""
        name = type(exc).__name__
        # httpx transport errors (connect/read/timeout/pool) are retryable.
        if name in {"ConnectError", "ReadTimeout", "WriteTimeout", "PoolTimeout",
                    "ConnectTimeout", "ReadError", "RemoteProtocolError"}:
            return True
        # httpx.HTTPStatusError: retry on 5xx and 429, not on other 4xx.
        status = getattr(exc, "response", None)
        if status is not None:
            code = getattr(status, "status_code", None)
            if isinstance(code, int):
                return code >= 500 or code == 429
        return False

    async def health_check(self, url: str) -> dict[str, Any]:
        """Check health of a remote agent. 检查远程 Agent 的健康状态"""
        try:
            from urllib.parse import urlparse

            client = await self._get_client()
            if client is None:
                import urllib.request

                parsed = urlparse(url)
                health_url = f"{parsed.scheme}://{parsed.netloc}/health"
                with urllib.request.urlopen(health_url, timeout=self._timeout) as resp:
                    result2: dict[str, Any] = json.loads(resp.read())
                return result2
            parsed = urlparse(url)
            health_url = f"{parsed.scheme}://{parsed.netloc}/health"
            response = await client.get(health_url)
            result: dict[str, Any] = response.json()
            return result
        except Exception:
            return {"status": "unreachable"}

    async def close(self) -> None:
        """Close the pooled client session. 关闭连接池客户端会话"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
