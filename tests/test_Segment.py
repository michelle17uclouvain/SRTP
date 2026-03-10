import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from SRTPSegment import SRTPSegment
import pytest


def test_encode_decode_data_segment():
    payload = b"hello"

    segment = SRTPSegment(
        ptype=SRTPSegment.PTYPE_DATA,
        window=10,
        seqnum=7,
        length=len(payload),
        timestamp=12345,
        payload=payload
    )

    data = segment.encode()
    decoded = SRTPSegment.decode(data)

    assert decoded is not None
    assert decoded.ptype == SRTPSegment.PTYPE_DATA
    assert decoded.window == 10
    assert decoded.seqnum == 7
    assert decoded.length == len(payload)
    assert decoded.timestamp == 12345
    assert decoded.payload == payload


def test_encode_decode_ack_segment():
    segment = SRTPSegment(
        ptype=SRTPSegment.PTYPE_ACK,
        window=3,
        seqnum=12,
        length=0,
        timestamp=999,
        payload=b""
    )

    data = segment.encode()
    decoded = SRTPSegment.decode(data)

    assert decoded is not None
    assert decoded.ptype == SRTPSegment.PTYPE_ACK
    assert decoded.window == 3
    assert decoded.seqnum == 12
    assert decoded.length == 0
    assert decoded.timestamp == 999
    assert decoded.payload == b""


def test_decode_rejects_invalid_crc1():
    segment = SRTPSegment(
        ptype=SRTPSegment.PTYPE_DATA,
        window=10,
        seqnum=7,
        length=5,
        timestamp=12345,
        payload=b"hello"
    )

    raw = bytearray(segment.encode())
    raw[0] ^= 0x01   # on modifie un bit dans le header

    decoded = SRTPSegment.decode(bytes(raw))
    assert decoded is None


def test_decode_rejects_invalid_crc2():
    segment = SRTPSegment(
        ptype=SRTPSegment.PTYPE_DATA,
        window=10,
        seqnum=7,
        length=5,
        timestamp=12345,
        payload=b"hello"
    )

    raw = bytearray(segment.encode())
    raw[12] ^= 0x01   # on modifie un bit dans le payload

    decoded = SRTPSegment.decode(bytes(raw))
    assert decoded is None


def test_decode_rejects_truncated_packet():
    segment = SRTPSegment(
        ptype=SRTPSegment.PTYPE_DATA,
        window=10,
        seqnum=7,
        length=5,
        timestamp=12345,
        payload=b"hello"
    )

    raw = segment.encode()
    truncated = raw[:-2]

    decoded = SRTPSegment.decode(truncated)
    assert decoded is None


def test_encode_rejects_invalid_ptype():
    with pytest.raises(ValueError):
        segment = SRTPSegment(
            ptype=99,
            window=10,
            seqnum=7,
            length=5,
            timestamp=12345,
            payload=b"hello"
        )
        segment.encode()


def test_encode_rejects_invalid_length():
    with pytest.raises(ValueError):
        segment = SRTPSegment(
            ptype=SRTPSegment.PTYPE_DATA,
            window=10,
            seqnum=7,
            length=3,
            timestamp=12345,
            payload=b"hello"
        )
        segment.encode()

def test_encode_rejects_invalid_window():
    with pytest.raises(ValueError):
        segment = SRTPSegment(
            ptype=SRTPSegment.PTYPE_DATA,
            window=100,
            seqnum=7,
            length=5,
            timestamp=12345,
            payload=b"hello"
        )
        segment.encode()


def test_decode_none_returns_none():
    assert SRTPSegment.decode(None) is None

def test_encode_rejects_invalid_seqnum():
    with pytest.raises(ValueError):
        segment = SRTPSegment(
            ptype=SRTPSegment.PTYPE_DATA,
            window=10,
            seqnum=5000,
            length=5,
            timestamp=12345,
            payload=b"hello"
        )
        segment.encode()

def test_encode_rejects_invalid_timestamp():
    with pytest.raises(ValueError):
        segment = SRTPSegment(
            ptype=SRTPSegment.PTYPE_DATA,
            window=10,
            seqnum=7,
            length=5,
            timestamp=0xFFFFFFFF + 1,
            payload=b"hello"
        )
        segment.encode()