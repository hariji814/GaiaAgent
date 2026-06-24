"""Security module — Authentication, authorization, delegation, and audit."""

from gaiaagent.security.auth import (
    APIKeyAuthenticator,
    AuthError,
    AuthResult,
    JWTAuthenticator,
    MultiAuthenticator,
)
from gaiaagent.security.authz import (
    AuthorizationEngine,
    AuthorizationRule,
    AgentPolicy,
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
from gaiaagent.security.audit import (
    AuditAction,
    AuditEntry,
    AuditLog,
    AuditSeverity,
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
    # Audit
    "AuditAction", "AuditEntry", "AuditLog", "AuditSeverity",
]
