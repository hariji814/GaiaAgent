"""AURC Identity — Agent ID parsing, validation, and Agent Descriptor.
AURC 身份系统 — Agent ID 解析、验证和 Agent 描述文档
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

# =============================================================================
# AURC ID
# =============================================================================

_AURC_ID_PATTERN = re.compile(
    r"^aurc:"
    r"(?P<namespace>[a-z0-9][a-z0-9._-]{0,63})"
    r"/"
    r"(?P<name>[a-z0-9][a-z0-9._-]{0,127})"
    r":"
    r"(?P<version>v\d+(?:\.\d+){0,2})"
    r"$"
)


class AURCId(BaseModel):
    """AURC Agent Identifier.
    AURC Agent 标识符

    Format: aurc:{namespace}/{name}:{version}
    Example: aurc:gaia/researcher:v1.2

    Design rationale / 设计理由:
        - URN-style for simplicity (no blockchain dependency like DID)
        - namespace provides decentralized uniqueness (like Docker Hub org/image)
        - version pinning ensures reproducibility
    """

    raw: str = Field(description="Full AURC ID string / 完整 AURC ID 字符串")
    namespace: str = Field(description="Organization or project namespace / 组织或项目命名空间")
    name: str = Field(description="Agent name within namespace / Agent 名称")
    version: str = Field(description="Semantic version tag / 语义版本标签")

    @field_validator("raw")
    @classmethod
    def validate_format(cls, v: str) -> str:
        if not _AURC_ID_PATTERN.match(v):
            raise ValueError(
                f"Invalid AURC ID format: '{v}'. "
                f"Expected: aurc:{{namespace}}/{{name}}:{{version}}, "
                f"e.g. aurc:gaia/researcher:v1.2"
            )
        return v

    @classmethod
    def parse(cls, id_string: str) -> AURCId:
        """Parse an AURC ID string into its components.
        解析 AURC ID 字符串为各组成部分

        Args:
            id_string: e.g. "aurc:gaia/researcher:v1.2"

        Returns:
            AURCId instance

        Raises:
            ValueError: If the format is invalid
        """
        match = _AURC_ID_PATTERN.match(id_string)
        if not match:
            raise ValueError(
                f"Invalid AURC ID: '{id_string}'. "
                f"Expected format: aurc:{{namespace}}/{{name}}:{{version}}"
            )
        return cls(
            raw=id_string,
            namespace=match.group("namespace"),
            name=match.group("name"),
            version=match.group("version"),
        )

    def matches(self, pattern: str) -> bool:
        """Check if this ID matches a glob-like pattern.
        检查 ID 是否匹配通配符模式

        Patterns:
            "aurc:gaia/*" matches any agent in gaia namespace
            "aurc:*/researcher:*" matches any researcher agent
            "aurc:gaia/researcher:v1.*" matches v1.x versions
        """
        regex = pattern.replace(".", r"\.").replace("*", ".*")
        return bool(re.match(f"^{regex}$", self.raw))

    def __str__(self) -> str:
        return self.raw

    def __hash__(self) -> int:
        return hash(self.raw)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, AURCId):
            return self.raw == other.raw
        if isinstance(other, str):
            return self.raw == other
        return NotImplemented


# =============================================================================
# Capability Declaration / 能力声明
# =============================================================================


class InputOutputSchema(BaseModel):
    """JSON Schema for skill input or output. 技能的输入/输出 JSON Schema"""

    type: str = "object"
    properties: dict[str, Any] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)


class SkillDeclaration(BaseModel):
    """Declaration of a single skill an agent provides.
    Agent 提供的单项技能声明
    """

    skill_id: str = Field(description="Unique skill identifier / 技能唯一标识")
    name: str = Field(description="Human-readable skill name / 人类可读的技能名")
    description: str = Field(default="", description="Skill description / 技能描述")
    input_schema: InputOutputSchema = Field(default_factory=InputOutputSchema)
    output_schema: InputOutputSchema = Field(default_factory=InputOutputSchema)
    tags: list[str] = Field(default_factory=list, description="Searchable tags / 搜索标签")


class Capabilities(BaseModel):
    """Agent capability declaration. Agent 能力声明

    Separates what the agent provides vs what it consumes,
    enabling the registry to match producers with consumers.
    """

    provides: list[SkillDeclaration] = Field(
        default_factory=list,
        description="Skills this agent offers / 此 Agent 提供的技能",
    )
    consumes: list[str] = Field(
        default_factory=list,
        description="Skill IDs this agent needs from others / 此 Agent 需要的外部技能",
    )

    def has_skill(self, skill_id: str) -> bool:
        """Check if this agent provides a specific skill."""
        return any(s.skill_id == skill_id for s in self.provides)

    def get_skill(self, skill_id: str) -> SkillDeclaration | None:
        """Get a skill declaration by ID."""
        for s in self.provides:
            if s.skill_id == skill_id:
                return s
        return None


# =============================================================================
# Protocol Binding / 协议绑定
# =============================================================================


class ProtocolSupport(BaseModel):
    """Declares which protocols an agent supports.
    声明 Agent 支持的协议
    """

    native: str = Field(
        default="aurc/0.1",
        description="Native AURC protocol version / 原生 AURC 协议版本",
    )
    bridges: list[str] = Field(
        default_factory=list,
        description="External protocols supported via bridges / 通过桥接支持的外部协议",
    )

    def supports(self, protocol: str) -> bool:
        """Check if a specific protocol version is supported."""
        return protocol == self.native or protocol in self.bridges


# =============================================================================
# Runtime Requirements / 运行时需求
# =============================================================================


class RuntimeRequirements(BaseModel):
    """Agent runtime requirements. Agent 运行时需求"""

    min_memory_mb: int = Field(default=256, description="Minimum memory in MB / 最小内存 MB")
    max_concurrency: int = Field(default=10, description="Maximum concurrent tasks / 最大并发数")
    supports_streaming: bool = Field(
        default=True, description="Supports streaming responses / 支持流式响应"
    )
    supports_pause: bool = Field(default=False, description="Supports pause/resume / 支持暂停恢复")
    timeout_seconds: int = Field(default=3600, description="Default task timeout / 默认任务超时")


# =============================================================================
# Auth Declaration / 认证声明
# =============================================================================


class AuthDeclaration(BaseModel):
    """Agent authentication declaration. Agent 认证声明"""

    methods: list[str] = Field(
        default_factory=lambda: ["api_key"],
        description="Supported auth methods / 支持的认证方式",
    )
    scopes: list[str] = Field(
        default_factory=list,
        description="Available permission scopes / 可用权限范围",
    )


# =============================================================================
# Agent Descriptor / Agent 描述文档
# =============================================================================


class AgentDescriptor(BaseModel):
    """Complete Agent Descriptor — the identity document for an AURC agent.
    完整的 Agent 描述文档 — AURC Agent 的身份文档

    This is the AURC equivalent of:
    - MCP's server capabilities (but richer)
    - A2A's Agent Card (but protocol-agnostic)

    It serves as the single source of truth for:
    1. Who the agent is (identity)
    2. What it can do (capabilities)
    3. How to communicate with it (protocols)
    4. What it needs to run (runtime requirements)
    5. How to authenticate (security)
    """

    # Schema version / 模式版本
    schema_version: str = Field(
        default="aurc://spec/v0.1/agent-descriptor.json",
        description="Descriptor schema version / 描述文档模式版本",
    )

    # Identity / 身份
    aurc_id: str = Field(description="Full AURC ID, e.g. 'aurc:gaia/researcher:v1.2'")
    display_name: str = Field(description="Human-readable display name / 人类可读显示名")
    description: str = Field(default="", description="Agent description / Agent 描述")
    version: str = Field(default="0.1.0", description="Agent software version / Agent 软件版本")
    author: str = Field(default="", description="Agent author / Agent 作者")
    license: str = Field(default="Apache-2.0", description="License / 许可证")

    # Capabilities / 能力
    capabilities: Capabilities = Field(default_factory=Capabilities)

    # Protocols / 协议
    protocols: ProtocolSupport = Field(default_factory=ProtocolSupport)

    # Runtime / 运行时
    runtime: RuntimeRequirements = Field(default_factory=RuntimeRequirements)

    # Auth / 认证
    auth: AuthDeclaration = Field(default_factory=AuthDeclaration)

    # Metadata / 元数据
    tags: list[str] = Field(default_factory=list, description="Searchable tags / 搜索标签")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary metadata / 任意元数据",
    )

    @field_validator("aurc_id")
    @classmethod
    def validate_aurc_id(cls, v: str) -> str:
        AURCId.parse(v)  # Validates format
        return v

    @property
    def parsed_id(self) -> AURCId:
        """Get the parsed AURC ID."""
        return AURCId.parse(self.aurc_id)

    def to_registry_entry(self) -> dict[str, Any]:
        """Convert to a registry-compatible entry.
        转换为注册中心兼容的条目
        """
        return {
            "aurc_id": self.aurc_id,
            "display_name": self.display_name,
            "description": self.description,
            "capabilities": {
                "provides": [s.skill_id for s in self.capabilities.provides],
                "consumes": self.capabilities.consumes,
            },
            "protocols": {
                "native": self.protocols.native,
                "bridges": self.protocols.bridges,
            },
            "tags": self.tags,
        }
