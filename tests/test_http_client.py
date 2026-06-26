"""Phase 4.3 tests: HTTPTransportClient connection pool + retry + timeouts.

Verifies the long-lived pooled client is reused, that transient failures
are retried with backoff, that non-retryable 4xx errors are not retried,
and that timeout settings are externalized.
"""
from __future__ import annotations

import asyncio

import pytest

from gaiaagent.transport.http import HTTPTransportClient, HTTPTransportError


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise _StatusError(self)

    def json(self):
        return self._payload


class _StatusError(Exception):
    def __init__(self, resp):
        self.response = resp
        super().__init__(f"HTTP {resp.status_code}")


class FakeClient:
    """Minimal fake httpx.AsyncClient that records calls and scripts responses."""

    def __init__(self, post_responses=None, get_response=None):
        self._post_responses = post_responses or [FakeResponse(200, {"ok": True})]
        self._get_response = get_response
        self.post_calls = 0
        self.closed = False

    async def post(self, url, json=None, headers=None):
        idx = min(self.post_calls, len(self._post_responses) - 1)
        resp = self._post_responses[idx]
        self.post_calls += 1
        if isinstance(resp, Exception):
            raise resp
        return resp

    async def get(self, url):
        if isinstance(self._get_response, Exception):
            raise self._get_response
        return self._get_response

    async def aclose(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _fast_backoff(monkeypatch):
    """Zero out retry backoff so tests don't actually sleep (no real delay)."""
    _real_sleep = asyncio.sleep

    async def _noop(*_a, **_k):
        await _real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _noop)
    yield


class TestPooling:
    async def test_client_reused_across_sends(self, monkeypatch):
        calls = []

        async def fake_get_client(self):
            if self._client is None:
                self._client = FakeClient(post_responses=[FakeResponse()] * 5)
                calls.append("created")
            return self._client

        monkeypatch.setattr(HTTPTransportClient, "_get_client", fake_get_client)
        c = HTTPTransportClient()
        await c.send("http://x/aurc", {})
        await c.send("http://x/aurc", {})
        assert calls == ["created"]  # pooled client created once
        await c.close()

    async def test_close_releases_pool(self, monkeypatch):
        fake = FakeClient()
        async def fake_get_client(self):
            self._client = fake
            return fake
        monkeypatch.setattr(HTTPTransportClient, "_get_client", fake_get_client)
        c = HTTPTransportClient()
        await c.send("http://x/aurc", {})
        await c.close()
        assert fake.closed
        assert c._client is None


class TestRetry:
    async def test_retries_then_succeeds(self, monkeypatch):
        # 2 transient failures then success
        fake = FakeClient(post_responses=[
            _StatusError(FakeResponse(503)),
            _StatusError(FakeResponse(500)),
            FakeResponse(200, {"ok": True}),
        ])
        # _StatusError needs .response.status_code for retryability
        async def fake_get_client(self):
            self._client = fake
            return fake
        monkeypatch.setattr(HTTPTransportClient, "_get_client", fake_get_client)
        c = HTTPTransportClient(max_retries=3, retry_backoff=0)
        result = await c.send("http://x/aurc", {})
        assert result == {"ok": True}
        assert fake.post_calls == 3
        await c.close()

    async def test_no_retry_on_4xx(self, monkeypatch):
        fake = FakeClient(post_responses=[_StatusError(FakeResponse(404))])
        async def fake_get_client(self):
            self._client = fake
            return fake
        monkeypatch.setattr(HTTPTransportClient, "_get_client", fake_get_client)
        c = HTTPTransportClient(max_retries=3, retry_backoff=0)
        with pytest.raises(HTTPTransportError):
            await c.send("http://x/aurc", {})
        assert fake.post_calls == 1  # not retried
        await c.close()

    async def test_exhausts_retries_raises(self, monkeypatch):
        fake = FakeClient(post_responses=[_StatusError(FakeResponse(503))] * 10)
        async def fake_get_client(self):
            self._client = fake
            return fake
        monkeypatch.setattr(HTTPTransportClient, "_get_client", fake_get_client)
        c = HTTPTransportClient(max_retries=2, retry_backoff=0)
        with pytest.raises(HTTPTransportError):
            await c.send("http://x/aurc", {})
        assert fake.post_calls == 3  # initial + 2 retries
        await c.close()


class TestRetryability:
    def test_5xx_retryable(self):
        err = _StatusError(FakeResponse(503))
        assert HTTPTransportClient._is_retryable(err)

    def test_429_retryable(self):
        err = _StatusError(FakeResponse(429))
        assert HTTPTransportClient._is_retryable(err)

    def test_404_not_retryable(self):
        err = _StatusError(FakeResponse(404))
        assert not HTTPTransportClient._is_retryable(err)

    def test_connect_error_retryable_by_name(self):
        class ConnectError(Exception):
            pass
        assert HTTPTransportClient._is_retryable(ConnectError())

    def test_generic_exception_not_retryable(self):
        assert not HTTPTransportClient._is_retryable(ValueError("boom"))


class TestTimeouts:
    def test_externalized_timeouts(self):
        c = HTTPTransportClient(timeout_seconds=30, connect_timeout=5, read_timeout=10)
        assert c._connect_timeout == 5
        assert c._read_timeout == 10
        assert c._timeout == 30
