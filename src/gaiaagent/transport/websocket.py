"""AURC WebSocket Transport — real-time bidirectional messaging.
AURC WebSocket 传输 — 实时双向消息

Provides a WebSocket server and client for AURC message exchange.
Uses JSON over WebSocket for persistent, bidirectional, real-time communication.
提供基于 WebSocket 的服务器和客户端，用于 AURC 消息交换。
使用 JSON over WebSocket 实现持久、双向、实时通信。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

# Type for message handlers / 消息处理函数类型
WebSocketMessageHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]


class WebSocketTransportError(Exception):
    """WebSocket transport error. WebSocket 传输错误"""
    pass


def _ws_error_envelope(code: str, message: str) -> str:
    """Build a structured JSON error string for the wire.

    Mirrors the HTTP transport's error shape so clients branch on a stable
    {error: {code, message}} envelope across both transports. Raw exception
    text is kept out of the response.
    """
    return json.dumps({"error": {"code": code, "message": message}})


# =============================================================================
# Server / 服务器
# =============================================================================


class WebSocketTransportServer:
    """WebSocket server for real-time bidirectional AURC messaging.
    用于实时双向 AURC 消息的 WebSocket 服务器

    Implements a persistent WebSocket endpoint that:
    实现持久 WebSocket 端点：
    1. Accepts WebSocket connections from remote agents / 接受远程 Agent 的 WebSocket 连接
    2. Routes incoming messages to the local handler / 将收到的消息路由到本地处理函数
    3. Supports broadcasting to all connected clients / 支持向所有已连接客户端广播
    4. Tracks connected clients for lifecycle management / 跟踪已连接客户端以进行生命周期管理

    Usage / 用法:
        server = WebSocketTransportServer(host="0.0.0.0", port=8765)
        server.set_handler(handle_aurc_message)
        await server.start()
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        ping_interval: float = 20.0,
        ping_timeout: float = 10.0,
        max_frame_bytes: int = 10 * 1024 * 1024,
    ) -> None:
        self._host = host
        self._port = port
        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout
        self._max_frame_bytes = max_frame_bytes
        self._handler: WebSocketMessageHandler | None = None
        self._server: Any = None  # websockets.Server instance / websockets 服务器实例
        self._running = False
        # Track connected clients for broadcasting / 跟踪已连接客户端用于广播
        self._clients: set[Any] = set()

    def set_handler(self, handler: WebSocketMessageHandler) -> None:
        """Set the async message handler. 设置异步消息处理函数

        Args:
            handler: Async callable that receives a message dict and optionally
                     returns a response dict. / 接收消息字典并可选返回响应字典的异步可调用对象
        """
        self._handler = handler

    async def start(self) -> None:
        """Start the WebSocket server. 启动 WebSocket 服务器

        Raises:
            WebSocketTransportError: If the websockets library is not installed.
                                     如果 websockets 库未安装。
        """
        try:
            from websockets import serve  # type: ignore[import-not-found]
        except ImportError:
            logger.error(
                "websockets not installed. Install with: pip install gaiaagent[websocket]"
            )
            raise WebSocketTransportError(
                "websockets library is required for WebSocket transport"
            )

        self._running = True
        handler = self._create_handler()
        logger.info(
            "WebSocket transport server starting on ws://%s:%d",
            self._host,
            self._port,
        )

        try:
            self._server = await serve(
                handler,
                self._host,
                self._port,
                # Inbound frame cap: oversized messages are rejected by the
                # websockets library before they reach the handler. / 入口帧上限
                max_size=self._max_frame_bytes,
                # Heartbeat: server pings idle clients every ping_interval
                # and drops them if no pong within ping_timeout. This detects
                # half-open connections (NAT timeout, dead peers) proactively.
                ping_interval=self._ping_interval,
                ping_timeout=self._ping_timeout,
            )
            # Block until the server is closed / 阻塞直到服务器关闭
            await self._server.wait_closed()
        except OSError as e:
            self._running = False
            raise WebSocketTransportError(
                f"Failed to start WebSocket server on {self._host}:{self._port}: {e}"
            ) from e

    async def stop(self) -> None:
        """Stop the WebSocket server and close all client connections.
        停止 WebSocket 服务器并关闭所有客户端连接
        """
        self._running = False

        # Close all connected clients / 关闭所有已连接客户端
        for ws in list(self._clients):
            try:
                await ws.close(1001, "Server shutting down")
            except Exception:
                pass
        self._clients.clear()

        # Close the server / 关闭服务器
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        logger.info("WebSocket transport server stopped")

    async def broadcast(self, message_dict: dict[str, Any]) -> None:
        """Send a message to all connected clients. 向所有已连接客户端发送消息

        Args:
            message_dict: Message as dict to broadcast / 要广播的消息字典
        """
        if not self._clients:
            logger.debug("No connected clients to broadcast to / 没有已连接客户端可广播")
            return

        data = json.dumps(message_dict, default=str)
        # Send concurrently to all clients / 并发发送给所有客户端
        disconnected: list[Any] = []
        send_tasks = []
        for ws in self._clients:
            send_tasks.append(self._safe_send(ws, data, disconnected))

        await asyncio.gather(*send_tasks)

        # Remove disconnected clients / 移除已断开的客户端
        for ws in disconnected:
            self._clients.discard(ws)

    @property
    def is_running(self) -> bool:
        """Whether the server is currently running. 服务器是否正在运行"""
        return self._running

    @property
    def client_count(self) -> int:
        """Number of currently connected clients. 当前已连接客户端数量"""
        return len(self._clients)

    def _create_handler(self) -> Callable[..., Any]:
        """Create the WebSocket connection handler. 创建 WebSocket 连接处理函数

        Returns:
            An async handler function compatible with websockets.serve().
            与 websockets.serve() 兼容的异步处理函数。
        """
        server_ref = self

        async def ws_handler(websocket: Any) -> None:
            """Handle a single WebSocket client connection.
            处理单个 WebSocket 客户端连接
            """
            remote = websocket.remote_address
            logger.info("Client connected: %s", remote)
            server_ref._clients.add(websocket)

            try:
                async for raw_message in websocket:
                    try:
                        data = json.loads(raw_message)
                    except json.JSONDecodeError as e:
                        logger.warning(
                            "Invalid JSON from %s: %s / 来自 %s 的无效 JSON: %s",
                            remote, e, remote, e,
                        )
                        # Structured error envelope; raw parse error stays in the log.
                        # / 结构化错误信封，原始解析错误仅留日志
                        await websocket.send(
                            _ws_error_envelope("bad_message", "Malformed message")
                        )
                        continue

                    # Route to handler / 路由到处理函数
                    if server_ref._handler:
                        try:
                            response = await server_ref._handler(data)
                            if response is not None:
                                await websocket.send(
                                    json.dumps(response, default=str)
                                )
                        except Exception as e:
                            logger.error(
                                "Handler error for %s: %s / 处理 %s 时出错: %s",
                                remote, e, remote, e,
                            )
                            # Internal exception text never goes on the wire.
                            # / 内部异常文本不上线路
                            await websocket.send(
                                _ws_error_envelope("internal_error", "Internal error")
                            )
                    else:
                        # No handler configured / 未配置处理函数
                        logger.warning(
                            "No handler configured, echoing message / 未配置处理函数，回显消息"
                        )
                        await websocket.send(json.dumps({
                            "warning": "No handler configured",
                            "echo": data,
                        }, default=str))

            except Exception as e:
                # websockets raises ConnectionClosed or similar
                # websockets 抛出 ConnectionClosed 等
                logger.info("Client disconnected: %s (%s)", remote, e)
            finally:
                server_ref._clients.discard(websocket)
                logger.info("Client removed: %s", remote)

        return ws_handler

    @staticmethod
    async def _safe_send(
        ws: Any, data: str, disconnected: list[Any]
    ) -> None:
        """Send data to a WebSocket, tracking failures. 向 WebSocket 发送数据，跟踪失败

        Args:
            ws: WebSocket connection / WebSocket 连接
            data: JSON string to send / 要发送的 JSON 字符串
            disconnected: List to append failed connections to / 用于记录失败连接的列表
        """
        try:
            await ws.send(data)
        except Exception:
            disconnected.append(ws)


