"""AURC SDK — Decorators for declarative agent definition.
AURC SDK — 声明式 Agent 定义的装饰器

Provides a developer-friendly API for creating AURC agents:

    @aurc_agent(id="aurc:gaia/researcher:v1.0", capabilities=["research"])
    class ResearchAgent:
        @skill("research")
        async def research(self, query: str) -> dict:
            return {"report": "..." }

    # One-line harness setup:
    harness = AURCHarness(bridges=[MCPBridge(), A2ABridge()])
    await harness.start()
"""

from __future__ import annotations

import functools
import inspect
import logging
from typing import Any, Callable, TypeVar, get_type_hints

from ..core.identity import (
    AgentDescriptor,
    AuthDeclaration,
    Capabilities,
    ProtocolSupport,
    RuntimeRequirements,
    SkillDeclaration,
    InputOutputSchema,
)

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable)


# =============================================================================
# Skill Decorator / 技能装饰器
# =============================================================================


def skill(
    skill_id: str | None = None,
    name: str | None = None,
    description: str = "",
    tags: list[str] | None = None,
) -> Callable[[F], F]:
    """Decorator to mark a method as an AURC skill.
    将方法标记为 AURC 技能的装饰器

    The decorated method becomes a callable skill that can be:
    - Discovered by the AURC Registry / 被 AURC 注册中心发现
    - Invoked via AURC messages / 通过 AURC 消息调用
    - Bridged to MCP tools or A2A skills / 桥接到 MCP 工具或 A2A 技能

    Args:
        skill_id: Unique skill identifier (defaults to method name) / 技能唯一标识
        name: Human-readable name (defaults to method name) / 人类可读名称
        description: Skill description / 技能描述
        tags: Searchable tags / 搜索标签

    Example / 示例:
        @skill("deep-research", description="Multi-source research and analysis")
        async def research(self, query: str, depth: str = "medium") -> dict:
            ...
    """
    def decorator(func: F) -> F:
        actual_skill_id = skill_id or func.__name__
        actual_name = name or func.__name__.replace("_", " ").title()
        actual_tags = tags or []

        # Store skill metadata on the function / 在函数上存储技能元数据
        func._aurc_skill = SkillMetadata(  # type: ignore[attr-defined]
            skill_id=actual_skill_id,
            name=actual_name,
            description=description or func.__doc__ or "",
            tags=actual_tags,
            input_schema=_extract_input_schema(func),
            output_schema=_extract_output_schema(func),
        )

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            logger.debug("Skill '%s' invoked with params: %s", actual_skill_id, kwargs)
            result = await func(*args, **kwargs) if inspect.iscoroutinefunction(func) else func(*args, **kwargs)
            logger.debug("Skill '%s' completed", actual_skill_id)
            return result

        # Copy metadata to wrapper / 复制元数据到包装器
        wrapper._aurc_skill = func._aurc_skill  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator


class SkillMetadata:
    """Metadata stored for a @skill decorated method."""

    __slots__ = ("skill_id", "name", "description", "tags", "input_schema", "output_schema")

    def __init__(
        self,
        skill_id: str,
        name: str,
        description: str,
        tags: list[str],
        input_schema: InputOutputSchema,
        output_schema: InputOutputSchema,
    ):
        self.skill_id = skill_id
        self.name = name
        self.description = description
        self.tags = tags
        self.input_schema = input_schema
        self.output_schema = output_schema

    def to_declaration(self) -> SkillDeclaration:
        """Convert to a SkillDeclaration for the Agent Descriptor."""
        return SkillDeclaration(
            skill_id=self.skill_id,
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
            output_schema=self.output_schema,
            tags=self.tags,
        )


# =============================================================================
# Agent Decorator / Agent 装饰器
# =============================================================================


