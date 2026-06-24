# AURC Protocol Quick Start Guide
# AURC 协议快速入门指南

> Build your first AURC agent in 5 minutes / 5 分钟构建你的第一个 AURC Agent

## Prerequisites / 前提条件

- Python 3.10+
- `uv` or `pip` package manager

## Installation / 安装

```bash
pip install gaiaagent
# or / 或
uv add gaiaagent
```

## 1. Define Your Agent / 定义你的 Agent

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
        # Your translation logic here / 你的翻译逻辑
        return {
            "original": text,
            "translated": f"[{target_lang}] {text}",
            "confidence": 0.95,
        }

    @skill("detect-language", description="Detect the language of text")
    async def detect_language(self, text: str) -> dict:
        return {"detected_lang": "zh", "confidence": 0.88}
```

## 2. Start the Harness / 启动运行时

```python
import asyncio
from gaiaagent.harness.lifecycle import RuntimeHarness

async def run():
    harness = RuntimeHarness()

    # Create and register your agent / 创建并注册 Agent
    agent = TranslatorAgent()
    await harness.register(agent.aurc_descriptor)

    # Start a task / 启动任务
    await harness.start("aurc:myproject/translator:v1.0")

    # Check health / 检查健康
    health = await harness.health_check("aurc:myproject/translator:v1.0")
    print(f"Status: {health.status.value}")

asyncio.run(run())
```

## 3. Connect to MCP Servers / 连接 MCP 服务器

```python
from gaiaagent.bridges.base import MCPBridge

# Create MCP bridge / 创建 MCP 桥接器
mcp_bridge = MCPBridge()

# Translate MCP tool call to AURC / 将 MCP 工具调用翻译为 AURC
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

## 4. Add Security / 添加安全

```python
from gaiaagent.security.auth import APIKeyAuthenticator
from gaiaagent.security.authz import (
    AuthorizationEngine, AgentPolicy, AuthorizationRule, Constraint,
)

# Create API key / 创建 API Key
auth = APIKeyAuthenticator()
key = auth.create_key(
    "aurc:myproject/translator:v1.0",
    scopes=["translate", "detect"],
)
print(f"API Key: {key}")

# Set authorization policy / 设置授权策略
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

# Check authorization / 检查授权
result = engine.authorize(
    agent_id="aurc:myproject/translator:v1.0",
    resource_type="translation-api",
    action="execute",
    attributes={"text_length": 200},
)
print(f"Authorized: {result.allowed}")  # True
```

## 5. Route Messages / 路由消息

```python
from gaiaagent.bus.router import MessageRouter
from gaiaagent.core.message import AURCMessage, MessageBody
from gaiaagent.core.types import MessageDirection

router = MessageRouter()

# Register handler / 注册处理函数
async def handle_message(msg):
    print(f"Received: {msg.body.skill}")
    return {"status": "processed"}

router.register_handler("aurc:myproject/translator:v1.0", handle_message)

# Send message / 发送消息
msg = AURCMessage(
    source="aurc:myproject/orchestrator:v1.0",
    target="aurc:myproject/translator:v1.0",
    type=MessageDirection.REQUEST,
    body=MessageBody(method="invoke", skill="translate", params={"text": "Hello"}),
)
result = await router.route(msg)
```

## Next Steps / 后续步骤

- Read the [full protocol specification](../PROTOCOL.md) / 阅读完整协议规范
- Explore [examples](../examples/) / 探索示例
- Build a [multi-agent workflow](multi-agent.md) / 构建多 Agent 工作流
- Connect to [real MCP servers](mcp-integration.md) / 连接真实 MCP 服务器
- Deploy with [HTTP transport](http-deployment.md) / 使用 HTTP 传输部署
