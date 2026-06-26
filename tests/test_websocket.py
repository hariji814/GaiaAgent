"""Tests for WebSocket transport — real-time bidirectional messaging.
WebSocket 传输测试 — 实时双向消息
"""


from gaiaagent.transport.websocket import (
    WebSocketTransportClient,
    WebSocketTransportError,
    WebSocketTransportServer,
)


class TestWebSocketServer:
    """Tests for WebSocketTransportServer."""

    def test_server_create(self):
        """Server should initialize with default settings."""
        server = WebSocketTransportServer()
        assert server is not None
        assert not server.is_running
        assert server.client_count == 0

    def test_server_custom_host_port(self):
        """Server should accept custom host and port."""
        server = WebSocketTransportServer(host="127.0.0.1", port=9999)
        assert server is not None

    def test_server_handler_setting(self):
        """Server should accept a message handler."""
        server = WebSocketTransportServer()

        async def my_handler(msg):
            return {"echo": msg}

        server.set_handler(my_handler)
        # Handler should be set without error
        assert server._handler is not None


class TestWebSocketClient:
    """Tests for WebSocketTransportClient."""

    def test_client_create(self):
        """Client should initialize with default settings."""
        client = WebSocketTransportClient(url="ws://localhost:8765")
        assert client is not None
        assert not client.is_connected

    def test_client_custom_timeout(self):
        """Client should accept custom timeout."""
        client = WebSocketTransportClient(
            url="ws://localhost:8765", timeout=10.0
        )
        assert client._timeout == 10.0


class TestWebSocketTransportError:
    """Tests for WebSocketTransportError."""

    def test_error_creation(self):
        """Error should be creatable with a message."""
        err = WebSocketTransportError("Connection failed")
        assert str(err) == "Connection failed"
        assert isinstance(err, Exception)
