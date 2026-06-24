"""ACP Bridge — Agent Communication Protocol bridge implementation.
ACP 桥接器 — Agent Communication Protocol 桥接实现

Translates between IBM's ACP (Agent Communication Protocol) and AURC.

ACP key concepts / ACP 关键概念:
- Agent: An entity that can be invoked to perform tasks
- Task: A unit of work with a lifecycle (submitted→running→completed/failed)
- Session: Optional grouping of related invocations
- Skills: Capabilities declared by an agent descriptor

ACP is a lightweight, HTTP-native protocol designed for agent-to-agent
communication. It uses a simple JSON envelope (not JSON-RPC) with method-based
dispatch.

ACP 是一个轻量级的、基于 HTTP 的协议，专为 Agent 间通信设计。
它使用简单的 JSON 信封（非 JSON-RPC）进行基于方法的分发。
"""

from __future__ import annotations

import logging
from typing import Any

from ..core.message import AURCMessage, BridgeContext, MessageBody
from ..core.types import MessageDirection

logger = logging.getLogger(__name__)


# =============================================================================
# ACP Bridge Implementation / ACP 桥接器实现
# =============================================================================


class ACPBridge:
    """ACP ↔ AURC Bridge.
    ACP ↔ AURC 桥接器

    Translates between ACP (Agent Communication Protocol v1.0) and AURC.

    ACP uses a simple JSON envelope with method-based dispatch.
    Key methods / 关键方法:
    - invoke: Agent invocation — the primary way to start work (→ AURC delegation)
    - cancel: Cancel a running task (→ AURC notification)
    - get-task: Query task status (→ AURC request)
    - list-tasks: List tasks with optional filtering (→ AURC request)
    - set-task: Update task state directly (→ AURC notification)

    Direction mapping / 方向映射:
    ACP Client → AURC:  translate_to_aurc()
    AURC → ACP Server:  translate_from_aurc()

    Key translations / 关键转换:
    - ACP invoke → AURC delegation (agent invocation)
    - ACP cancel → AURC notification (task cancellation)
    - ACP get-task → AURC request (status query)
    - ACP list-tasks → AURC request (task listing)
    - ACP set-task → AURC notification (task state update)
    - ACP Agent Descriptor → AURC Agent Descriptor
    """

    @property
    def source_protocol(self) -> str:
        """External protocol identifier for ACP. ACP 外部协议标识符"""
        return "acp/1.0"

    def can_bridge(self, source_protocol: str, target_protocol: str) -> bool:
        """Check if this bridge handles the given protocol pair.
        检查此桥接器是否能处理指定的协议对

        Supports bidirectional bridging between ACP and AURC.
        支持 ACP 和 AURC 之间的双向桥接。
        """
        return (
            source_protocol == self.source_protocol and target_protocol == "aurc/0.1"
        ) or (
            source_protocol == "aurc/0.1" and target_protocol == self.source_protocol
        )

    # -------------------------------------------------------------------------
    # External → AURC / 外部协议 → AURC
    # -------------------------------------------------------------------------

    async def translate_to_aurc(self, acp_message: dict) -> AURCMessage:
        """Translate an ACP message to AURC format.
        将 ACP 消息翻译为 AURC 格式

        Handles:
        - invoke → AURC delegation (agent invocation) / 调用 → AURC 委派
        - cancel → AURC notification (task cancellation) / 取消 → AURC 通知
        - get-task → AURC request (status query) / 获取任务 → AURC 请求
        - list-tasks → AURC request (task listing) / 列出任务 → AURC 请求
        - set-task → AURC notification (task state update) / 设置任务 → AURC 通知

        ACP message format / ACP 消息格式:
            {
                "method": "invoke",
                "params": {
                    "agent_id": "acp-agent-id",
                    "task": "task-description",
                    "input": {...},
                    "session_id": "optional-session"
                },
                "id": "request-id"
            }
        """
        method = acp_message.get("method", "")
        params = acp_message.get("params", {})
        msg_id = acp_message.get("id")

        bridge_ctx = BridgeContext(
            origin_protocol="acp/1.0",
            bridged_from="acp/1.0",
            bridge_chain=["acp→aurc"],
        )

        if method == "invoke":
            # ACP agent invocation → AURC delegation / ACP Agent 调用 → AURC 委派
            # This is ACP's primary method — it asks an agent to perform work.
            # 这是 ACP 的主要方法 — 请求 Agent 执行工作。
            return AURCMessage(
                source=f"acp:external/{params.get('agent_id', 'unknown')}",
                target="aurc:local/orchestrator",
                type=MessageDirection.DELEGATION,
                body=MessageBody(
                    method="invoke",
                    skill=self._infer_skill(params.get("task", "")),
                    params={
                        "agent_id": params.get("agent_id", ""),
                        "task": params.get("task", ""),
                        "input": params.get("input", {}),
                        "session_id": params.get("session_id", ""),
                    },
                    metadata={
                        "acp_method": method,
                    },
                ),
                protocol_context=bridge_ctx,
                correlation_id=str(msg_id) if msg_id else None,
            )

        elif method == "cancel":
            # ACP task cancellation → AURC notification / ACP 任务取消 → AURC 通知
            return AURCMessage(
                source="acp:external/client",
                target="aurc:local/orchestrator",
                type=MessageDirection.NOTIFICATION,
                body=MessageBody(
                    event="task_cancelled",
                    data={
                        "task_id": params.get("task_id", ""),
                        "reason": params.get("reason", ""),
                    },
                ),
                protocol_context=bridge_ctx,
            )

        elif method == "get-task":
            # ACP task status query → AURC request / ACP 任务状态查询 → AURC 请求
            return AURCMessage(
                source="acp:external/client",
                target="aurc:local/orchestrator",
                type=MessageDirection.REQUEST,
                body=MessageBody(
                    method="query_task_status",
                    params={
                        "task_id": params.get("task_id", ""),
                    },
                ),
                protocol_context=bridge_ctx,
                correlation_id=str(msg_id) if msg_id else None,
            )

        elif method == "list-tasks":
            # ACP task listing → AURC request / ACP 任务列表 → AURC 请求
            return AURCMessage(
                source="acp:external/client",
                target="aurc:local/orchestrator",
                type=MessageDirection.REQUEST,
                body=MessageBody(
                    method="list_tasks",
                    params={
                        "agent_id": params.get("agent_id", ""),
                        "status_filter": params.get("status", ""),
                        "session_id": params.get("session_id", ""),
                    },
                ),
                protocol_context=bridge_ctx,
                correlation_id=str(msg_id) if msg_id else None,
            )

        elif method == "set-task":
            # ACP task state update → AURC notification / ACP 任务状态更新 → AURC 通知
            return AURCMessage(
                source="acp:external/client",
                target="aurc:local/orchestrator",
                type=MessageDirection.NOTIFICATION,
                body=MessageBody(
                    event="task_state_updated",
                    data={
                        "task_id": params.get("task_id", ""),
                        "state": params.get("state", ""),
                        "message": params.get("message", ""),
                    },
                ),
                protocol_context=bridge_ctx,
            )

        else:
            # Generic ACP method → AURC request / 通用 ACP 方法 → AURC 请求
            logger.warning("Unknown ACP method '%s', falling back to generic request", method)
            return AURCMessage(
                source="acp:external/client",
                target="aurc:local/orchestrator",
                type=MessageDirection.REQUEST,
                body=MessageBody(method=method, params=params),
                protocol_context=bridge_ctx,
                correlation_id=str(msg_id) if msg_id else None,
            )

    # -------------------------------------------------------------------------
    # AURC → External / AURC → 外部协议
    # -------------------------------------------------------------------------

    async def translate_from_aurc(self, aurc_message: AURCMessage) -> dict:
        """Translate an AURC message to ACP format.
        将 AURC 消息翻译为 ACP 格式

        Handles:
        - AURC delegation → ACP invoke / AURC 委派 → ACP 调用
        - AURC response → ACP result (completed/failed) / AURC 响应 → ACP 结果
        - AURC stream → ACP streaming updates / AURC 流式 → ACP 流式更新
        - AURC notification → ACP notification / AURC 通知 → ACP 通知

        ACP response format / ACP 响应格式:
            {
                "id": "request-id",
                "status": "completed" | "failed",
                "task_id": "task-id",
                "result": {...} | null,
                "error": "..." | null
            }
        """
        if aurc_message.type == MessageDirection.DELEGATION:
            # AURC delegation → ACP invoke / AURC 委派 → ACP 调用
            body = aurc_message.body
            return {
                "method": "invoke",
                "id": aurc_message.correlation_id or aurc_message.message_id,
                "params": {
                    "agent_id": body.params.get("agent_id", ""),
                    "task": body.params.get("task", ""),
                    "input": body.params.get("input", {}),
                    "session_id": body.params.get(
                        "session_id", aurc_message.session.session_id
                    ),
                },
            }

        elif aurc_message.type == MessageDirection.RESPONSE:
            body = aurc_message.body
            if body.error:
                # Map to ACP failed result / 映射为 ACP 失败结果
                return {
                    "id": aurc_message.correlation_id,
                    "status": "failed",
                    "task_id": body.metadata.get("task_id", ""),
                    "result": None,
                    "error": {
                        "code": body.error.code,
                        "message": body.error.message,
                        "details": body.error.details,
                    },
                }
            else:
                # Map to ACP completed result / 映射为 ACP 完成结果
                return {
                    "id": aurc_message.correlation_id,
                    "status": "completed",
                    "task_id": body.metadata.get("task_id", ""),
                    "result": body.result,
                    "error": None,
                }

        elif aurc_message.type == MessageDirection.STREAM:
            # AURC stream → ACP streaming update / AURC 流式 → ACP 流式更新
            body = aurc_message.body
            return {
                "method": "stream-update",
                "task_id": body.metadata.get("task_id", ""),
                "chunk": {
                    "index": body.chunk_index,
                    "total": body.total_chunks,
                    "data": body.data,
                    "is_final": body.is_final,
                },
            }

        elif aurc_message.type == MessageDirection.NOTIFICATION:
            body = aurc_message.body
            # Map AURC events to ACP notification types / 将 AURC 事件映射为 ACP 通知类型
            event_map = {
                "task_started": "task.started",
                "task_cancelled": "task.cancelled",
                "task_completed": "task.completed",
                "task_failed": "task.failed",
                "task_state_updated": "task.updated",
            }
            acp_event = event_map.get(body.event or "", body.event or "unknown")
            return {
                "method": "notification",
                "params": {
                    "event": acp_event,
                    "data": body.data or {},
                },
            }

        # Fallback — unsupported message type / 兜底 — 不支持的消息类型
        logger.warning(
            "Unsupported AURC message type '%s' for ACP translation",
            aurc_message.type,
        )
        return {
            "method": "unknown",
            "error": {
                "code": "unsupported_message_type",
                "message": f"Cannot translate AURC type '{aurc_message.type}' to ACP",
            },
        }

    # -------------------------------------------------------------------------
    # Capability Mapping / 能力映射
    # -------------------------------------------------------------------------

    async def map_capabilities(self, acp_skills: list[dict]) -> list[dict]:
        """Map ACP agent skills to AURC skill declarations.
        将 ACP Agent 技能映射为 AURC 技能声明

        ACP skills have: name, description, input_schema, output_schema
        AURC skills need: skill_id, name, description, input_schema, output_schema

        ACP 技能字段: name, description, input_schema, output_schema
        AURC 技能字段: skill_id, name, description, input_schema, output_schema
        """
        skills = []
        for skill in acp_skills:
            skill_name = skill.get("name", "")
            skills.append({
                "skill_id": f"acp:{skill.get('id', skill_name)}",
                "name": skill_name,
                "description": skill.get("description", ""),
                "input_schema": skill.get("input_schema", skill.get("inputSchema", {})),
                "output_schema": skill.get("output_schema", skill.get("outputSchema", {})),
                "tags": ["acp-bridge"],
            })
        return skills

    # -------------------------------------------------------------------------
    # Agent Descriptor Mapping / Agent 描述符映射
    # -------------------------------------------------------------------------

    def map_agent_card(self, agent_descriptor: dict) -> dict:
        """Convert an ACP agent descriptor to an AURC Agent Descriptor dict.
        将 ACP Agent 描述符转换为 AURC Agent Descriptor 字典

        ACP agent descriptors contain: name, description, skills, auth info.
        This method normalizes them into AURC's canonical agent descriptor format.

        ACP Agent 描述符包含: name, description, skills, auth 信息。
        此方法将其规范化为 AURC 的标准 Agent 描述符格式。
        """
        agent_name = agent_descriptor.get("name", "unknown")
        return {
            "aurc_id": f"aurc:acp-bridge/{agent_name}:v1.0",
            "display_name": agent_descriptor.get("name", ""),
            "description": agent_descriptor.get("description", ""),
            "capabilities": {
                "provides": [
                    {
                        "skill_id": f"acp:{s.get('id', s.get('name', ''))}",
                        "name": s.get("name", ""),
                        "description": s.get("description", ""),
                    }
                    for s in agent_descriptor.get("skills", [])
                ],
                "consumes": [],
            },
            "protocols": {
                "native": "aurc/0.1",
                "bridges": ["acp/1.0"],
            },
            "auth": {
                "methods": agent_descriptor.get("authentication", {}).get(
                    "methods", ["api_key"]
                ),
                "scopes": [],
            },
        }

    # -------------------------------------------------------------------------
    # Private helpers / 私有辅助方法
    # -------------------------------------------------------------------------

    @staticmethod
    def _infer_skill(task_description: str) -> str:
        """Infer the target skill from task description.
        从任务描述推断目标技能

        Uses keyword matching as a simple heuristic. In production, this would
        use more sophisticated intent classification or skill matching.

        使用关键词匹配作为简单启发式方法。生产环境中会使用更复杂的
        意图分类或技能匹配。
        """
        description_lower = task_description.lower()
        if any(kw in description_lower for kw in ["research", "search", "find", "look up"]):
            return "research"
        if any(kw in description_lower for kw in ["summarize", "summary", "brief", "digest"]):
            return "summarize"
        if any(kw in description_lower for kw in ["translate", "translation", "localize"]):
            return "translate"
        if any(kw in description_lower for kw in ["code", "program", "implement", "build"]):
            return "code-generation"
        if any(kw in description_lower for kw in ["analyze", "analysis", "evaluate"]):
            return "analysis"
        return "general"
