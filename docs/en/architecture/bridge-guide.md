# Bridge Developer Guide

> 🌐 [中文版](../../zh/architecture/bridge-guide.md)
> **[← Back to README](../../../README.md)** | [Architecture](../architecture.md) | [Protocol Spec](../../../PROTOCOL.md) | [API Reference](../api-reference.md)
>
> How to write a custom protocol bridge for AURC.

## What is a Bridge?

A Bridge translates between AURC's canonical message format and an external protocol.
It enables AURC agents to communicate with agents on other protocols (MCP, A2A, gRPC, etc.).

## Bridge Interface

Every bridge must implement these methods:

```python
class MyCustomBridge:
    @property
    def source_protocol(self) -> str:
        """External protocol identifier.
        Example: 'grpc/1.0', 'custom/2.0'
        """
        return "custom/2.0"

    def can_bridge(self, source: str, target: str) -> bool:
        """Check if this bridge handles the given protocol pair."""
        return (source == self.source_protocol and target == "aurc/0.1") or \
               (source == "aurc/0.1" and target == self.source_protocol)

    async def translate_to_aurc(self, external_message: Any) -> AURCMessage:
        """Convert external protocol message → AURC message."""
        ...

    async def translate_from_aurc(self, aurc_message: AURCMessage) -> Any:
        """Convert AURC message → external protocol message."""
        ...

    async def map_capabilities(self, external_caps: list) -> list[dict]:
        """Map external capabilities to AURC skill declarations."""
        ...
```

## Step-by-Step: Writing a gRPC Bridge

### 1. Define the mapping

| gRPC Concept | AURC Concept |
|-------------|-------------|
| Service method | Skill |
| Protobuf message | AURCMessage body |
| Unary call | request/response |
| Server streaming | stream |
| Service descriptor | AgentDescriptor |

### 2. Implement translate_to_aurc

```python
async def translate_to_aurc(self, grpc_request: dict) -> AURCMessage:
    return AURCMessage(
        source=f"grpc:external/{grpc_request.get('service', 'unknown')}",
        target="aurc:local/handler",
        type=MessageDirection.REQUEST,
        body=MessageBody(
            method="invoke",
            skill=grpc_request.get("method", ""),
            params=grpc_request.get("params", {}),
        ),
        protocol_context=BridgeContext(
            origin_protocol="grpc/1.0",
            bridged_from="grpc/1.0",
            bridge_chain=["grpc→aurc"],
        ),
    )
```

### 3. Implement translate_from_aurc

```python
async def translate_from_aurc(self, msg: AURCMessage) -> dict:
    if msg.type == MessageDirection.REQUEST:
        return {
            "service": msg.target.split("/")[-1],
            "method": msg.body.skill,
            "params": msg.body.params,
        }
    elif msg.type == MessageDirection.RESPONSE:
        if msg.body.error:
            return {"error": {"code": 2, "message": msg.body.error.message}}
        return {"result": msg.body.result}
```

### 4. Register with BridgeRegistry

```python
from gaiaagent.bridges import BridgeRegistry

registry = BridgeRegistry()
registry.register(GrpcBridge())
```

### 5. Connect to MessageRouter

```python
from gaiaagent.bus import MessageRouter

router = MessageRouter()

async def grpc_forwarder(msg: AURCMessage):
    grpc_msg = await grpc_bridge.translate_from_aurc(msg)
    # Send to gRPC server...
    return {"status": "forwarded"}

router.register_bridge_forwarder("grpc", grpc_forwarder)
```

## Testing Your Bridge

```python
import pytest
from gaiaagent.core.message import AURCMessage, MessageDirection

@pytest.mark.asyncio
async def test_grpc_to_aurc():
    bridge = GrpcBridge()
    grpc_msg = {"service": "search", "method": "query", "params": {"q": "test"}}
    aurc_msg = await bridge.translate_to_aurc(grpc_msg)
    assert aurc_msg.type == MessageDirection.REQUEST
    assert aurc_msg.body.skill == "query"

@pytest.mark.asyncio
async def test_aurc_to_grpc():
    bridge = GrpcBridge()
    aurc_msg = AURCMessage(
        source="aurc:test:v1.0", target="grpc:search:v1.0",
        type=MessageDirection.REQUEST,
        body=MessageBody(method="invoke", skill="query", params={"q": "test"}),
    )
    grpc_msg = await bridge.translate_from_aurc(aurc_msg)
    assert grpc_msg["method"] == "query"
```

## Existing Bridges for Reference

| Bridge | File | Protocol |
|--------|------|----------|
| MCPBridge | `bridges/base.py` | MCP (JSON-RPC 2.0) |
| A2ABridge | `bridges/a2a.py` | A2A (JSON-RPC 2.0 + SSE) |
| ACPBridge | `bridges/acp.py` | ACP (HTTP JSON envelope) |
