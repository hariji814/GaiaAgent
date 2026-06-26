"""Ed25519 delegation signatures for cross-protocol identity integrity.
Ed25519 委托签名，用于跨协议身份完整性

Each delegation hop can be cryptographically signed by the delegating agent
so that a bridge/recipient can verify the chain was not tampered with. This
closes the gap where DelegationValidator previously only checked structural
rules (scope narrowing, depth) without proving authenticity.

依赖 `cryptography` 包（通过 `gaiaagent[security]` 安装）。未安装时，
签名/验证会抛出 :class:`SigningUnavailableError`，但模块导入不会失败 ——
这样不启用安全增强的部署仍可正常使用其余功能。
"""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import TYPE_CHECKING

from ..core.message import DelegationHop

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class SigningError(Exception):
    """Base error for delegation signing/verification failures. 委托签名错误"""


class SigningUnavailableError(SigningError):
    """cryptography is not installed. 未安装 cryptography"""


class InvalidSignatureError(SigningError):
    """A delegation hop signature did not verify. 委托跳签名验证失败"""


def _has_cryptography() -> bool:
    try:
        import cryptography  # noqa: F401
    except ImportError:
        return False
    return True


def _canonical_hop_bytes(hop: DelegationHop) -> bytes:
    """Canonical byte representation of a hop for signing/verification.

    对委托跳的规范化字节表示，用于签名与验签。

    The representation is deterministic: it hashes from_agent, to_agent, the
    sorted scopes, and the ISO-8601 timestamp. Adding a signature field to the
    hop later must NOT be included (it would be circular).
    """
    payload = "|".join([
        hop.from_agent,
        hop.to_agent,
        ",".join(sorted(hop.scopes)),
        hop.timestamp.isoformat(),
    ])
    return payload.encode("utf-8")


def _hop_digest(hop: DelegationHop) -> str:
    """SHA-256 hex digest of the canonical hop bytes. 委托跳摘要"""
    return hashlib.sha256(_canonical_hop_bytes(hop)).hexdigest()


def generate_keypair() -> tuple[bytes, bytes]:
    """Generate an Ed25519 keypair.

    生成 Ed25519 密钥对

    Returns:
        (private_key_bytes, public_key_bytes) as 32-byte raw seeds/keys
        / (私钥字节, 公钥字节)，各 32 字节

    Raises:
        SigningUnavailableError: if cryptography is not installed
    """
    if not _has_cryptography():
        raise SigningUnavailableError(
            "cryptography is required for Ed25519 signing. "
            "Install with: pip install gaiaagent[security]"
        )
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
        PublicFormat,
    )

    priv = Ed25519PrivateKey.generate()
    priv_bytes = priv.private_bytes(
        encoding=Encoding.Raw,
        format=PrivateFormat.Raw,
        encryption_algorithm=NoEncryption(),
    )
    pub_bytes = priv.public_key().public_bytes(
        encoding=Encoding.Raw,
        format=PublicFormat.Raw,
    )
    return priv_bytes, pub_bytes


def sign_delegation_hop(
    hop: DelegationHop,
    private_key_bytes: bytes,
    key_id: str,
) -> DelegationHop:
    """Sign a delegation hop in-place and return it.

    对委托跳签名（就地修改并返回）。

    The signature covers the canonical hop bytes. The `key_id` is recorded so
    verifiers know which public key to use. A hop already carrying a signature
    is re-signed (overwriting).

    Args:
        hop: The delegation hop to sign / 待签名委托跳
        private_key_bytes: 32-byte Ed25519 private key / 32 字节私钥
        key_id: Identifier for the corresponding public key / 公钥标识

    Returns:
        The same hop with signature + signing_key_id populated
        / 同一委托跳，已填入签名与密钥标识

    Raises:
        SigningUnavailableError: if cryptography is not installed
    """
    if not _has_cryptography():
        raise SigningUnavailableError(
            "cryptography is required for Ed25519 signing. "
            "Install with: pip install gaiaagent[security]"
        )
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )

    priv = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    sig = priv.sign(_canonical_hop_bytes(hop))
    hop.signature = base64.b64encode(sig).decode("ascii")
    hop.signing_key_id = key_id
    logger.debug("Signed delegation hop %s -> %s (key=%s)", hop.from_agent, hop.to_agent, key_id)
    return hop


def verify_delegation_hop(
    hop: DelegationHop,
    public_key_bytes: bytes,
) -> None:
    """Verify a delegation hop's signature.

    验证委托跳签名。

    Args:
        hop: The delegation hop carrying a signature / 携带签名的委托跳
        public_key_bytes: 32-byte Ed25519 public key / 32 字节公钥

    Raises:
        SigningUnavailableError: if cryptography is not installed
        InvalidSignatureError: if the hop is unsigned or the signature is bad
    """
    if not _has_cryptography():
        raise SigningUnavailableError(
            "cryptography is required for Ed25519 verification. "
            "Install with: pip install gaiaagent[security]"
        )
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PublicKey,
    )

    if not getattr(hop, "signature", ""):
        raise InvalidSignatureError(
            f"Hop {hop.from_agent} -> {hop.to_agent} has no signature"
        )
    try:
        sig = base64.b64decode(hop.signature)
    except Exception as exc:
        raise InvalidSignatureError(f"Malformed signature: {exc}") from exc

    pub = Ed25519PublicKey.from_public_bytes(public_key_bytes)
    try:
        pub.verify(sig, _canonical_hop_bytes(hop))
    except Exception as exc:
        raise InvalidSignatureError(
            f"Signature verification failed for hop {hop.from_agent} -> {hop.to_agent}: {exc}"
        ) from exc


__all__ = [
    "SigningError",
    "SigningUnavailableError",
    "InvalidSignatureError",
    "generate_keypair",
    "sign_delegation_hop",
    "verify_delegation_hop",
]