# =============================================================================
# Client / 客户端
# =============================================================================


class WebSocketTransportClient:
    """WebSocket client for real-time bidirectional AURC messaging.
    用于实时双向 AURC 消息的 WebSocket 客户端

    Features / 功能:
    - Persistent WebSocket connection / 持久 WebSocket 连接
    - Automatic reconnection with exponential backoff / 指数退避自动重连
    - Subscribe pattern for background message handling / 订阅模式用于后台消息处理
    - JSON message serialization / JSON 消息序列化

    Usage / 用法:
        client = WebSocketTransportClient(url="ws://localhost:8765")
        await client.connect()
        await client.send({"type": "request", "method": "invoke"})
        response = await client.receive()

        # Or use subscribe for background listening / 或使用 subscribe 后台监听
        await client.subscribe(on_message)
    """

    # Default reconnection parameters / 默认重连参数
    _DEFAULT_RECONNECT_DELAY = 1.0       # Initial delay in seconds / 初始延迟秒数
    _DEFAULT_MAX_RECONNECT_DELAY = 30.0  # Max delay in seconds / 最大延迟秒数
    _RECONNECT_BACKOFF_FACTOR = 2.0      # Exponential backoff multiplier / 指数退避乘数

    def __init__(
        self,
        url: str = "ws://localhost:8765",
        timeout: float = 30.0,
        reconnect: bool = True,
        max_reconnect_delay: float = _DEFAULT_MAX_RECONNECT_DELAY,
        heartbeat_interval: float = 20.0,
        max_frame_bytes: int = 10 * 1024 * 1024,
    ) -> None:
        """Initialize the WebSocket client. 初始化 WebSocket 客户端

        Args:
            url: WebSocket server URL / WebSocket 服务器 URL
            timeout: Connection timeout in seconds / 连接超时秒数
            reconnect: Enable automatic reconnection / 启用自动重连
            max_reconnect_delay: Maximum reconnection delay in seconds / 最大重连延迟秒数
            heartbeat_interval: Seconds between client-initiated pings
                (keeps NAT/firewall mappings alive and detects dead peers).
                客户端 ping 间隔秒数（保活 NAT/防火墙映射并检测死亡对端）。
            max_frame_bytes: Max inbound message size in bytes / 入口最大帧字节数
        """
        self._url = url
        self._timeout = timeout
        self._reconnect_enabled = reconnect
        self._max_reconnect_delay = max_reconnect_delay
        self._heartbeat_interval = heartbeat_interval
        self._max_frame_bytes = max_frame_bytes
        self._ws: Any = None  # websockets.ClientConnection / websockets 客户端连接
        self._connected = False
        self._listener_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._closing = False  # Flag to prevent reconnection during close / 关闭时阻止重连的标志

    async def connect(self) -> None:
        """Establish WebSocket connection to the server.
        建立到服务器的 WebSocket 连接

        Raises:
            WebSocketTransportError: If websockets is not installed or connection fails.
                                     如果 websockets 未安装或连接失败。
        """
        try:
            from websockets import connect as ws_connect
        except ImportError:
            logger.error(
                "websockets not installed. Install with: pip install gaiaagent[websocket]"
            )
            raise WebSocketTransportError(
                "websockets library is required for WebSocket transport"
            )

        try:
            self._ws = await asyncio.wait_for(
                ws_connect(
                    self._url,
                    max_size=self._max_frame_bytes,
                ),
                timeout=self._timeout,
            )
            self._connected = True
            self._closing = False
            self._start_heartbeat()
            logger.info("WebSocket client connected to %s", self._url)
        except asyncio.TimeoutError as e:
            raise WebSocketTransportError(
                f"Connection to {self._url} timed out after {self._timeout}s"
            ) from e
        except Exception as e:
            raise WebSocketTransportError(
                f"Failed to connect to {self._url}: {e}"
            ) from e

    async def send(self, message_dict: dict[str, Any]) -> None:
        """Send a message over the WebSocket connection.
        通过 WebSocket 连接发送消息

        Args:
            message_dict: Message as dict / 消息字典

        Raises:
            WebSocketTransportError: If not connected or send fails.
                                     如果未连接或发送失败。
        """
        if not self._connected or self._ws is None:
            raise WebSocketTransportError(
                "Not connected to WebSocket server / 未连接到 WebSocket 服务器"
            )

        try:
            data = json.dumps(message_dict, default=str)
            await self._ws.send(data)
        except Exception as e:
            self._connected = False
            raise WebSocketTransportError(f"Failed to send message: {e}") from e

    async def receive(self) -> dict[str, Any]:
        """Receive the next message from the WebSocket connection.
        从 WebSocket 连接接收下一条消息

        Returns:
            Received message as dict / 接收到的消息字典

        Raises:
            WebSocketTransportError: If not connected, receive fails, or
                                     connection is closed.
                                     如果未连接、接收失败或连接已关闭。
        """
        if not self._connected or self._ws is None:
            raise WebSocketTransportError(
                "Not connected to WebSocket server / 未连接到 WebSocket 服务器"
            )

        try:
            raw = await self._ws.recv()
            result: dict[str, Any] = json.loads(raw)
            return result
        except Exception as e:
            self._connected = False
            raise WebSocketTransportError(f"Failed to receive message: {e}") from e

    def _start_heartbeat(self) -> None:
        """Start (or restart) the client-side ping heartbeat task."""
        if self._heartbeat_task and not self._heartbeat_task.done():
            return
        if self._heartbeat_interval <= 0:
            return
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _heartbeat_loop(self) -> None:
        """Periodically ping the server to keep the connection alive.

        Detects half-open peers: if a ping fails the connection is marked
        lost so the reconnect loop in _listen_and_reconnect can take over.
        """
        try:
            while self._connected and not self._closing and self._ws is not None:
                await asyncio.sleep(self._heartbeat_interval)
                if not self._connected or self._closing or self._ws is None:
                    return
                try:
                    await self._ws.ping()
                except Exception as e:
                    logger.warning("heartbeat ping failed: %s", e)
                    self._connected = False
                    return
        except asyncio.CancelledError:
            return

    async def close(self) -> None:
        """Close the WebSocket connection and stop any background listener.
        关闭 WebSocket 连接并停止任何后台监听器
        """
        self._closing = True
        self._connected = False

        # Cancel heartbeat task / 取消心跳任务
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        # Cancel background listener / 取消后台监听器
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

        # Close WebSocket / 关闭 WebSocket
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        logger.info("WebSocket client disconnected from %s", self._url)

    @property
    def is_connected(self) -> bool:
        """Whether the client is currently connected. 客户端是否已连接"""
        return self._connected

    async def subscribe(self, handler: WebSocketMessageHandler) -> None:
        """Register a callback for incoming messages and start background listener.
        注册消息回调并启动后台监听器

        Starts an asyncio.Task that continuously reads messages from the
        WebSocket and dispatches them to the handler. If reconnection is
        enabled, automatically reconnects on connection loss with
        exponential backoff.
        启动一个 asyncio.Task，持续从 WebSocket 读取消息并分发给处理函数。
        如果启用了重连，在连接断开时使用指数退避自动重连。

        Args:
            handler: Async callable invoked with each received message dict.
                     May optionally return a response dict to send back.
                     每条接收到的消息字典调用的异步可调用对象。
                     可选返回响应字典发送回去。
        """
        # Cancel any existing listener / 取消已有的监听器
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        self._listener_task = asyncio.create_task(
            self._listen_and_reconnect(handler)
        )
        logger.info("Background listener started for %s", self._url)

    async def _listen_and_reconnect(
        self, handler: WebSocketMessageHandler
    ) -> None:
        """Background loop: listen for messages with automatic reconnection.
        后台循环：监听消息并自动重连

        This is the core of the subscribe mechanism. It handles:
        这是订阅机制的核心，处理：
        1. Receiving and dispatching messages / 接收和分发消息
        2. Detecting connection loss / 检测连接断开
        3. Reconnecting with exponential backoff / 指数退避重连
        4. Clean shutdown via self._closing flag / 通过 self._closing 标志干净关闭
        """
        reconnect_delay = self._DEFAULT_RECONNECT_DELAY

        while not self._closing:
            # Connect if needed / 必要时连接
            if not self._connected:
                if not self._reconnect_enabled:
                    logger.info(
                        "Connection lost, reconnection disabled / 连接断开，重连已禁用"
                    )
                    return
                try:
                    logger.info(
                        "Reconnecting to %s in %.1fs... / %.1f 秒后重连 %s...",
                        self._url, reconnect_delay, reconnect_delay, self._url,
                    )
                    await asyncio.sleep(reconnect_delay)
                    await self.connect()
                    # Reset delay on successful connection / 成功连接后重置延迟
                    reconnect_delay = self._DEFAULT_RECONNECT_DELAY
                except WebSocketTransportError as e:
                    logger.warning("Reconnection failed: %s / 重连失败: %s", e, e)
                    # Exponential backoff / 指数退避
                    reconnect_delay = min(
                        reconnect_delay * self._RECONNECT_BACKOFF_FACTOR,
                        self._max_reconnect_delay,
                    )
                    continue
                except asyncio.CancelledError:
                    return

            # Listen for messages / 监听消息
            try:
                if self._ws is None:
                    self._connected = False
                    continue

                raw = await self._ws.recv()
                message_dict = json.loads(raw)

                try:
                    response = await handler(message_dict)
                    # Send response back if handler returns one / 如果处理函数返回响应则发送回去
                    if response is not None and self._connected and self._ws:
                        await self._ws.send(json.dumps(response, default=str))
                except Exception as e:
                    logger.error(
                        "Handler error in subscriber: %s / 订阅处理函数错误: %s",
                        e, e,
                    )

            except asyncio.CancelledError:
                return
            except json.JSONDecodeError as e:
                logger.warning(
                    "Invalid JSON received, skipping: %s / 收到无效 JSON，跳过: %s",
                    e, e,
                )
                continue
            except Exception as e:
                # Connection lost — will reconnect on next iteration / 连接断开 — 下次迭代重连
                self._connected = False
                if not self._closing:
                    logger.warning(
                        "Connection lost: %s — will reconnect / 连接断开: %s — 将重连",
                        e, e,
                    )
