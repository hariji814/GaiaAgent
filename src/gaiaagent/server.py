"""
AURC Server - wires the HTTP transport to a real routing + lifecycle chain.

This is the "serve that doesn't lie" piece: instead of the CLI's echo handler,
AURCServer holds a RuntimeHarness + MessageRouter + a set of registered agent
instances whose @skill methods are invoked when a routed message targets them.
POST /aurc with an AURC message -> router.route() -> real agent skill -> real
result. The dashboard can be mounted alongside it.
"""
from __future__ import annotations

import logging
from typing import Any

from gaiaagent.bus.router import MessageRouter
from gaiaagent.core.identity import AgentDescriptor
from gaiaagent.core.message import AURCMessage
from gaiaagent.harness.lifecycle import RuntimeHarness
from gaiaagent.security.audit import AuditLog
from gaiaagent.security.authz import AuthorizationEngine
from gaiaagent.security.message_authz import (
    AuthzDeniedError,
    MessageAuthorizer,
    RouteAuthzGuard,
)

logger = logging.getLogger(__name__)


class AURCServer:
    """A runnable AURC node: harness + router + agents + HTTP handler.

    Usage::

        server = AURCServer()
        await server.register_agent(MyAgent())   # @aurc_agent decorated
        # POST /aurc {target: "aurc:ns/myagent:v1.0", body:{skill:"greet", ...}}
        server.http_handler  # pass to HTTPTransportServer.set_handler()
    """

    def __init__(
        self,
        harness: RuntimeHarness | None = None,
        router: MessageRouter | None = None,
        authz_engine: AuthorizationEngine | None = None,
        authorizer: MessageAuthorizer | None = None,
        audit_log: AuditLog | None = None,
    ) -> None:
        self.harness = harness or RuntimeHarness()
        self.router = router or MessageRouter()
        # agent_id -> agent instance (carries @skill methods + descriptor)
        self._agents: dict[str, Any] = {}
        # Wire a hot-path authorizer onto the router. An explicit authorizer
        # wins; otherwise an authz_engine is wrapped in a RouteAuthzGuard.
        # Leaving both None keeps the legacy unauthenticated behavior.
        if authorizer is not None:
            if isinstance(authorizer, RouteAuthzGuard):
                # Retroactively wire the shared audit log into a caller-
                # supplied guard without clobbering one it already owns.
                authorizer.attach_audit(audit_log)
            self.router.set_authorizer(authorizer)
        elif authz_engine is not None:
            self.router.set_authorizer(
                RouteAuthzGuard(authz_engine, audit=audit_log)
            )
        self.audit_log: AuditLog | None = audit_log

    async def register_agent(self, agent: Any) -> str:
        """Register a @aurc_agent-decorated instance with the server.

        Wires its skills as a router handler keyed by the agent's AURC ID, and
        registers the descriptor with the harness so lifecycle is tracked.
        """
        descriptor: AgentDescriptor = agent.aurc_descriptor
        agent_id = descriptor.aurc_id
        self._agents[agent_id] = agent

        await self.harness.register(descriptor)

        async def handler(msg: AURCMessage) -> dict[str, Any]:
            return await self._invoke_skill(agent, msg)

        self.router.register_handler(agent_id, handler)
        await self.harness.start(agent_id)
        logger.info("AURCServer: registered agent '%s'", agent_id)
        return agent_id

    async def _invoke_skill(self, agent: Any, msg: AURCMessage) -> dict[str, Any]:
        """Dispatch a routed message to the agent's @skill method."""
        skill_id = msg.body.skill or msg.body.method or ""
        # The @aurc_agent decorator indexes registered skills by id -> SkillMetadata.
        skills: dict[str, Any] = getattr(agent.__class__, "_aurc_skills", {})
        if skill_id not in skills:
            return {
                "error": {
                    "code": "skill_not_found",
                    "message": f"Agent has no skill '{skill_id}'",
                    "recoverable": False,
                }
            }
        # Resolve the bound method; skill_id matches the attribute name by convention.
        method = getattr(agent, skill_id, None)
        if method is None or not callable(method):
            return {
                "error": {
                    "code": "skill_not_found",
                    "message": f"Agent has no skill '{skill_id}'",
                    "recoverable": False,
                }
            }
        try:
            params = msg.body.params or {}
            result = await method(**params) if _is_async(method) else method(**params)
            return {"result": result}
        except TypeError as exc:
            # Signature mismatch (missing/extra kwargs) -> caller-visible error.
            return {
                "error": {
                    "code": "bad_skill_params",
                    "message": str(exc),
                    "recoverable": True,
                }
            }

    async def http_handler(self, request_data: dict[str, Any]) -> dict[str, Any]:
        """HTTPTransportServer handler: decode AURC message -> route -> result.

        Accepts either a raw AURC message dict or a wrapped envelope. Returns a
        JSON-serializable dict; on any failure returns an error envelope so the
        HTTP layer always produces a 200 with a structured body.
        """
        try:
            msg = AURCMessage.model_validate(request_data)
        except Exception as exc:
            return {"error": {"code": "bad_message", "message": str(exc)}}

        try:
            outcome = await self.router.route(msg)
        except AuthzDeniedError as exc:
            logger.info("Authorization denied for %s: %s", msg.message_id, exc.reason)
            return {"error": {"code": "forbidden", "message": exc.reason, "recoverable": False}}
        except Exception as exc:
            logger.exception("route failed for %s", msg.message_id)
            return {"error": {"code": "route_error", "message": str(exc)}}

        # Handlers return either a dict (already JSON-friendly) or an AURCMessage
        # (e.g. when routed to a BridgeConnector). Normalize both.
        if isinstance(outcome, AURCMessage):
            return outcome.model_dump(mode="json", exclude_none=True)
        if isinstance(outcome, dict):
            return outcome
        if outcome is None:
            return {"result": None, "routed": False}
        return {"result": outcome}


def _is_async(func: Any) -> bool:
    import inspect

    target = getattr(func, "__wrapped__", func)
    return inspect.iscoroutinefunction(target)
