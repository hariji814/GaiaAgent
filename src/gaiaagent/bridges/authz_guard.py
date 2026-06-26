"""Bridge authorization guard — fail-closed enforcement at the protocol boundary.
桥接授权守卫 —— 在协议边界进行 fail-closed 强制

When an external message (A2A / ACP) is translated into an AURC invocation,
the bridge must not blindly forward it. :class:`BridgeAuthzGuard` wraps
`translate_to_aurc()` so that every inbound message is authorized against the
CapABAC :class:`AuthorizationEngine` before it reaches the orchestrator.

Design / 设计:
- Default deny: no policy => denied (fail-closed, never silently allow).
- The guard extracts agent_id (from message source), resource_type (skill),
  and action (method) from the translated AURCMessage.
- Authorization failures raise :class:`BridgeAuthzError` so callers cannot
  ignore them; the original translation is never returned on denial.
- An optional :class:`DelegationValidator` can be attached to enforce signed
  delegation chains for cross-protocol identity propagation (Phase 4.4).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from ..core.message import AURCMessage
from ..security.message_authz import derive_authz_request, extract_agent_id

if TYPE_CHECKING:
    from ..security.authz import AuthorizationEngine
    from ..security.delegation import DelegationValidator

logger = logging.getLogger(__name__)


class BridgeAuthzError(Exception):
    """Raised when an inbound bridged message is denied authorization.
    入站桥接消息被拒绝授权时抛出。"""

    def __init__(self, reason: str, aurc_message: AURCMessage | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.aurc_message = aurc_message


class BridgeAuthzGuard:
    """Authorize inbound bridged messages before they enter the AURC core.

    在入站桥接消息进入 AURC 核心前进行授权。

    Usage / 用法::

        guard = BridgeAuthzGuard(authz_engine)
        guarded_bridge = guard.wrap(a2a_bridge)
        aurc_msg = await guarded_bridge.translate_to_aurc(a2a_msg)  # may raise BridgeAuthzError

    The guard is opt-in: bridges without a guard retain their original
    (unauthenticated) behavior, so existing deployments are not broken.
    """

    def __init__(
        self,
        engine: AuthorizationEngine,
        delegation_validator: DelegationValidator | None = None,
    ) -> None:
        self._engine = engine
        self._validator = delegation_validator
        self._denied_count = 0
        self._allowed_count = 0

    @property
    def denied_count(self) -> int:
        return self._denied_count

    @property
    def allowed_count(self) -> int:
        return self._allowed_count

    def authorize_message(self, message: AURCMessage) -> None:
        """Authorize a single translated AURC message (fail-closed).

        对单条已翻译的 AURC 消息进行授权（fail-closed）。

        Raises:
            BridgeAuthzError: if the message is not explicitly allowed.
        """
        # Derive authorization inputs from the translated message.
        # / 从翻译后的消息推导授权输入。
        # Reuse the shared derivation so bridge and hot-path enforcement
        # stay consistent (see security.message_authz.derive_authz_request).
        req = derive_authz_request(message)
        agent_id = req.agent_id
        resource_type = req.resource_type
        action = req.action
        attributes = req.attributes

        # Validate delegation chain first (if a validator is attached).
        # / 若挂载了委托验证器，先验证委托链。
        if self._validator is not None and message.security.delegation_chain:
            chain_result = self._validator.validate(message.security)
            if not chain_result.valid:
                self._denied_count += 1
                logger.warning(
                    "Bridge authz DENIED (delegation): %s from=%s skill=%s",
                    chain_result.reason, agent_id, resource_type,
                )
                raise BridgeAuthzError(
                    f"Delegation rejected: {chain_result.reason}", message
                )

        result = self._engine.authorize(
            agent_id=agent_id,
            resource_type=resource_type,
            action=action,
            attributes=attributes,
        )
        if not result.allowed:
            self._denied_count += 1
            logger.warning(
                "Bridge authz DENIED: %s agent=%s skill=%s action=%s",
                result.reason, agent_id, resource_type, action,
            )
            raise BridgeAuthzError(result.reason, message)

        self._allowed_count += 1
        logger.info(
            "Bridge authz ALLOWED: agent=%s skill=%s action=%s",
            agent_id, resource_type, action,
        )

    def wrap(self, bridge: Any) -> _GuardedBridge:
        """Wrap a ProtocolBridge so translate_to_aurc is authorized.

        包装 ProtocolBridge，使 translate_to_aurc 经过授权。
        """
        return _GuardedBridge(self, bridge)

    @staticmethod
    def _extract_agent_id(message: AURCMessage) -> str:
        """Extract a stable agent_id from the message source.

        从消息来源提取稳定的 agent_id。

        Bridged messages use sources like 'a2a:external/<id>' or
        'acp:external/<id>'. We strip the 'external/' qualifier so the
        AuthorizationEngine sees the raw agent id.
        """
        return extract_agent_id(message)


class _GuardedBridge:
    """A ProtocolBridge decorator that enforces authz on translate_to_aurc.

    ProtocolBridge 装饰器，对 translate_to_aurc 强制授权。

    Only the inbound path (translate_to_aurc) is guarded; outbound
    translate_from_aurc and capability mapping pass through unchanged.
    """

    def __init__(self, guard: BridgeAuthzGuard, bridge: Any) -> None:
        self._guard = guard
        self._bridge = bridge

    @property
    def source_protocol(self) -> str:
        return cast(str, self._bridge.source_protocol)

    def can_bridge(self, source_protocol: str, target_protocol: str) -> bool:
        return cast(bool, self._bridge.can_bridge(source_protocol, target_protocol))

    async def translate_to_aurc(self, external_message: Any) -> AURCMessage:
        # Fail-closed: translate, then authorize before returning. If the
        # translation itself throws, the exception propagates (not swallowed).
        # / fail-closed：先翻译，再授权后才返回。翻译本身抛错则原样传播。
        aurc_message = cast(AURCMessage, await self._bridge.translate_to_aurc(external_message))
        self._guard.authorize_message(aurc_message)
        return aurc_message

    async def translate_from_aurc(self, aurc_message: AURCMessage) -> Any:
        return await self._bridge.translate_from_aurc(aurc_message)

    async def map_capabilities(self, capabilities: list[Any]) -> list[Any]:
        return cast(list[Any], await self._bridge.map_capabilities(capabilities))


__all__ = ["BridgeAuthzGuard", "BridgeAuthzError"]
