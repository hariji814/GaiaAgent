"""AURC Authentication — multi-method authentication support.
AURC 认证 — 多方式认证支持

Supports:
- API Key authentication / API Key 认证
- JWT token validation / JWT 令牌验证
- OAuth 2.1 token introspection / OAuth 2.1 令牌内省
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """Authentication failure. 认证失败"""
    pass


@dataclass
class AuthResult:
    """Result of an authentication attempt. 认证结果"""
    authenticated: bool
    agent_id: str | None = None
    scopes: list[str] = field(default_factory=list)
    expires_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def is_valid(self) -> bool:
        """Check if the auth result is valid and not expired."""
        if not self.authenticated:
            return False
        if self.expires_at and datetime.now(timezone.utc) > self.expires_at:
            return False
        return True


# =============================================================================
# API Key Authentication / API Key 认证
# =============================================================================


class APIKeyAuthenticator:
    """API Key based authentication.
    基于 API Key 的认证

    Keys are stored as SHA-256 hashes for security.
    Each key is associated with an agent ID and scopes.

    Usage / 用法:
        auth = APIKeyAuthenticator()
        key = auth.create_key("aurc:gaia/researcher:v1.0", scopes=["research:read"])
        result = auth.authenticate(key)
    """

    def __init__(self) -> None:
        # key_hash → (agent_id, scopes, created_at) / 键哈希 → (Agent ID, 权限, 创建时间)
        self._keys: dict[str, tuple[str, list[str], datetime]] = {}

    def create_key(
        self,
        agent_id: str,
        scopes: list[str] | None = None,
        prefix: str = "aurc",
    ) -> str:
        """Create a new API key for an agent.
        为 Agent 创建新的 API Key

        Args:
            agent_id: Agent's AURC ID / Agent 的 AURC ID
            scopes: Permission scopes / 权限范围
            prefix: Key prefix for identification / 键前缀用于标识

        Returns:
            The raw API key (shown only once) / 原始 API Key（仅显示一次）
        """
        raw_key = f"{prefix}_{secrets.token_urlsafe(32)}"
        key_hash = self._hash_key(raw_key)
        self._keys[key_hash] = (
            agent_id,
            scopes or [],
            datetime.now(timezone.utc),
        )
        logger.info("API key created for agent '%s'", agent_id)
        return raw_key

    def authenticate(self, raw_key: str) -> AuthResult:
        """Authenticate using an API key.
        使用 API Key 认证

        Args:
            raw_key: The raw API key string / 原始 API Key 字符串

        Returns:
            AuthResult with authentication status / 包含认证状态的 AuthResult
        """
        key_hash = self._hash_key(raw_key)
        entry = self._keys.get(key_hash)

        if entry is None:
            return AuthResult(authenticated=False, error="Invalid API key")

        agent_id, scopes, created_at = entry
        return AuthResult(
            authenticated=True,
            agent_id=agent_id,
            scopes=scopes,
            metadata={"created_at": created_at.isoformat(), "method": "api_key"},
        )

    def revoke_key(self, raw_key: str) -> bool:
        """Revoke an API key. 吊销 API Key"""
        key_hash = self._hash_key(raw_key)
        if key_hash in self._keys:
            del self._keys[key_hash]
            logger.info("API key revoked")
            return True
        return False

    def revoke_agent_keys(self, agent_id: str) -> int:
        """Revoke all keys for an agent. 吊销 Agent 的所有 Key"""
        to_remove = [
            h for h, (aid, _, _) in self._keys.items()
            if aid == agent_id
        ]
        for h in to_remove:
            del self._keys[h]
        return len(to_remove)

    @property
    def key_count(self) -> int:
        return len(self._keys)

    @staticmethod
    def _hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode()).hexdigest()


# =============================================================================
# JWT Authentication / JWT 认证
# =============================================================================


class JWTAuthenticator:
    """JWT token authentication (simplified, without external library dependency).
    JWT 令牌认证（简化版，不依赖外部库）

    This is a simplified implementation for the AURC protocol spec.
    In production, use a full JWT library (e.g., python-jose, PyJWT).

    Token structure / 令牌结构:
    - Header: {"alg": "HS256", "typ": "JWT"}
    - Payload: {"sub": agent_id, "scopes": [...], "exp": timestamp, "iat": timestamp}
    - Signature: HMAC-SHA256(header.payload, secret)
    """

    def __init__(self, secret: str | None = None) -> None:
        self._secret = secret or secrets.token_urlsafe(64)

    def create_token(
        self,
        agent_id: str,
        scopes: list[str] | None = None,
        expires_in_seconds: int = 3600,
    ) -> str:
        """Create a JWT token. 创建 JWT 令牌"""
        now = int(time.time())
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "sub": agent_id,
            "scopes": scopes or [],
            "iat": now,
            "exp": now + expires_in_seconds,
        }

        header_b64 = self._b64encode(json.dumps(header))
        payload_b64 = self._b64encode(json.dumps(payload))
        signature = self._sign(f"{header_b64}.{payload_b64}")

        return f"{header_b64}.{payload_b64}.{signature}"

    def authenticate(self, token: str) -> AuthResult:
        """Authenticate using a JWT token. 使用 JWT 令牌认证"""
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return AuthResult(authenticated=False, error="Invalid token format")

            header_b64, payload_b64, signature = parts

            # Verify signature / 验证签名
            expected_sig = self._sign(f"{header_b64}.{payload_b64}")
            if not hmac.compare_digest(signature, expected_sig):
                return AuthResult(authenticated=False, error="Invalid signature")

            # Decode payload / 解码载荷
            payload = json.loads(self._b64decode(payload_b64))

            # Check expiration / 检查过期
            exp = payload.get("exp", 0)
            if time.time() > exp:
                return AuthResult(authenticated=False, error="Token expired")

            return AuthResult(
                authenticated=True,
                agent_id=payload.get("sub"),
                scopes=payload.get("scopes", []),
                expires_at=datetime.fromtimestamp(exp, tz=timezone.utc),
                metadata={"method": "jwt", "issued_at": payload.get("iat")},
            )
        except Exception as e:
            return AuthResult(authenticated=False, error=f"Token error: {e}")

    def _sign(self, data: str) -> str:
        sig = hmac.new(self._secret.encode(), data.encode(), hashlib.sha256).digest()
        return self._b64encode_bytes(sig)

    @staticmethod
    def _b64encode(data: str) -> str:
        return base64.urlsafe_b64encode(data.encode()).rstrip(b"=").decode()

    @staticmethod
    def _b64encode_bytes(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    @staticmethod
    def _b64decode(data: str) -> str:
        padding = 4 - len(data) % 4
        if padding != 4:
            data += "=" * padding
        return base64.urlsafe_b64decode(data).decode()


# =============================================================================
# Multi-Method Authenticator / 多方式认证器
# =============================================================================


class MultiAuthenticator:
    """Combines multiple authentication methods.
    组合多种认证方式

    Tries each authenticator in order and returns the first successful result.

    Usage / 用法:
        auth = MultiAuthenticator()
        auth.add_api_key()
        auth.add_jwt(secret="my-secret")

        result = auth.authenticate("api_key", raw_key)
        result = auth.authenticate("jwt", token)
    """

    def __init__(self) -> None:
        self._authenticators: dict[str, Any] = {}

    def add_api_key(self) -> APIKeyAuthenticator:
        """Add API Key authentication. 添加 API Key 认证"""
        authenticator = APIKeyAuthenticator()
        self._authenticators["api_key"] = authenticator
        return authenticator

    def add_jwt(self, secret: str | None = None) -> JWTAuthenticator:
        """Add JWT authentication. 添加 JWT 认证"""
        authenticator = JWTAuthenticator(secret)
        self._authenticators["jwt"] = authenticator
        return authenticator

    def authenticate(self, method: str, credential: str) -> AuthResult:
        """Authenticate using a specific method.
        使用特定方式认证

        Args:
            method: Authentication method name / 认证方式名称
            credential: The credential (key, token, etc.) / 凭证
        """
        authenticator = self._authenticators.get(method)
        if not authenticator:
            return AuthResult(
                authenticated=False,
                error=f"Unknown auth method: {method}",
            )
        return authenticator.authenticate(credential)

    def authenticate_any(self, credentials: dict[str, str]) -> AuthResult:
        """Try multiple authentication methods, return first success.
        尝试多种认证方式，返回首个成功结果

        Args:
            credentials: Dict of method → credential / 方法 → 凭证 映射
        """
        for method, credential in credentials.items():
            result = self.authenticate(method, credential)
            if result.authenticated:
                return result
        return AuthResult(authenticated=False, error="All authentication methods failed")
