"""AURC HTTP Transport — HTTP/2 based message transport.
AURC HTTP 传输 — 基于 HTTP/2 的消息传输

Provides an HTTP server and client for AURC message exchange.
Uses JSON over HTTP POST for request/response patterns.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)

# Type for message handlers / 消息处理函数类型
HTTPMessageHandler = Callable[[dict], Awaitable[dict]]


class HTTPTransportError(Exception):
    """HTTP transport error. HTTP 传输错误"""
    pass


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
        self._server: Any = None  # Will hold the actual server instance
        self._running = False

    def set_handler(self, handler: HTTPMessageHandler) -> None:
        """Set the message handler. 设置消息处理函数"""
        self._handler = handler

    async def start(self) -> None:
        """Start the HTTP server. 启动 HTTP 服务器"""
        try:
            import uvicorn
            from uvicorn import Config, Server

            # Create ASGI app / 创建 ASGI 应用
            app = self._create_app()
            config = Config(app=app, host=self._host, port=self._port, log_level="info")
            self._server = Server(config)
            self._running = True
            logger.info("HTTP transport server starting on %s:%d", self._host, self._port)
            await self._server.serve()
        except ImportError:
            logger.error("uvicorn not installed. Install with: pip install gaiaagent[http]")
            raise HTTPTransportError("uvicorn is required for HTTP transport")

    async def stop(self) -> None:
        """Stop the HTTP server. 停止 HTTP 服务器"""
        if self._server:
            self._server.should_exit = True
            self._running = False
            logger.info("HTTP transport server stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def endpoint_url(self) -> str:
        return f"http://{self._host}:{self._port}/aurc"

    def _create_app(self) -> Any:
        """Create the ASGI application. 创建 ASGI 应用"""
        handler = self._handler

        async def app(scope: dict, receive: Any, send: Any) -> None:
            if scope["type"] != "http":
                return

            method = scope.get("method", "")
            path = scope.get("path", "")

            # Only handle POST /aurc / 只处理 POST /aurc
            if method == "POST" and path in ("/aurc", "/aurc/"):
                # Read request body / 读取请求体
                body = b""
                while True:
                    message = await receive()
                    body += message.get("body", b"")
                    if not message.get("more_body", False):
                        break

                try:
                    request_data = json.loads(body)
                    if handler:
                        response_data = await handler(request_data)
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
                except Exception as e:
                    error_body = json.dumps({"error": str(e)}).encode()
                    await send({
                        "type": "http.response.start",
                        "status": 500,
                        "headers": [[b"content-type", b"application/json"]],
                    })
                    await send({
                        "type": "http.response.body",
                        "body": error_body,
                    })

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


class HTTPTransportClient:
    """HTTP client for sending AURC messages.
    发送 AURC 消息的 HTTP 客户端

    Usage / 用法:
        client = HTTPTransportClient()
        response = await client.send("http://localhost:8080/aurc", message_dict)
    """

    def __init__(self, timeout_seconds: float = 30.0) -> None:
        self._timeout = timeout_seconds
        self._session: Any = None

    async def send(self, url: str, message: dict) -> dict:
        """Send an AURC message via HTTP POST.
        通过 HTTP POST 发送 AURC 消息

        Args:
            url: Target URL / 目标 URL
            message: Message as dict / 消息字典

        Returns:
            Response dict / 响应字典
        """
        try:
            import httpx
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    url,
                    json=message,
                    headers={
                        "Content-Type": "application/json",
                        "X-Protocol": "aurc/0.1",
                    },
                )
                response.raise_for_status()
                return response.json()
        except ImportError:
            # Fallback to urllib / 回退到 urllib
            import urllib.request
            data = json.dumps(message, default=str).encode()
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json", "X-Protocol": "aurc/0.1"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read())

    async def health_check(self, url: str) -> dict:
        """Check health of a remote agent. 检查远程 Agent 的健康状态"""
        try:
            from urllib.parse import urlparse
            import httpx
            parsed = urlparse(url)
            health_url = f"{parsed.scheme}://{parsed.netloc}/health"
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(health_url)
                return response.json()
        except Exception:
            return {"status": "unreachable"}

    async def close(self) -> None:
        """Close the client session. 关闭客户端会话"""
        if self._session:
            await self._session.aclose()
