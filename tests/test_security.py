"""Tests for AURC Security — Auth, CapABAC, Delegation, Audit."""


import pytest

from gaiaagent.core.message import DelegationHop, MessageSecurity
from gaiaagent.security.audit import AuditAction, AuditLog, AuditSeverity
from gaiaagent.security.auth import (
    APIKeyAuthenticator,
    JWTAuthenticator,
    MultiAuthenticator,
)
from gaiaagent.security.authz import (
    AgentPolicy,
    AuthorizationEngine,
    AuthorizationRule,
    Constraint,
)
from gaiaagent.security.delegation import (
    DelegationBuilder,
    DelegationValidator,
    compute_chain_hash,
)

# =============================================================================
# Authentication Tests / 认证测试
# =============================================================================


class TestAPIKeyAuth:
    def test_create_and_authenticate(self):
        auth = APIKeyAuthenticator()
        key = auth.create_key("aurc:gaia/test:v1.0", scopes=["read", "write"])
        result = auth.authenticate(key)
        assert result.authenticated is True
        assert result.agent_id == "aurc:gaia/test:v1.0"
        assert result.scopes == ["read", "write"]

    def test_invalid_key(self):
        auth = APIKeyAuthenticator()
        result = auth.authenticate("invalid_key_12345")
        assert result.authenticated is False

    def test_revoke_key(self):
        auth = APIKeyAuthenticator()
        key = auth.create_key("aurc:gaia/test:v1.0")
        assert auth.revoke_key(key) is True
        result = auth.authenticate(key)
        assert result.authenticated is False

    def test_revoke_agent_keys(self):
        auth = APIKeyAuthenticator()
        auth.create_key("aurc:gaia/test:v1.0")
        auth.create_key("aurc:gaia/test:v1.0")
        assert auth.key_count == 2
        count = auth.revoke_agent_keys("aurc:gaia/test:v1.0")
        assert count == 2
        assert auth.key_count == 0


class TestJWTAuth:
    def test_create_and_authenticate(self):
        auth = JWTAuthenticator(secret="test-secret")
        token = auth.create_token("aurc:gaia/test:v1.0", scopes=["read"])
        result = auth.authenticate(token)
        assert result.authenticated is True
        assert result.agent_id == "aurc:gaia/test:v1.0"
        assert result.scopes == ["read"]

    def test_expired_token(self):
        auth = JWTAuthenticator(secret="test-secret")
        token = auth.create_token("aurc:gaia/test:v1.0", expires_in_seconds=-1)
        result = auth.authenticate(token)
        assert result.authenticated is False
        assert "expired" in result.error.lower()

    def test_invalid_signature(self):
        auth_a = JWTAuthenticator(secret="secret-a")
        auth_b = JWTAuthenticator(secret="secret-b")
        token = auth_a.create_token("aurc:gaia/test:v1.0")
        result = auth_b.authenticate(token)
        assert result.authenticated is False

    def test_malformed_token(self):
        auth = JWTAuthenticator()
        result = auth.authenticate("not.a.valid.token")
        assert result.authenticated is False


class TestMultiAuth:
    def test_api_key_via_multi(self):
        multi = MultiAuthenticator()
        api = multi.add_api_key()
        key = api.create_key("aurc:gaia/test:v1.0", scopes=["read"])
        result = multi.authenticate("api_key", key)
        assert result.authenticated is True

    def test_jwt_via_multi(self):
        multi = MultiAuthenticator()
        jwt = multi.add_jwt(secret="test")
        token = jwt.create_token("aurc:gaia/test:v1.0")
        result = multi.authenticate("jwt", token)
        assert result.authenticated is True

    def test_unknown_method(self):
        multi = MultiAuthenticator()
        result = multi.authenticate("unknown", "credential")
        assert result.authenticated is False

    def test_authenticate_any(self):
        multi = MultiAuthenticator()
        api = multi.add_api_key()
        key = api.create_key("aurc:gaia/test:v1.0")
        result = multi.authenticate_any({
            "jwt": "bad-token",
            "api_key": key,
        })
        assert result.authenticated is True


# =============================================================================
# Authorization Tests / 授权测试
# =============================================================================


