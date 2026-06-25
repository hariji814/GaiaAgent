> 🌐 [中文版](../../zh/guides/quickstart.md)
> **[← Back to README](../../../README.md)** | [Protocol Spec](../../../PROTOCOL.md) | [Architecture](../architecture.md) | [API Reference](../api-reference.md)
>
> Build your first AURC agent in 5 minutes

## Prerequisites

- Python 3.10+
- `uv` or `pip` package manager

## Installation

```bash
pip install gaiaagent
# or
uv add gaiaagent
```

## 1. Define Your Agent

```python
from gaiaagent.sdk.decorators import aurc_agent, skill

@aurc_agent(
    id="aurc:myproject/translator:v1.0",
    display_name="Translator Agent",
    description="Translates text between languages",
    tags=["translation", "nlp"],
)
class TranslatorAgent:

    @skill("translate", description="Translate text to a target language")
    async def translate(self, text: str, target_lang: str = "en") -> dict:
        # Your translation logic here
        return {
            "original": text,
            "translated": f"[{target_lang}] {text}",
            "confidence": 0.95,
        }

    @skill("detect-language", description="Detect the language of text")
    async def detect_language(self, text: str) -> dict:
        return {"detected_lang": "zh", "confidence": 0.88}
```

## 2. Start the Harness

```python
import asyncio
from gaiaagent.harness.lifecycle import RuntimeHarness

async def run():
    harness = RuntimeHarness()

    # Create and register your agent
    agent = TranslatorAgent()
    await harness.register(agent.aurc_descriptor)

    # Start a task
    await harness.start("aurc:myproject/translator:v1.0")

    # Check health
    health = await harness.health_check("aurc:myproject/translator:v1.0")
    print(f"Status: {health.status.value}")

asyncio.run(run())
```

## 3. Connect to MCP Servers

```python
from gaiaagent.bridges.base import MCPBridge

# Create MCP bridge
mcp_bridge = MCPBridge()

# Translate MCP tool call to AURC
mcp_message = {
    "jsonrpc": "2.0",
    "id": "req-1",
    "method": "tools/call",
    "params": {
        "name": "web-search",
        "arguments": {"query": "AI protocols"}
    }
}

aurc_message = await mcp_bridge.translate_to_aurc(mcp_message)
print(f"AURC skill: {aurc_message.body.skill}")  # "web-search"
```

## 4. Add Security

```python
from gaiaagent.security.auth import APIKeyAuthenticator
from gaiaagent.security.authz import (
    AuthorizationEngine, AgentPolicy, AuthorizationRule, Constraint,
)

# Create API key
auth = APIKeyAuthenticator()
key = auth.create_key(
    "aurc:myproject/translator:v1.0",
    scopes=["translate", "detect"],
)
print(f"API Key: {key}")

# Set authorization policy
engine = AuthorizationEngine()
engine.set_policy("aurc:myproject/translator:v1.0", AgentPolicy(
    agent_id="aurc:myproject/translator:v1.0",
    rules=[
        AuthorizationRule(
            resource_type="translation-api",
            actions=["execute"],
            constraints=[
                Constraint("text_length", "lte", 5000),
            ],
            rate_limit=1000,
        ),
    ],
))

# Check authorization
result = engine.authorize(
    agent_id="aurc:myproject/translator:v1.0",
    resource_type="translation-api",
    action="execute",
    attributes={"text_length": 200},
)
print(f"Authorized: {result.allowed}")  # True
```

## 5. Route Messages

```python
from gaiaagent.bus.router import MessageRouter
from gaiaagent.core.message import AURCMessage, MessageBody
from gaiaagent.core.types import MessageDirection

router = MessageRouter()

# Register handler
async def handle_message(msg):
    print(f"Received: {msg.body.skill}")
    return {"status": "processed"}

router.register_handler("aurc:myproject/translator:v1.0", handle_message)

# Send message
msg = AURCMessage(
    source="aurc:myproject/orchestrator:v1.0",
    target="aurc:myproject/translator:v1.0",
    type=MessageDirection.REQUEST,
    body=MessageBody(method="invoke", skill="translate", params={"text": "Hello"}),
)
result = await router.route(msg)
```

## Next Steps

- Read the [full protocol specification](../../../PROTOCOL.md)
- Explore [examples](../../examples/)
- Build a [multi-agent workflow](multi-agent.md)
- Connect to [real MCP servers](mcp-integration.md)
- Deploy with [HTTP transport](http-deployment.md)
