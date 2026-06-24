"""AURC Message Codec — serialization and deserialization.
AURC 消息编解码器 — 序列化和反序列化

Supports:
- JSON (canonical, human-readable) / JSON（标准，人类可读）
- MessagePack (high-performance binary) / MessagePack（高性能二进制）
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from ..core.message import AURCMessage

logger = logging.getLogger(__name__)


class CodecError(Exception):
    """Raised on encoding/decoding failures. 编码/解码失败时抛出"""
    pass


class JSONCodec:
    """JSON codec for AURC messages.
    AURC 消息的 JSON 编解码器

    Handles:
    - datetime serialization to ISO 8601 / datetime 序列化为 ISO 8601
    - Pydantic model serialization / Pydantic 模型序列化
    - Pretty printing for debugging / 调试用的美化输出
    """

    @staticmethod
    def encode(message: AURCMessage, pretty: bool = False) -> str:
        """Encode an AURC message to JSON string.
        将 AURC 消息编码为 JSON 字符串

        Args:
            message: The message to encode / 要编码的消息
            pretty: Whether to format with indentation / 是否使用缩进格式化

        Returns:
            JSON string / JSON 字符串
        """
        try:
            data = message.model_dump(mode="json")
            if pretty:
                return json.dumps(data, indent=2, ensure_ascii=False, default=str)
            return json.dumps(data, ensure_ascii=False, default=str)
        except Exception as e:
            raise CodecError(f"Failed to encode message: {e}") from e

    @staticmethod
    def decode(raw: str | bytes) -> AURCMessage:
        """Decode a JSON string to an AURC message.
        将 JSON 字符串解码为 AURC 消息

        Args:
            raw: JSON string or bytes / JSON 字符串或字节

        Returns:
            AURCMessage instance / AURC 消息实例
        """
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            data = json.loads(raw)
            return AURCMessage(**data)
        except json.JSONDecodeError as e:
            raise CodecError(f"Invalid JSON: {e}") from e
        except Exception as e:
            raise CodecError(f"Failed to decode message: {e}") from e

    @staticmethod
    def encode_bytes(message: AURCMessage) -> bytes:
        """Encode to UTF-8 bytes. 编码为 UTF-8 字节"""
        return JSONCodec.encode(message).encode("utf-8")

    @staticmethod
    def encode_batch(messages: list[AURCMessage]) -> str:
        """Encode multiple messages as a JSON array. 将多条消息编码为 JSON 数组"""
        data = [msg.model_dump(mode="json") for msg in messages]
        return json.dumps(data, ensure_ascii=False, default=str)

    @staticmethod
    def decode_batch(raw: str | bytes) -> list[AURCMessage]:
        """Decode a JSON array of messages. 解码 JSON 数组消息"""
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            data_list = json.loads(raw)
            return [AURCMessage(**d) for d in data_list]
        except Exception as e:
            raise CodecError(f"Failed to decode batch: {e}") from e


# =============================================================================
# NDJSON (Newline-Delimited JSON) / 换行分隔 JSON
# =============================================================================


class NDJSONCodec:
    """Newline-Delimited JSON codec — for streaming over stdio.
    换行分隔 JSON 编解码器 — 用于 stdio 流式传输

    Each message is a single JSON line terminated by '\\n'.
    This is the same format used by MCP's stdio transport.
    """

    @staticmethod
    def encode(message: AURCMessage) -> str:
        """Encode a message as a single JSON line. 编码为单行 JSON"""
        return json.dumps(message.model_dump(mode="json"), ensure_ascii=False, default=str) + "\n"

    @staticmethod
    def decode(line: str) -> AURCMessage:
        """Decode a single JSON line. 解码单行 JSON"""
        line = line.strip()
        if not line:
            raise CodecError("Empty NDJSON line")
        return JSONCodec.decode(line)

    @staticmethod
    def encode_stream(messages: list[AURCMessage]) -> str:
        """Encode multiple messages as NDJSON. 将多条消息编码为 NDJSON"""
        return "".join(NDJSONCodec.encode(msg) for msg in messages)

    @staticmethod
    def decode_stream(raw: str) -> list[AURCMessage]:
        """Decode an NDJSON stream. 解码 NDJSON 流"""
        messages = []
        for line in raw.strip().split("\n"):
            line = line.strip()
            if line:
                messages.append(JSONCodec.decode(line))
        return messages


# =============================================================================
# Message Framing / 消息帧
# =============================================================================


class MessageFrame:
    """Message framing for wire transport. 消息帧用于线路传输

    Wraps encoded messages with a simple length-prefix frame:
    [4 bytes: length (big-endian)] [N bytes: payload]

    This enables reliable message boundary detection on streaming transports.
    """

    HEADER_SIZE = 4

    @staticmethod
    def frame(payload: bytes) -> bytes:
        """Add a length-prefix frame to a payload. 为载荷添加长度前缀帧"""
        length = len(payload)
        header = length.to_bytes(MessageFrame.HEADER_SIZE, byteorder="big")
        return header + payload

    @staticmethod
    def unframe(data: bytes) -> tuple[bytes, bytes]:
        """Extract a framed message from a buffer.
        从缓冲区中提取帧消息

        Returns:
            (payload, remaining_buffer)
        """
        if len(data) < MessageFrame.HEADER_SIZE:
            raise CodecError("Incomplete frame header")

        length = int.from_bytes(data[:MessageFrame.HEADER_SIZE], byteorder="big")
        total_needed = MessageFrame.HEADER_SIZE + length

        if len(data) < total_needed:
            raise CodecError(
                f"Incomplete frame: need {total_needed} bytes, have {len(data)}"
            )

        payload = data[MessageFrame.HEADER_SIZE:total_needed]
        remaining = data[total_needed:]
        return payload, remaining

    @staticmethod
    def frame_message(message: AURCMessage) -> bytes:
        """Frame an AURC message for wire transport. 为线路传输帧化 AURC 消息"""
        payload = JSONCodec.encode_bytes(message)
        return MessageFrame.frame(payload)

    @staticmethod
    def unframe_message(data: bytes) -> tuple[AURCMessage, bytes]:
        """Unframe a wire message to an AURC message. 将线路消息解帧为 AURC 消息"""
        payload, remaining = MessageFrame.unframe(data)
        message = JSONCodec.decode(payload)
        return message, remaining