class TestCapABAC:
    @pytest.fixture
    def engine(self):
        eng = AuthorizationEngine()
        eng.set_policy("aurc:gaia/test:v1.0", AgentPolicy(
            agent_id="aurc:gaia/test:v1.0",
            rules=[
                AuthorizationRule(
                    resource_type="web-search",
                    actions=["execute"],
                    constraints=[
                        Constraint("domain", "matches", r".*\.(edu|gov)$"),
                    ],
                    rate_limit=100,
                ),
                AuthorizationRule(
                    resource_type="database",
                    actions=["read", "write"],
                    constraints=[
                        Constraint("sensitivity", "in", ["public", "internal"]),
                    ],
                ),
                AuthorizationRule(
                    resource_type="*",
                    actions=["health_check"],
                    constraints=[],
                ),
            ],
        ))
        return eng

    def test_allowed_with_constraint(self, engine):
        result = engine.authorize(
            "aurc:gaia/test:v1.0", "web-search", "execute",
            attributes={"domain": "mit.edu"},
        )
        assert result.allowed is True

    def test_denied_constraint_mismatch(self, engine):
        result = engine.authorize(
            "aurc:gaia/test:v1.0", "web-search", "execute",
            attributes={"domain": "evil.com"},
        )
        assert result.allowed is False

    def test_denied_no_policy(self, engine):
        result = engine.authorize("aurc:gaia/unknown:v1.0", "web-search", "execute")
        assert result.allowed is False

    def test_wildcard_resource(self, engine):
        result = engine.authorize("aurc:gaia/test:v1.0", "anything", "health_check")
        assert result.allowed is True

    def test_constraint_operators(self):
        assert Constraint("x", "eq", 5).evaluate(5) is True
        assert Constraint("x", "ne", 5).evaluate(3) is True
        assert Constraint("x", "gt", 5).evaluate(6) is True
        assert Constraint("x", "lt", 5).evaluate(4) is True
        assert Constraint("x", "gte", 5).evaluate(5) is True
        assert Constraint("x", "lte", 5).evaluate(5) is True
        assert Constraint("x", "in", [1, 2, 3]).evaluate(2) is True
        assert Constraint("x", "not_in", [1, 2]).evaluate(3) is True
        assert Constraint("x", "contains", "hello world").evaluate("hello") is False

    def test_scope_authorization(self, engine):
        result = engine.authorize_scopes(
            "aurc:gaia/test:v1.0", "database", "read",
            required_scopes=["db:read"],
            granted_scopes=["db:read", "db:write"],
            attributes={"sensitivity": "public"},
        )
        assert result.allowed is True

    def test_scope_authorization_missing(self, engine):
        result = engine.authorize_scopes(
            "aurc:gaia/test:v1.0", "database", "read",
            required_scopes=["db:admin"],
            granted_scopes=["db:read"],
            attributes={"sensitivity": "public"},
        )
        assert result.allowed is False


# =============================================================================
# Delegation Tests / 委托链测试
# =============================================================================


class TestDelegationValidator:
    @pytest.fixture
    def validator(self):
        return DelegationValidator(max_depth=3)

    def test_valid_chain(self, validator):
        chain = [
            DelegationHop(
                from_agent="user/alice", to_agent="orch",
                scopes=["read", "write", "admin"],
            ),
            DelegationHop(from_agent="orch", to_agent="researcher", scopes=["read", "write"]),
            DelegationHop(from_agent="researcher", to_agent="web-search", scopes=["read"]),
        ]
        security = MessageSecurity(delegation_chain=chain)
        result = validator.validate(security)
        assert result.valid is True
        assert result.depth == 3

    def test_empty_chain(self, validator):
        security = MessageSecurity(delegation_chain=[])
        result = validator.validate(security)
        assert result.valid is True

    def test_scope_widening_rejected(self, validator):
        chain = [
            DelegationHop(from_agent="user/alice", to_agent="orch", scopes=["read"]),
            DelegationHop(
                from_agent="orch", to_agent="researcher",
                scopes=["read", "write"],  # Widened!
            ),
        ]
        security = MessageSecurity(delegation_chain=chain)
        result = validator.validate(security)
        assert result.valid is False
        assert result.failed_hop == 1

    def test_depth_exceeded(self, validator):
        chain = [
            DelegationHop(from_agent=f"a{i}", to_agent=f"a{i+1}", scopes=["read"])
            for i in range(5)  # 5 hops > max_depth=3
        ]
        security = MessageSecurity(delegation_chain=chain)
        result = validator.validate(security)
        assert result.valid is False

    def test_effective_scopes(self, validator):
        chain = [
            DelegationHop(from_agent="user", to_agent="orch", scopes=["read", "write", "admin"]),
            DelegationHop(from_agent="orch", to_agent="researcher", scopes=["read"]),
        ]
        security = MessageSecurity(delegation_chain=chain)
        result = validator.validate(security)
        assert result.valid is True
        assert result.effective_scopes == ["read"]

    def test_validate_effective_scopes_sufficient(self, validator):
        chain = [
            DelegationHop(from_agent="user", to_agent="orch", scopes=["read", "write"]),
            DelegationHop(from_agent="orch", to_agent="agent", scopes=["read"]),
        ]
        security = MessageSecurity(delegation_chain=chain)
        result = validator.validate_effective_scopes(security, ["read"])
        assert result.valid is True

    def test_validate_effective_scopes_insufficient(self, validator):
        chain = [
            DelegationHop(from_agent="user", to_agent="orch", scopes=["read", "write"]),
            DelegationHop(from_agent="orch", to_agent="agent", scopes=["read"]),
        ]
        security = MessageSecurity(delegation_chain=chain)
        result = validator.validate_effective_scopes(security, ["write"])
        assert result.valid is False


