"""Security module — Authentication, authorization, delegation, and audit."""

from gaiaagent.security.audit import (
    AuditAction,
    AuditEntry,
    AuditLog,
    AuditSeverity,
)
from gaiaagent.security.auth import (
    APIKeyAuthenticator,
    AuthError,
    AuthResult,
    JWTAuthenticator,
    MultiAuthenticator,
)
from gaiaagent.security.authz import (
    AgentPolicy,
    AuthorizationEngine,
    AuthorizationRule,
    AuthzResult,
    Constraint,
    DelegationPolicy,
)
from gaiaagent.security.delegation import (
    DelegationBuilder,
    DelegationResult,
    DelegationValidator,
    compute_chain_hash,
)
from gaiaagent.security.message_authz import (
    AuthzDeniedError,
    AuthzRequest,
    MessageAuthorizer,
    RouteAuthzGuard,
    derive_authz_request,
    extract_agent_id,
)

__all__ = [
    # Auth
    "APIKeyAuthenticator", "AuthError", "AuthResult",
    "JWTAuthenticator", "MultiAuthenticator",
    # AuthZ
    "AuthorizationEngine", "AuthorizationRule", "AgentPolicy",
    "AuthzResult", "Constraint", "DelegationPolicy",
    # Delegation
    "DelegationBuilder", "DelegationResult", "DelegationValidator",
    "compute_chain_hash",
    # Message authz (hot path)
    "AuthzDeniedError", "AuthzRequest", "MessageAuthorizer",
    "RouteAuthzGuard", "derive_authz_request", "extract_agent_id",
    # Audit
    "AuditAction", "AuditEntry", "AuditLog", "AuditSeverity",
]
