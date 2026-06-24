"""Tests for AURC Message Codec."""

import pytest

from gaiaagent.bus.codec import JSONCodec, NDJSONCodec, MessageFrame, CodecError
from gaiaagent.core.message import AURCMessage, MessageBody
from gaiaagent.core.types import MessageDirection


@pytest.fixture
def sample_message():
    return AURCMessage(
        source="aurc:gaia/orchestrator:v1.0",
        target="aurc:gaia/researcher:v1.0",
        type=MessageDirection.REQUEST,
        body=MessageBody(
            method="invoke",
            skill="deep-research",
            params={"query": "AI protocols"},
        ),
    )


class TestJSONCodec:
    def test_encode_decode_roundtrip(self, sample_message):
        encoded = JSONCodec.encode(sample_message)
        decoded = JSONCodec.decode(encoded)
        assert decoded.source == sample_message.source
        assert decoded.target == sample_message.target
        assert decoded.body.skill == "deep-research"

    def test_encode_pretty(self, sample_message):
        encoded = JSONCodec.encode(sample_message, pretty=True)
        assert "\n" in encoded
        assert "  " in encoded

    def test_encode_bytes(self, sample_message):
        data = JSONCodec.encode_bytes(sample_message)
        assert isinstance(data, bytes)
        decoded = JSONCodec.decode(data)
        assert decoded.source == sample_message.source

    def test_batch_encode_decode(self, sample_message):
        messages = [sample_message, sample_message]
        encoded = JSONCodec.encode_batch(messages)
        decoded = JSONCodec.decode_batch(encoded)
        assert len(decoded) == 2

    def test_decode_invalid_json(self):
        with pytest.raises(CodecError, match="Invalid JSON"):
            JSONCodec.decode("not valid json {{{")

    def test_decode_invalid_schema(self):
        with pytest.raises(CodecError):
            JSONCodec.decode('{"foo": "bar"}')


class TestNDJSONCodec:
    def test_encode_decode(self, sample_message):
        encoded = NDJSONCodec.encode(sample_message)
        assert encoded.endswith("\n")
        decoded = NDJSONCodec.decode(encoded)
        assert decoded.source == sample_message.source

    def test_stream_encode_decode(self, sample_message):
        messages = [sample_message, sample_message, sample_message]
        encoded = NDJSONCodec.encode_stream(messages)
        decoded = NDJSONCodec.decode_stream(encoded)
        assert len(decoded) == 3

    def test_decode_empty_line(self):
        with pytest.raises(CodecError, match="Empty"):
            NDJSONCodec.decode("")


class TestMessageFrame:
    def test_frame_unframe(self):
        payload = b"hello world"
        framed = MessageFrame.frame(payload)
        assert len(framed) == MessageFrame.HEADER_SIZE + len(payload)
        extracted, remaining = MessageFrame.unframe(framed)
        assert extracted == payload
        assert remaining == b""

    def test_frame_with_remaining(self):
        payload = b"test"
        framed = MessageFrame.frame(payload) + b"extra_data"
        extracted, remaining = MessageFrame.unframe(framed)
        assert extracted == payload
        assert remaining == b"extra_data"

    def test_incomplete_header(self):
        with pytest.raises(CodecError, match="Incomplete frame header"):
            MessageFrame.unframe(b"\x00\x00")

    def test_incomplete_payload(self):
        header = (100).to_bytes(4, byteorder="big")  # Claim 100 bytes
        with pytest.raises(CodecError, match="Incomplete frame"):
            MessageFrame.unframe(header + b"short")

    def test_frame_message_roundtrip(self, sample_message):
        framed = MessageFrame.frame_message(sample_message)
        decoded, remaining = MessageFrame.unframe_message(framed)
        assert decoded.source == sample_message.source
        assert decoded.body.skill == "deep-research"
        assert remaining == b""
