"""AURC Message Router — routes messages between agents.
AURC 消息路由器 — 在 Agent 之间路由消息

Responsibilities / 职责:
1. Direct routing: source and target in same Harness / 直连路由
2. Registry routing: look up target via Registry / 注册表路由
3. Bridge routing: target is external protocol agent / 桥接路由
4. Broadcast routing: multicast to subscribers / 广播路由
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Any

from ..core.message import AURCMessage
from ..security.message_authz import AuthzDeniedError, MessageAuthorizer

logger = logging.getLogger(__name__)

# Type aliases / 类型别名
MessageHandler = Callable[[AURCMessage], Awaitable[Any]]
"""Async callback: (message) -> result"""


class RoutingError(Exception):
    """Raised when a message cannot be routed. 消息无法路由时抛出"""
    pass


class MessageRouter:
    """Central message router for the AURC message bus.
    AURC 消息总线的中央路由器

    Routing priority (highest to lowest) / 路由优先级（从高到低）:
    1. Direct: both agents registered locally / 直连：两个 Agent 都在本地
    2. Registry: target found in registry / 注册表：在注册中心找到目标
    3. Bridge: target is on external protocol / 桥接：目标在外部协议
    4. Broadcast: target is a group address / 广播：目标是组播地址

    Usage / 用法:
        router = MessageRouter()

        # Register a handler for an agent / 注册 Agent 的处理函数
        router.register_handler("aurc:gaia/researcher:v1.0", handle_message)

        # Route a message / 路由消息
        await router.route(message)

        # Subscribe to broadcast groups / 订阅广播组
        router.subscribe("aurc:group/researchers", handle_message)
    """

    def __init__(self) -> None:
        # Agent handlers: agent_id → handler function / Agent 处理函数映射
        self._handlers: dict[str, MessageHandler] = {}

        # Bridge forwarders: protocol → forward function / 桥接转发函数映射
        self._bridge_forwarders: dict[str, MessageHandler] = {}

        # Group subscriptions: group_id → set of handlers / 组播订阅映射
        self._subscriptions: dict[str, list[MessageHandler]] = defaultdict(list)

        # Message queue for undeliverable messages / 不可投递消息队列
        self._dead_letter_queue: deque[AURCMessage] = deque()
        self._max_dead_letters = 100

        # Statistics / 统计
        self._stats = RouterStats()

        # Optional hot-path authorizer. When None, routing behaves exactly
        # like the unauthenticated path (backward compatible).
        self._authorizer: MessageAuthorizer | None = None

    # =========================================================================
    # Handler Registration / 处理函数注册
    # =========================================================================

    def register_handler(self, agent_id: str, handler: MessageHandler) -> None:
        """Register a message handler for an agent.
        为 Agent 注册消息处理函数

        Args:
            agent_id: The agent's AURC ID / Agent 的 AURC ID
            handler: Async function to handle incoming messages / 处理入站消息的异步函数
        """
        if agent_id in self._handlers:
            logger.warning("Replacing handler for agent: %s", agent_id)
        self._handlers[agent_id] = handler
        logger.info("Router: registered handler for '%s'", agent_id)

    def unregister_handler(self, agent_id: str) -> None:
        """Remove a message handler. 移除消息处理函数"""
        self._handlers.pop(agent_id, None)

    def register_bridge_forwarder(self, protocol: str, forwarder: MessageHandler) -> None:
        """Register a forwarder for bridged messages.
        注册桥接消息转发函数

        Args:
            protocol: External protocol identifier / 外部协议标识
            forwarder: Async function to forward messages to external protocol
                / 转发到外部协议的异步函数
        """
        self._bridge_forwarders[protocol] = forwarder
        logger.info("Router: registered bridge forwarder for '%s'", protocol)

    def set_authorizer(self, authorizer: MessageAuthorizer) -> None:
        """Attach a hot-path authorizer. When set, every routed message is
        authorized (fail-closed) before dispatch. Attaching twice replaces
        the previous authorizer.
        """
        self._authorizer = authorizer
        logger.info("Router: hot-path authorizer attached")

    # =========================================================================
    # Subscriptions / 订阅
    # =========================================================================

    def subscribe(self, group_id: str, handler: MessageHandler) -> None:
        """Subscribe to a broadcast group. 订阅广播组

        Args:
            group_id: Group identifier (e.g., "aurc:group/researchers") / 组标识
            handler: Handler called for each group message / 组消息处理函数
        """
        self._subscriptions[group_id].append(handler)

    def unsubscribe(self, group_id: str, handler: MessageHandler) -> None:
        """Unsubscribe from a broadcast group. 取消订阅广播组"""
        handlers = self._subscriptions.get(group_id, [])
        if handler in handlers:
            handlers.remove(handler)

    # =========================================================================
    # Routing / 路由
    # =========================================================================

    async def route(self, message: AURCMessage) -> Any:
        """Route a message to its target.
        将消息路由到目标

        Applies routing priority:
        1. Check TTL / 检查 TTL
        2. Direct routing (local handler) / 直连路由
        3. Bridge routing (external protocol) / 桥接路由
        4. Group routing (broadcast) / 组播路由
        5. Dead letter queue / 死信队列

        Returns:
            Handler result, or None if routed to group/dead letter
        """
        # TTL check / TTL 检查
        if message.routing.ttl_hops <= 0:
            logger.warning("Message '%s' TTL expired, dropping", message.message_id)
            self._stats.dropped += 1
            return None
        # Decrement TTL for this hop / 递减 TTL
        message.routing.ttl_hops -= 1

        target = message.target
        self._stats.total_routed += 1

        # Authorization (hot-path guard). When an authorizer is attached,
        # every routed message is authorized before dispatch (fail-closed).
        # No authorizer => identical behavior to the unauthenticated path.
        if self._authorizer is not None:
            try:
                self._authorizer.authorize_message(message)
            except AuthzDeniedError:
                self._stats.denied += 1
                logger.warning(
                    "Authorization denied for message '%s': %s -> %s",
                    message.message_id, message.source, message.target,
                )
                raise

        # 1. Direct routing / 直连路由
        if target in self._handlers:
            self._stats.direct += 1
            logger.debug(
                "Direct route: %s → %s (msg: %s)",
                message.source, target, message.message_id,
            )
            try:
                return await self._handlers[target](message)
            except Exception:
                logger.exception("Handler error for agent '%s'", target)
                self._stats.errors += 1
                raise

        # 2. Bridge routing / 桥接路由
        if target.startswith(("mcp:", "a2a:", "acp:")):
            protocol_prefix = target.split(":")[0]
            forwarder = self._bridge_forwarders.get(protocol_prefix)
            if forwarder:
                self._stats.bridged += 1
                logger.debug(
                    "Bridge route: %s → %s via %s (msg: %s)",
                    message.source, target, protocol_prefix, message.message_id,
                )
                return await forwarder(message)

        # 3. Group/broadcast routing / 组播路由
        if target.startswith("aurc:group/"):
            self._stats.broadcast += 1
            handlers = self._subscriptions.get(target, [])
            logger.debug(
                "Broadcast route: %s → %s (%d subscribers)",
                message.source, target, len(handlers),
            )
            coros = [handler(message) for handler in handlers]
            gathered = await asyncio.gather(*coros, return_exceptions=True)
            results = []
            for item in gathered:
                if isinstance(item, Exception):
                    logger.exception(
                        "Broadcast handler error in group '%s': %s", target, item
                    )
                    self._stats.errors += 1
                else:
                    results.append(item)
            return results

        # 4. Wildcard routing / 通配符路由
        # Check if any registered handler matches with a wildcard / 检查通配符匹配
        for pattern, handler in self._handlers.items():
            if "*" in pattern and self._wildcard_match(pattern, target):
                self._stats.direct += 1
                return await handler(message)

        # 5. Dead letter queue / 死信队列
        logger.warning(
            "No route for message '%s': %s → %s",
            message.message_id, message.source, target,
        )
        self._dead_letter_queue.append(message)
        self._stats.dead_lettered += 1
        if len(self._dead_letter_queue) > self._max_dead_letters:
            self._dead_letter_queue.popleft()
        return None

    # =========================================================================
    # Queries / 查询
    # =========================================================================

    def has_handler(self, agent_id: str) -> bool:
        """Check if an agent has a registered handler."""
        return agent_id in self._handlers

    @property
    def handler_count(self) -> int:
        return len(self._handlers)

    @property
    def stats(self) -> RouterStats:
        return self._stats

    @property
    def dead_letter_queue(self) -> list[AURCMessage]:
        """Get undeliverable messages. 获取不可投递的消息"""
        return list(self._dead_letter_queue)

    def clear_dead_letters(self) -> int:
        """Clear the dead letter queue. Returns count cleared."""
        count = len(self._dead_letter_queue)
        self._dead_letter_queue.clear()
        return count

    # =========================================================================
    # Internal / 内部方法
    # =========================================================================

    @staticmethod
    def _wildcard_match(pattern: str, target: str) -> bool:
        """Simple wildcard matching for routing patterns.
        简单的通配符匹配

        Supports '*' as wildcard within a segment.
        """
        pattern_parts = pattern.split("/")
        target_parts = target.split("/")

        if len(pattern_parts) != len(target_parts):
            return False

        for p, t in zip(pattern_parts, target_parts):
            if p == "*":
                continue
            if p != t:
                return False
        return True


class RouterStats:
    """Router statistics tracker. 路由器统计追踪器"""

    def __init__(self) -> None:
        self.total_routed: int = 0
        self.direct: int = 0
        self.bridged: int = 0
        self.broadcast: int = 0
        self.dead_lettered: int = 0
        self.dropped: int = 0
        self.errors: int = 0
        self.denied: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "total_routed": self.total_routed,
            "direct": self.direct,
            "bridged": self.bridged,
            "broadcast": self.broadcast,
            "dead_lettered": self.dead_lettered,
            "dropped": self.dropped,
            "errors": self.errors,
            "denied": self.denied,
        }

    def reset(self) -> None:
        self.total_routed = 0
        self.direct = 0
        self.bridged = 0
        self.broadcast = 0
        self.dead_lettered = 0
        self.dropped = 0
        self.errors = 0
        self.denied = 0