def aurc_agent(
    id: str,
    display_name: str | None = None,
    description: str = "",
    version: str = "0.1.0",
    author: str = "",
    license: str = "AGPL-3.0",
    protocols: list[str] | None = None,
    tags: list[str] | None = None,
    consumes: list[str] | None = None,
    max_concurrency: int = 10,
    supports_streaming: bool = True,
    supports_pause: bool = False,
    timeout_seconds: int = 3600,
    auth_methods: list[str] | None = None,
) -> Callable[[type], type]:
    """Decorator to declare an AURC agent class.
    声明 AURC Agent 类的装饰器

    Scans the class for @skill decorated methods and builds
    the AgentDescriptor automatically.

    Args:
        id: AURC ID (e.g., "aurc:gaia/researcher:v1.0") / AURC ID
        display_name: Human-readable name / 人类可读名称
        description: Agent description / Agent 描述
        version: Agent software version / Agent 软件版本
        author: Agent author / Agent 作者
        license: License identifier / 许可证标识
        protocols: External protocols supported / 支持的外部协议
        tags: Searchable tags / 搜索标签
        consumes: External skill IDs this agent needs / 此 Agent 需要的外部技能
        max_concurrency: Maximum concurrent tasks / 最大并发任务数
        supports_streaming: Supports streaming responses / 支持流式响应
        supports_pause: Supports pause/resume / 支持暂停/恢复
        timeout_seconds: Default task timeout / 默认任务超时
        auth_methods: Supported auth methods / 支持的认证方式

    Example / 示例:
        @aurc_agent(
            id="aurc:gaia/researcher:v1.0",
            display_name="Research Agent",
            description="Deep research with multi-source analysis",
            protocols=["mcp/2025-06-18", "a2a/1.0"],
            tags=["research", "analysis"],
        )
        class ResearchAgent:
            @skill("deep-research", description="Multi-source research")
            async def research(self, query: str) -> dict:
                return {"report": "..."}
    """
    def decorator(cls: type) -> type:
        # Scan for @skill methods / 扫描 @skill 方法
        skills = _collect_skills(cls)

        # Build the Agent Descriptor / 构建 Agent 描述文档
        descriptor = AgentDescriptor(
            aurc_id=id,
            display_name=display_name or cls.__name__,
            description=description or cls.__doc__ or "",
            version=version,
            author=author,
            license=license,
            capabilities=Capabilities(
                provides=[s.to_declaration() for s in skills],
                consumes=consumes or [],
            ),
            protocols=ProtocolSupport(
                native="aurc/0.1",
                bridges=protocols or [],
            ),
            runtime=RuntimeRequirements(
                max_concurrency=max_concurrency,
                supports_streaming=supports_streaming,
                supports_pause=supports_pause,
                timeout_seconds=timeout_seconds,
            ),
            auth=AuthDeclaration(
                methods=auth_methods or ["api_key"],
                scopes=[],
            ),
            tags=tags or [],
        )

        # Attach descriptor and skill metadata to the class / 将描述和技能元数据附加到类
        cls._aurc_descriptor = descriptor  # type: ignore[attr-defined]
        cls._aurc_skills = {s.skill_id: s for s in skills}  # type: ignore[attr-defined]

        # Add a helper property / 添加辅助属性
        @property  # type: ignore[misc]
        def aurc_descriptor(self: Any) -> AgentDescriptor:
            return self.__class__._aurc_descriptor

        cls.aurc_descriptor = aurc_descriptor  # type: ignore[attr-defined]

        logger.info(
            "AURC Agent registered: %s with %d skills (%s)",
            id,
            len(skills),
            ", ".join(s.skill_id for s in skills),
        )

        return cls

    return decorator


# =============================================================================
# Internal Helpers / 内部辅助
# =============================================================================


def _collect_skills(cls: type) -> list[SkillMetadata]:
    """Scan a class for @skill decorated methods."""
    skills = []
    for attr_name in dir(cls):
        attr = getattr(cls, attr_name, None)
        if callable(attr) and hasattr(attr, "_aurc_skill"):
            skills.append(attr._aurc_skill)
    return skills


def _extract_input_schema(func: Callable) -> InputOutputSchema:
    """Extract input schema from function type hints.
    从函数类型提示中提取输入模式
    """
    hints = get_type_hints(func)
    sig = inspect.signature(func)

    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue

        param_type = hints.get(param_name, str)
        json_type = _python_type_to_json(param_type)
        properties[param_name] = {"type": json_type}

        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    return InputOutputSchema(
        type="object",
        properties=properties,
        required=required,
    )


def _extract_output_schema(func: Callable) -> InputOutputSchema:
    """Extract output schema from function return type hint."""
    hints = get_type_hints(func)
    return_type = hints.get("return", dict)
    json_type = _python_type_to_json(return_type)

    return InputOutputSchema(type=json_type)


def _python_type_to_json(python_type: type) -> str:
    """Convert a Python type to JSON Schema type string."""
    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }
    return type_map.get(python_type, "object")
