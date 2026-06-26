"""Shared message authorization helpers for the AURC hot path.

Both the bridge inbound guard (BridgeAuthzGuard) and the router hot-path
guard (RouteAuthzGuard) derive the same authorization request from an
AURCMessage. Centralizing that derivation here keeps the two enforcement
points consistent and removes duplicated extraction logic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from ..core.message import AURCMessage
from .audit import AuditAction, AuditLog, AuditSeverity

if TYPE_CHECKING:
    from .authz import AuthorizationEngine
    from .delegation import DelegationValidator

logger = logging.getLogger(__name__)


class AuthzDeniedError(Exception):
    """Raised when a message is denied authorization on the routing hot path.

    Carries the agent_id and resource so callers (e.g. AURCServer) can map
    the denial to a structured error envelope without re-parsing the reason.
    """

    def __init__(
        self,
        reason: str,
        *,
        agent_id: str = "",
        resource: str = "",
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.agent_id = agent_id
        self.resource = resource


@dataclass
class AuthzRequest:
    """Inputs derived from a message for an authorization decision."""

    agent_id: str
    resource_type: str
    action: str
    attributes: dict[str, Any]


def extract_agent_id(message: AURCMessage) -> str:
    """Extract a stable agent_id from the message source.

    Bridged messages use sources like 'a2a:external/<id>' or
    'acp:external/<id>'. The 'external/' qualifier is stripped so the
    AuthorizationEngine sees the raw agent id. Unqualified sources are
    used verbatim.
    """
    source = message.source or "unknown"
    if "external/" in source:
        return source.split("external/", 1)[1]
    return source


def derive_authz_request(message: AURCMessage) -> AuthzRequest:
    """Derive a stable authorization request from an AURC message.

    - agent_id: from the message source (external/ qualifier stripped)
    - resource_type: the skill id, falling back to the method name
    - action: the method name, falling back to 'invoke'
    - attributes: message params plus source/target/message_type for
      constraint evaluation
    """
    attributes: dict[str, Any] = dict(message.body.params)
    attributes["source"] = message.source
    attributes["target"] = message.target
    attributes["message_type"] = (
        message.type.value if message.type else "unknown"
    )
    return AuthzRequest(
        agent_id=extract_agent_id(message),
        resource_type=message.body.skill or message.body.method or "unknown",
        action=message.body.method or "invoke",
        attributes=attributes,
    )


@runtime_checkable
class MessageAuthorizer(Protocol):
    """Authorize a single AURC message on the routing hot path.

    Implementations must be fail-closed: authorize_message() returns None on
    success and raises AuthzDeniedError when the message is not explicitly
    allowed.
    """

    def authorize_message(self, message: AURCMessage) -> None:
        """Authorize the message; raise AuthzDeniedError if denied."""
        ...


class RouteAuthzGuard:
    """Hot-path authorizer backed by the CapABAC AuthorizationEngine.

    Applied by MessageRouter when an authorizer is attached. Fail-closed:
    no policy => denied (the AuthorizationEngine is itself default-deny).
    An optional DelegationValidator enforces signed delegation chains for
    cross-protocol identity propagation before the authz decision.

    This is the router-side counterpart to BridgeAuthzGuard; both reuse
    derive_authz_request so inbound-bridge and hot-path enforcement stay
    consistent.

    Auditability: when an ``AuditLog`` is attached (directly or via
    :meth:`attach_audit`), every decision is recorded -- denials as
    ``AUTHZ_DENIED`` (WARNING), grants as ``AUTHZ_GRANTED`` (INFO). Grant
    logging can be disabled with ``log_grants=False`` for high-throughput
    hot paths where only denials are needed. Because
    ``PrometheusMetricsExporter`` renders ``aurc_audit_events_total{action=...}``
    from the audit log action stats, attaching a shared audit log makes
    authz decisions observable with no extra wiring.
    """

    def __init__(
        self,
        engine: AuthorizationEngine,
        delegation_validator: DelegationValidator | None = None,
        audit: AuditLog | None = None,
        *,
        log_grants: bool = True,
    ) -> None:
        self._engine = engine
        self._validator = delegation_validator
        self._audit: AuditLog | None = audit
        self._log_grants = log_grants
        self._denied_count = 0
        self._allowed_count = 0

    @property
    def denied_count(self) -> int:
        return self._denied_count

    @property
    def allowed_count(self) -> int:
        return self._allowed_count

    def attach_audit(self, audit: AuditLog | None) -> None:
        """Attach an audit log if one is not already set.

        No-op when ``audit`` is None or an audit log is already attached.
        Lets a host (e.g. ``AURCServer``) retroactively wire its shared
        audit log into an authorizer it did not construct itself, without
        clobbering a caller-provided sink.
        """
        if audit is not None and self._audit is None:
            self._audit = audit

    def authorize_message(self, message: AURCMessage) -> None:
        """Authorize a message on the hot path (fail-closed).

        Raises:
            AuthzDeniedError: if the message is not explicitly allowed, or
                if an attached DelegationValidator rejects the chain.
        """
        req = derive_authz_request(message)

        # Validate delegation chain first (if a validator is attached).
        if self._validator is not None and message.security.delegation_chain:
            chain_result = self._validator.validate(message.security)
            if not chain_result.valid:
                self._denied_count += 1
                logger.warning(
                    "Route authz DENIED (delegation): %s from=%s skill=%s",
                    chain_result.reason, req.agent_id, req.resource_type,
                )
                self._record_audit(
                    message=message,
                    req=req,
                    action=AuditAction.AUTHZ_DENIED,
                    severity=AuditSeverity.WARNING,
                    reason=f"Delegation rejected: {chain_result.reason}",
                )
                raise AuthzDeniedError(
                    f"Delegation rejected: {chain_result.reason}",
                    agent_id=req.agent_id,
                    resource=req.resource_type,
                )

        result = self._engine.authorize(
            agent_id=req.agent_id,
            resource_type=req.resource_type,
            action=req.action,
            attributes=req.attributes,
        )
        if not result.allowed:
            self._denied_count += 1
            logger.warning(
                "Route authz DENIED: %s agent=%s skill=%s action=%s",
                result.reason, req.agent_id, req.resource_type, req.action,
            )
            self._record_audit(
                message=message,
                req=req,
                action=AuditAction.AUTHZ_DENIED,
                severity=AuditSeverity.WARNING,
                reason=result.reason,
            )
            raise AuthzDeniedError(
                result.reason,
                agent_id=req.agent_id,
                resource=req.resource_type,
            )

        self._allowed_count += 1
        logger.debug(
            "Route authz ALLOWED: agent=%s skill=%s action=%s",
            req.agent_id, req.resource_type, req.action,
        )
        if self._log_grants:
            self._record_audit(
                message=message,
                req=req,
                action=AuditAction.AUTHZ_GRANTED,
                severity=AuditSeverity.INFO,
                reason=result.reason,
            )

    def _record_audit(
        self,
        *,
        message: AURCMessage,
        req: AuthzRequest,
        action: AuditAction,
        severity: AuditSeverity,
        reason: str,
    ) -> None:
        """Write a single authz decision to the attached audit log (if any)."""
        if self._audit is None:
            return
        self._audit.log(
            action=action,
            agent_id=req.agent_id,
            target_id=message.target,
            message_id=message.message_id,
            correlation_id=message.correlation_id or "",
            severity=severity,
            details={
                "resource": req.resource_type,
                "requested_action": req.action,
                "reason": reason,
            },
        )


__all__ = [
    "AuthzDeniedError",
    "AuthzRequest",
    "MessageAuthorizer",
    "RouteAuthzGuard",
    "derive_authz_request",
    "extract_agent_id",
]
