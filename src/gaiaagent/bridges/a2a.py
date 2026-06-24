"""A2A Bridge — Agent-to-Agent protocol bridge implementation.
A2A 桥接器 — Agent-to-Agent 协议桥接实现

Translates between Google's A2A (Agent-to-Agent) protocol and AURC.

A2A key concepts / A2A 关键概念:
- Agent Card: JSON metadata at /.well-known/agent-card.json
- Task: Unit of work with lifecycle (submitted→working→completed)
- Message: Contains typed Parts (text, file, data)
- Artifact: Output produced by a task
"""

from __future__ import annotations

import logging
from typing import Any

from ..core.message import AURCMessage, BridgeContext, MessageBody
from ..core.types import MessageDirection

logger = logging.getLogger(__name__)


class A2ABridge:
    """A2A ↔ AURC Bridge.
    A2A ↔ AURC 桥接器

    Translates between A2A (Agent-to-Agent protocol v1.0) and AURC.

    Direction mapping / 方向映射:
    A2A Client → AURC:  translate_to_aurc()
    AURC → A2A Server:  translate_from_aurc()

    Key translations / 关键转换:
    - A2A tasks/send → AURC delegation
    - A2A tasks/get → AURC request (status query)
    - A2A Task state changes → AURC notifications
    - A2A Agent Card → AURC Agent Descriptor
    """

    @property
    def source_protocol(self) -> str:
        return "a2a/1.0"

    def can_bridge(self, source_protocol: str, target_protocol: str) -> bool:
        return (
            source_protocol == self.source_protocol and target_protocol == "aurc/0.1"
        ) or (
            source_protocol == "aurc/0.1" and target_protocol == self.source_protocol
        )

    async def translate_to_aurc(self, a2a_message: dict) -> AURCMessage:
        """Translate an A2A JSON-RPC message to AURC format.
        将 A2A JSON-RPC 消息翻译为 AURC 格式

        Handles:
        - tasks/send → AURC delegation (new task)
        - tasks/sendSubscribe → AURC delegation with streaming
        - tasks/get → AURC request (task status query)
        - tasks/cancel → AURC notification (cancellation)
        - tasks/pushNotification/set → AURC notification (callback registration)
        """
        method = a2a_message.get("method", "")
        params = a2a_message.get("params", {})
        msg_id = a2a_message.get("id")

        bridge_ctx = BridgeContext(
            origin_protocol="a2a/1.0",
            bridged_from="a2a/1.0",
            bridge_chain=["a2a→aurc"],
        )

        if method in ("tasks/send", "tasks/sendSubscribe"):
            # A2A task creation → AURC delegation / A2A 任务创建 → AURC 委派
            task = params
            messages = task.get("messages", [])

            # Extract the actual request content from messages / 从消息中提取请求内容
            request_content = self._extract_content(messages)

            return AURCMessage(
                source=f"a2a:external/{task.get('sessionId', 'unknown')}",
                target="aurc:local/orchestrator",
                type=MessageDirection.DELEGATION,
                body=MessageBody(
                    method="invoke",
                    skill=self._infer_skill(request_content),
                    params={
                        "task_id": task.get("id", ""),
                        "session_id": task.get("sessionId", ""),
                        "content": request_content,
                        "artifacts": task.get("artifacts", []),
                    },
                    metadata={
                        "a2a_method": method,
                        "push_notification": task.get("pushNotification", {}),
                    },
                ),
                protocol_context=bridge_ctx,
                correlation_id=str(msg_id) if msg_id else None,
            )

        elif method == "tasks/get":
            # Task status query → AURC request / 任务状态查询 → AURC 请求
            return AURCMessage(
                source="a2a:external/client",
                target="aurc:local/orchestrator",
                type=MessageDirection.REQUEST,
                body=MessageBody(
                    method="query_task_status",
                    params={
                        "task_id": params.get("id", ""),
                    },
                ),
                protocol_context=bridge_ctx,
                correlation_id=str(msg_id) if msg_id else None,
            )

        elif method == "tasks/cancel":
            # Task cancellation → AURC notification / 任务取消 → AURC 通知
            return AURCMessage(
                source="a2a:external/client",
                target="aurc:local/orchestrator",
                type=MessageDirection.NOTIFICATION,
                body=MessageBody(
                    event="task_cancelled",
                    data={"task_id": params.get("id", "")},
                ),
                protocol_context=bridge_ctx,
            )

        elif method == "tasks/pushNotification/set":
            # Push notification registration → AURC notification / 推送通知注册 → AURC 通知
            return AURCMessage(
                source="a2a:external/client",
                target="aurc:local/orchestrator",
                type=MessageDirection.NOTIFICATION,
                body=MessageBody(
                    event="push_notification_configured",
                    data=params,
                ),
                protocol_context=bridge_ctx,
            )

        else:
            # Generic A2A method / 通用 A2A 方法
            return AURCMessage(
                source="a2a:external/client",
                target="aurc:local/orchestrator",
                type=MessageDirection.REQUEST,
                body=MessageBody(method=method, params=params),
                protocol_context=bridge_ctx,
                correlation_id=str(msg_id) if msg_id else None,
            )

    async def translate_from_aurc(self, aurc_message: AURCMessage) -> dict:
        """Translate an AURC message to A2A JSON-RPC format.
        将 AURC 消息翻译为 A2A JSON-RPC 格式

        Handles:
        - AURC delegation → A2A tasks/send
        - AURC response → A2A Task result
        - AURC stream → A2A SSE events
        - AURC notification → A2A Task status update
        """
        if aurc_message.type == MessageDirection.DELEGATION:
            body = aurc_message.body
            return {
                "jsonrpc": "2.0",
                "id": aurc_message.correlation_id or aurc_message.message_id,
                "method": "tasks/send",
                "params": {
                    "id": body.params.get("task_id", aurc_message.message_id),
                    "sessionId": body.params.get("session_id", aurc_message.session.session_id),
                    "messages": [
                        {
                            "role": "user",
                            "parts": [
                                {"type": "text", "text": str(body.params.get("content", ""))}
                            ],
                        }
                    ],
                },
            }

        elif aurc_message.type == MessageDirection.RESPONSE:
            body = aurc_message.body
            if body.error:
                # Map to A2A failed state / 映射为 A2A 失败状态
                return {
                    "jsonrpc": "2.0",
                    "id": aurc_message.correlation_id,
                    "result": {
                        "id": body.metadata.get("task_id", ""),
                        "status": {
                            "state": "failed",
                            "message": {
                                "role": "agent",
                                "parts": [{"type": "text", "text": body.error.message}],
                            },
                        },
                    },
                }
            else:
                # Map to A2A completed state / 映射为 A2A 完成状态
                return {
                    "jsonrpc": "2.0",
                    "id": aurc_message.correlation_id,
                    "result": {
                        "id": body.metadata.get("task_id", ""),
                        "status": {"state": "completed"},
                        "artifacts": [
                            {
                                "parts": [
                                    {"type": "text", "text": str(body.result)}
                                ],
                            }
                        ],
                    },
                }

        elif aurc_message.type == MessageDirection.STREAM:
            # A2A SSE event format / A2A SSE 事件格式
            body = aurc_message.body
            return {
                "event": "status-update" if not body.is_final else "artifact-update",
                "data": {
                    "jsonrpc": "2.0",
                    "result": {
                        "id": body.metadata.get("task_id", ""),
                        "status": {
                            "state": "working",
                            "message": {
                                "role": "agent",
                                "parts": [{"type": "text", "text": str(body.data)}],
                            },
                        },
                    },
                },
            }

        elif aurc_message.type == MessageDirection.NOTIFICATION:
            body = aurc_message.body
            # Map AURC events to A2A task states / 将 AURC 事件映射为 A2A 任务状态
            state_map = {
                "task_started": "working",
                "task_paused": "input-required",
                "task_completed": "completed",
                "task_failed": "failed",
                "task_cancelled": "canceled",
            }
            a2a_state = state_map.get(body.event or "", "working")
            return {
                "jsonrpc": "2.0",
                "result": {
                    "id": body.data.get("task_id", "") if body.data else "",
                    "status": {"state": a2a_state},
                },
            }

        return {"jsonrpc": "2.0", "error": {"code": -32601, "message": "Unsupported message type"}}

    async def map_capabilities(self, a2a_skills: list[dict]) -> list[dict]:
        """Map A2A Agent Card skills to AURC skill declarations.
        将 A2A Agent Card 技能映射为 AURC 技能声明
        """
        skills = []
        for skill in a2a_skills:
            skills.append({
                "skill_id": f"a2a:{skill.get('id', skill.get('name', ''))}",
                "name": skill.get("name", ""),
                "description": skill.get("description", ""),
                "input_schema": skill.get("inputModes", {}),
                "output_schema": skill.get("outputModes", {}),
                "tags": ["a2a-bridge"],
            })
        return skills

    def map_agent_card(self, agent_card: dict) -> dict:
        """Convert an A2A Agent Card to an AURC Agent Descriptor dict.
        将 A2A Agent Card 转换为 AURC Agent Descriptor 字典
        """
        return {
            "aurc_id": f"aurc:a2a-bridge/{agent_card.get('name', 'unknown')}:v1.0",
            "display_name": agent_card.get("name", ""),
            "description": agent_card.get("description", ""),
            "capabilities": {
                "provides": [
                    {
                        "skill_id": f"a2a:{s.get('id', s.get('name', ''))}",
                        "name": s.get("name", ""),
                        "description": s.get("description", ""),
                    }
                    for s in agent_card.get("skills", [])
                ],
                "consumes": [],
            },
            "protocols": {
                "native": "aurc/0.1",
                "bridges": ["a2a/1.0"],
            },
            "auth": {
                "methods": agent_card.get("authentication", {}).get("schemes", ["api_key"]),
                "scopes": [],
            },
        }

    @staticmethod
    def _extract_content(messages: list[dict]) -> str:
        """Extract text content from A2A messages."""
        parts = []
        for msg in messages:
            for part in msg.get("parts", []):
                if part.get("type") == "text":
                    parts.append(part.get("text", ""))
        return "\n".join(parts)

    @staticmethod
    def _infer_skill(content: str) -> str:
        """Infer the target skill from message content.
        从消息内容推断目标技能
        """
        # In production, this would use more sophisticated matching / 生产环境中会使用更复杂的匹配
        content_lower = content.lower()
        if any(kw in content_lower for kw in ["research", "search", "find"]):
            return "research"
        if any(kw in content_lower for kw in ["summarize", "summary", "brief"]):
            return "summarize"
        if any(kw in content_lower for kw in ["translate", "translation"]):
            return "translate"
        if any(kw in content_lower for kw in ["code", "program", "implement"]):
            return "code-generation"
        return "general"
