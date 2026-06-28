# Transport

HTTP and WebSocket transports for AURC message exchange. JSON over the wire.

## Contract (verified against `transport/http.py`, `transport/websocket.py`)

- **HTTP server is uvicorn-backed.** `HTTPTransportServer.start()` runs `uvicorn.Server.serve()` in a **tracked** `asyncio.Task` (`_serve_task`) so that `stop()` can await the graceful drain of in-flight requests. Never lose the task reference (an untracked `create_task` can be GC'd mid-drain — TODO P2 applies the same fix to `lifecycle._fire_listeners`).
- **Graceful drain + timeout force-exit.** `stop()` drains in-flight requests then forces exit on timeout. SIGTERM hooks trigger the same path (Phase 4.3). Do not add a `Server.should_exit = True` without going through `stop()`.
- **WebSocket heartbeat.** `WebSocketTransportServer` is constructed with `ping_interval` (default 20s) and `ping_timeout` (default 10s); the underlying `websockets` server runs ping/pong. Stale connections that miss the pong are dropped. Do not disable the heartbeat to "fix" a connectivity issue — find the real cause.
- **Extra POST routes** (`set_route`) mount bridge endpoints (e.g. A2A/ACP inbound). They share the same JSON handler contract as the main AURC endpoint.
- **Ingress hardening is enforced** (TODO P1-2, done). `HTTPTransportServer` carries an `IngressLimits` policy (default 1 MiB body, 1024 concurrent connections, 30 s request timeout, 100 req/s global token bucket with 200 burst), overridable via `set_ingress_limits()` before `start()`. uvicorn gets `limit_concurrency`; the ASGI app rate-limits at the top (429 `rate_limited`), reads bodies via `_read_bounded()` (413 `payload_too_large` on overflow), and wraps handlers in `asyncio.wait_for(request_timeout)`. `WebSocketTransportServer`/`Client` take `max_frame_bytes` (default 10 MB) passed to `websockets` `max_size`. Error exits go through a single structured mapping layer (`_send_error` / `_ws_error_envelope`) -- `{error:{code,message}}` -- never raw `str(exc)`.

## When editing here

- The HTTP `http_handler` maps `AuthzDeniedError` to a `forbidden` error envelope and other errors to the structured envelope — keep error出口 in the mapping layer, not scattered in the transport.
- Transports are optional dependencies (`httpx`/`uvicorn`/`websockets` in the `http`/`ws` extras). Import them lazily inside `start()` so `import gaiaagent` works without transport deps installed. Do not move them to top-level imports.
- A new transport (e.g. gRPC, stdio): follow the same shape — tracked serve task, graceful stop, structured error envelope, lazy import.