class TestDelegationBuilder:
    def test_build_valid_chain(self):
        builder = DelegationBuilder()
        builder.add_hop("user", "orch", ["read", "write", "admin"])
        builder.add_hop("orch", "researcher", ["read", "write"])
        builder.add_hop("researcher", "tool", ["read"])
        chain = builder.build()
        assert len(chain) == 3
        assert builder.depth == 3
        assert builder.effective_scopes == ["read"]

    def test_reject_widening(self):
        builder = DelegationBuilder()
        builder.add_hop("user", "orch", ["read"])
        with pytest.raises(ValueError, match="Cannot widen"):
            builder.add_hop("orch", "agent", ["read", "write"])

    def test_reject_broken_chain(self):
        builder = DelegationBuilder()
        builder.add_hop("user", "orch", ["read"])
        with pytest.raises(ValueError, match="Chain broken"):
            builder.add_hop("wrong_agent", "tool", ["read"])

    def test_chain_hash(self):
        chain = [
            DelegationHop(from_agent="user", to_agent="orch", scopes=["read"]),
        ]
        hash1 = compute_chain_hash(chain)
        hash2 = compute_chain_hash(chain)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex digest


# =============================================================================
# Audit Log Tests / 审计日志测试
# =============================================================================


class TestAuditLog:
    @pytest.fixture
    def audit(self):
        return AuditLog(max_entries=100)

    def test_log_entry(self, audit):
        entry = audit.log(AuditAction.AGENT_REGISTERED, agent_id="aurc:test:v1.0")
        assert entry.action == AuditAction.AGENT_REGISTERED
        assert audit.count == 1

    def test_query_by_action(self, audit):
        audit.log(AuditAction.AGENT_REGISTERED, agent_id="a1")
        audit.log(AuditAction.MESSAGE_SENT, agent_id="a1")
        audit.log(AuditAction.AGENT_REGISTERED, agent_id="a2")

        results = audit.query(action=AuditAction.AGENT_REGISTERED)
        assert len(results) == 2

    def test_query_by_agent(self, audit):
        audit.log(AuditAction.AGENT_REGISTERED, agent_id="a1")
        audit.log(AuditAction.MESSAGE_SENT, agent_id="a1")
        audit.log(AuditAction.AGENT_REGISTERED, agent_id="a2")

        results = audit.query(agent_id="a1")
        assert len(results) == 2

    def test_query_by_severity(self, audit):
        audit.log(AuditAction.AUTHZ_DENIED, severity=AuditSeverity.WARNING)
        audit.log(AuditAction.AUTHZ_GRANTED, severity=AuditSeverity.INFO)
        results = audit.query(severity=AuditSeverity.WARNING)
        assert len(results) == 1

    def test_correlation_query(self, audit):
        audit.log(AuditAction.MESSAGE_SENT, correlation_id="corr-123")
        audit.log(AuditAction.MESSAGE_RECEIVED, correlation_id="corr-123")
        audit.log(AuditAction.MESSAGE_SENT, correlation_id="corr-456")

        results = audit.get_by_correlation("corr-123")
        assert len(results) == 2

    def test_stats(self, audit):
        audit.log(AuditAction.AGENT_REGISTERED)
        audit.log(AuditAction.AGENT_REGISTERED)
        audit.log(AuditAction.MESSAGE_SENT)
        stats = audit.stats()
        assert stats["agent_registered"] == 2
        assert stats["message_sent"] == 1

    def test_get_recent(self, audit):
        for i in range(10):
            audit.log(AuditAction.MESSAGE_SENT, details={"index": i})
        recent = audit.get_recent(3)
        assert len(recent) == 3

    def test_max_entries(self):
        audit = AuditLog(max_entries=5)
        for i in range(10):
            audit.log(AuditAction.MESSAGE_SENT)
        assert audit.count == 5  # Ring buffer evicts oldest

    def test_clear(self, audit):
        audit.log(AuditAction.AGENT_REGISTERED)
        audit.log(AuditAction.MESSAGE_SENT)
        cleared = audit.clear()
        assert cleared == 2
        assert audit.count == 0

    def test_entry_serialization(self):
        _ = AuditAction.AGENT_REGISTERED  # ensure import is used
        from gaiaagent.security.audit import AuditEntry
        e = AuditEntry(action=AuditAction.AGENT_REGISTERED, agent_id="test")
        d = e.to_dict()
        assert d["action"] == "agent_registered"
        assert d["agent_id"] == "test"

        restored = AuditEntry.from_dict(d)
        assert restored.action == AuditAction.AGENT_REGISTERED
        assert restored.agent_id == "test"
