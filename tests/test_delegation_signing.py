"""Phase 4.4 tests: Ed25519 delegation signatures + validator integration.

These tests require the optional `cryptography` package (gaiaagent[security]).
When it is not installed, the Ed25519 tests are skipped; the graceful-
degradation behavior (SigningUnavailableError) is always exercised.
"""
from __future__ import annotations

import pytest

from gaiaagent.core.message import DelegationHop, MessageSecurity
from gaiaagent.security.delegation import DelegationValidator
from gaiaagent.security.signing import (
    InvalidSignatureError,
    SigningUnavailableError,
    generate_keypair,
    sign_delegation_hop,
    verify_delegation_hop,
)

# ---------------------------------------------------------------------------
# Graceful degradation (always runs, no cryptography needed)
# ---------------------------------------------------------------------------


def test_signing_unavailable_when_no_cryptography() -> None:
    """If cryptography is absent, signing raises a clear error, not a crash."""
    try:
        import cryptography  # noqa: F401
        pytest.skip("cryptography is installed; degradation path not exercised")
    except ImportError:
        pass

    hop = DelegationHop(from_agent="a", to_agent="b", scopes=["s"])
    with pytest.raises(SigningUnavailableError):
        generate_keypair()
    with pytest.raises(SigningUnavailableError):
        sign_delegation_hop(hop, b"0" * 32, "k1")
    with pytest.raises(SigningUnavailableError):
        verify_delegation_hop(hop, b"0" * 32)


# ---------------------------------------------------------------------------
# Real Ed25519 (requires cryptography)
# ---------------------------------------------------------------------------

def _require_cryptography():
    """Skip helper: real Ed25519 needs the cryptography package."""
    pytest.importorskip("cryptography")


def _make_hop(
    from_agent: str = "aurc:user/alice",
    to_agent: str = "aurc:gaia/orchestrator",
) -> DelegationHop:
    return DelegationHop(
        from_agent=from_agent,
        to_agent=to_agent,
        scopes=["research:read", "web:search"],
    )


def test_sign_and_verify_roundtrip() -> None:
    _require_cryptography()
    priv, pub = generate_keypair()
    hop = _make_hop()
    sign_delegation_hop(hop, priv, "key-1")
    assert hop.signature
    assert hop.signing_key_id == "key-1"
    # Must not raise
    verify_delegation_hop(hop, pub)


def test_verify_rejects_tampered_hop() -> None:
    _require_cryptography()
    priv, pub = generate_keypair()
    hop = _make_hop()
    sign_delegation_hop(hop, priv, "key-1")
    # Tamper with scopes after signing
    hop.scopes = ["admin"]  # widened — signature now invalid
    with pytest.raises(InvalidSignatureError):
        verify_delegation_hop(hop, pub)


def test_verify_rejects_unsigned_hop() -> None:
    _require_cryptography()
    pub = generate_keypair()[1]
    hop = _make_hop()
    with pytest.raises(InvalidSignatureError, match="no signature"):
        verify_delegation_hop(hop, pub)


def test_verify_rejects_wrong_key() -> None:
    _require_cryptography()
    priv1, _ = generate_keypair()
    _, pub2 = generate_keypair()
    hop = _make_hop()
    sign_delegation_hop(hop, priv1, "key-1")
    with pytest.raises(InvalidSignatureError):
        verify_delegation_hop(hop, pub2)


def test_validator_enforces_required_signatures() -> None:
    _require_cryptography()
    """require_signatures=True rejects a chain with no signed hops."""
    priv, pub = generate_keypair()
    validator = DelegationValidator(require_signatures=True)
    validator.register_public_key("key-1", pub)

    hop = _make_hop()
    # unsigned chain
    sec = MessageSecurity(delegation_chain=[hop])
    result = validator.validate(sec)
    assert not result.valid
    assert "no signed hops" in result.reason


def test_validator_accepts_signed_chain() -> None:
    _require_cryptography()
    priv, pub = generate_keypair()
    validator = DelegationValidator(require_signatures=True)
    validator.register_public_key("key-1", pub)

    hop = _make_hop()
    sign_delegation_hop(hop, priv, "key-1")
    sec = MessageSecurity(delegation_chain=[hop])
    result = validator.validate(sec)
    assert result.valid, result.reason


def test_validator_rejects_tampered_signed_chain() -> None:
    _require_cryptography()
    priv, pub = generate_keypair()
    validator = DelegationValidator(require_signatures=True)
    validator.register_public_key("key-1", pub)

    hop = _make_hop()
    sign_delegation_hop(hop, priv, "key-1")
    hop.scopes = ["admin"]  # tamper after signing
    sec = MessageSecurity(delegation_chain=[hop])
    result = validator.validate(sec)
    assert not result.valid


def test_validator_rejects_unknown_signing_key() -> None:
    _require_cryptography()
    priv, _ = generate_keypair()
    validator = DelegationValidator(require_signatures=True)
    # no key registered under "key-1"
    hop = _make_hop()
    sign_delegation_hop(hop, priv, "key-1")
    sec = MessageSecurity(delegation_chain=[hop])
    result = validator.validate(sec)
    assert not result.valid
    assert "Unknown signing key" in result.reason
