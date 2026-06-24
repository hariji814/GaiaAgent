"""AURC Session Manager — manages conversation sessions between agents.
AURC 会话管理器 — 管理 Agent 之间的对话会话

Responsibilities / 职责:
1. Create and manage sessions / 创建和管理会话
2. Track conversation turns / 追踪对话轮次
3. Session-scoped context / 会话级上下文
4. Session timeout and cleanup / 会话超时和清理
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class SessionState:
    """State of a single session. 单个会话的状态

    Tracks:
    - Participants (source and target agents)
    - Turn count
    - Context data attached to the session
    - Timing information
    """

    def __init__(
        self,
        session_id: str,
        initiator: str,
        conversation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.session_id = session_id
        self.initiator = initiator
        self.conversation_id = conversation_id or f"conv-{uuid.uuid4().hex[:8]}"
        self.participants: set[str] = {initiator}
        self.turn: int = 0
        self.context: dict[str, Any] = {}
        self.metadata: dict[str, Any] = metadata or {}
        self.created_at: datetime = datetime.now(timezone.utc)
        self.last_activity: datetime = self.created_at
        self._is_active: bool = True

    @property
    def is_active(self) -> bool:
        return self._is_active

    def next_turn(self) -> int:
        """Increment and return the turn number. 递增并返回轮次号"""
        self.turn += 1
        self.last_activity = datetime.now(timezone.utc)
        return self.turn

    def add_participant(self, agent_id: str) -> None:
        """Add a participant to this session. 添加参与者"""
        self.participants.add(agent_id)
        self.last_activity = datetime.now(timezone.utc)

    def set_context(self, key: str, value: Any) -> None:
        """Set session-scoped context data. 设置会话级上下文数据"""
        self.context[key] = value
        self.last_activity = datetime.now(timezone.utc)

    def get_context(self, key: str, default: Any = None) -> Any:
        """Get session-scoped context data. 获取会话级上下文数据"""
        return self.context.get(key, default)

    def close(self) -> None:
        """Mark this session as closed. 标记会话为已关闭"""
        self._is_active = False
        self.last_activity = datetime.now(timezone.utc)

    @property
    def duration_seconds(self) -> float:
        """Session duration in seconds. 会话持续时间（秒）"""
        return (self.last_activity - self.created_at).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "initiator": self.initiator,
            "conversation_id": self.conversation_id,
            "participants": list(self.participants),
            "turn": self.turn,
            "is_active": self._is_active,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "duration_seconds": self.duration_seconds,
        }


class SessionManager:
    """Manages conversation sessions between agents.
    管理 Agent 之间的对话会话

    Usage / 用法:
        manager = SessionManager()

        # Create a session / 创建会话
        session = manager.create_session("aurc:gaia/orchestrator:v1.0")

        # Advance turn / 推进轮次
        turn = manager.advance_turn(session.session_id)

        # Add participants / 添加参与者
        manager.add_participant(session.session_id, "aurc:gaia/researcher:v1.0")

        # Session context / 会话上下文
        manager.set_context(session.session_id, "search_results", [...])

        # Lookup / 查找
        session = manager.get_session(session.session_id)
        active = manager.get_active_sessions()

        # Cleanup / 清理
        manager.close_session(session.session_id)
        manager.cleanup_stale(max_age_seconds=3600)
    """

    def __init__(self, max_sessions: int = 10000) -> None:
        self._sessions: dict[str, SessionState] = {}
        self._conversation_sessions: dict[str, list[str]] = {}  # conv_id → [session_ids]
        self._max_sessions = max_sessions

    # =========================================================================
    # Session Lifecycle / 会话生命周期
    # =========================================================================

    def create_session(
        self,
        initiator: str,
        conversation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SessionState:
        """Create a new session.
        创建新会话

        Args:
            initiator: The agent initiating the session / 发起会话的 Agent
            conversation_id: Optional conversation ID for grouping / 可选的对话分组 ID
            metadata: Optional metadata / 可选元数据

        Returns:
            The new SessionState
        """
        # Enforce max sessions / 强制最大会话数
        if len(self._sessions) >= self._max_sessions:
            self._evict_oldest()

        session_id = f"session-{uuid.uuid4().hex[:12]}"
        session = SessionState(
            session_id=session_id,
            initiator=initiator,
            conversation_id=conversation_id,
            metadata=metadata,
        )
        self._sessions[session_id] = session

        # Index by conversation / 按对话索引
        conv_id = session.conversation_id
        if conv_id not in self._conversation_sessions:
            self._conversation_sessions[conv_id] = []
        self._conversation_sessions[conv_id].append(session_id)

        logger.debug("Session created: %s (initiator: %s)", session_id, initiator)
        return session

    def close_session(self, session_id: str) -> None:
        """Close a session. 关闭会话"""
        session = self._sessions.get(session_id)
        if session:
            session.close()
            logger.debug("Session closed: %s", session_id)

    def get_session(self, session_id: str) -> SessionState | None:
        """Get a session by ID. 通过 ID 获取会话"""
        return self._sessions.get(session_id)

    def get_conversation_sessions(self, conversation_id: str) -> list[SessionState]:
        """Get all sessions in a conversation. 获取对话中的所有会话"""
        session_ids = self._conversation_sessions.get(conversation_id, [])
        return [
            self._sessions[sid]
            for sid in session_ids
            if sid in self._sessions
        ]

    # =========================================================================
    # Turn Management / 轮次管理
    # =========================================================================

    def advance_turn(self, session_id: str, participant: str | None = None) -> int:
        """Advance the session turn counter.
        推进会话轮次计数器

        Args:
            session_id: Session ID / 会话 ID
            participant: Agent ID of the turn participant / 本轮参与的 Agent ID

        Returns:
            The new turn number / 新轮次号
        """
        session = self._sessions.get(session_id)
        if not session:
            raise KeyError(f"Session '{session_id}' not found")
        if not session.is_active:
            raise RuntimeError(f"Session '{session_id}' is closed")

        if participant:
            session.add_participant(participant)
        return session.next_turn()

    # =========================================================================
    # Session Context / 会话上下文
    # =========================================================================

    def set_context(self, session_id: str, key: str, value: Any) -> None:
        """Set context data on a session. 设置会话上下文数据"""
        session = self._sessions.get(session_id)
        if not session:
            raise KeyError(f"Session '{session_id}' not found")
        session.set_context(key, value)

    def get_context(self, session_id: str, key: str, default: Any = None) -> Any:
        """Get context data from a session. 获取会话上下文数据"""
        session = self._sessions.get(session_id)
        if not session:
            return default
        return session.get_context(key, default)

    # =========================================================================
    # Queries / 查询
    # =========================================================================

    def get_active_sessions(self) -> list[SessionState]:
        """Get all active sessions. 获取所有活跃会话"""
        return [s for s in self._sessions.values() if s.is_active]

    def get_sessions_by_participant(self, agent_id: str) -> list[SessionState]:
        """Get all sessions an agent participates in. 获取 Agent 参与的所有会话"""
        return [s for s in self._sessions.values() if agent_id in s.participants]

    @property
    def session_count(self) -> int:
        return len(self._sessions)

    @property
    def active_count(self) -> int:
        return len(self.get_active_sessions())

    # =========================================================================
    # Cleanup / 清理
    # =========================================================================

    def cleanup_stale(self, max_age_seconds: float = 3600) -> int:
        """Remove stale sessions older than max_age_seconds.
        清理超过 max_age_seconds 的陈旧会话

        Returns:
            Number of sessions removed / 移除的会话数
        """
        now = datetime.now(timezone.utc)
        to_remove = []

        for sid, session in self._sessions.items():
            if not session.is_active:
                age = (now - session.last_activity).total_seconds()
                if age > max_age_seconds:
                    to_remove.append(sid)

        for sid in to_remove:
            session = self._sessions.pop(sid)
            # Clean up conversation index / 清理对话索引
            conv_id = session.conversation_id
            if conv_id in self._conversation_sessions:
                try:
                    self._conversation_sessions[conv_id].remove(sid)
                except ValueError:
                    pass

        if to_remove:
            logger.info("Cleaned up %d stale sessions", len(to_remove))
        return len(to_remove)

    def _evict_oldest(self) -> None:
        """Evict the oldest inactive session. 驱逐最旧的未活跃会话"""
        oldest_id = None
        oldest_time = None

        for sid, session in self._sessions.items():
            if not session.is_active:
                if oldest_time is None or session.last_activity < oldest_time:
                    oldest_id = sid
                    oldest_time = session.last_activity

        if oldest_id:
            self._sessions.pop(oldest_id)
        else:
            # All sessions active — evict oldest by creation time / 全部活跃则按创建时间驱逐
            if self._sessions:
                oldest_id = min(
                    self._sessions,
                    key=lambda sid: self._sessions[sid].created_at,
                )
                self._sessions.pop(oldest_id)
