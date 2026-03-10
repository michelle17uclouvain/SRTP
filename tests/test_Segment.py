import sys
import os
import socket
import threading
import tempfile

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
def _make_data_seg(seqnum, payload, window=32):
    seg = SRTPSegment(
        ptype=SRTPSegment.PTYPE_DATA,
        window=window,
        seqnum=seqnum % 2048,
        length=len(payload),
        timestamp=seqnum,
        payload=payload,
    )
    return seg.encode()

def _mini_server(port, file_content, ready_event):
    sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    sock.bind(("::1", port))
    sock.settimeout(5.0)
    ready_event.set()
    try:
        _, addr = sock.recvfrom(2048)
        blocks = [file_content[i:i+1024] for i in range(0, max(len(file_content), 1), 1024)]
        for seq, block in enumerate(blocks):
            sock.sendto(_make_data_seg(seq, block), addr)
            try:
                sock.recvfrom(2048)
            except socket.timeout:
                pass
        sock.sendto(_make_data_seg(len(blocks), b"", window=0), addr)
    except socket.timeout:
        pass
    finally:
        sock.close()

def _run_client(port, content):
    ready = threading.Event()
    t = threading.Thread(target=_mini_server, args=(port, content, ready), daemon=True)
    t.start()
    ready.wait(timeout=2)
    with tempfile.NamedTemporaryFile(delete=False) as f:
        save_path = f.name
    try:
        from client import run_client
        run_client("::1", port, "/test", save_path)
        with open(save_path, "rb") as f:
            return f.read()
    finally:
        os.unlink(save_path)
        t.join(timeout=3)

def test_client_receives_file():
    """Le client reçoit correctement un fichier (plusieurs blocs)."""
    content = b"Y" * 3000
    assert _run_client(19920, content) == content

def test_client_sends_valid_ack():
    """Le client répond avec un ACK SRTP valide après réception d'un paquet DATA."""
    port = 19921
    received_acks = []
    ready = threading.Event()

    def server_capture(ready):
        sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        sock.bind(("::1", port))
        sock.settimeout(5.0)
        ready.set()
        try:
            _, addr = sock.recvfrom(2048)
            sock.sendto(_make_data_seg(0, b"hi"), addr)
            raw, _ = sock.recvfrom(2048)
            received_acks.append(raw)
            sock.sendto(_make_data_seg(1, b"", window=0), addr)
        except socket.timeout:
            pass
        finally:
            sock.close()

    t = threading.Thread(target=server_capture, args=(ready,), daemon=True)
    t.start()
    ready.wait(timeout=2)
    with tempfile.NamedTemporaryFile(delete=False) as f:
        save_path = f.name
    try:
        from client import run_client
        run_client("::1", port, "/f", save_path)
    finally:
        os.unlink(save_path)
        t.join(timeout=3)

    assert len(received_acks) >= 1
    ack = SRTPSegment.decode(received_acks[0])
    assert ack is not None
    assert ack.ptype == SRTPSegment.PTYPE_ACK
    assert ack.length == 0

def test_client_ignores_corrupted_packet():
    """Le client ignore un paquet corrompu et reçoit quand même les données valides."""
    port = 19922
    content = b"valid data"
    ready = threading.Event()

    def server_with_corruption(ready):
        sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        sock.bind(("::1", port))
        sock.settimeout(5.0)
        ready.set()
        try:
            _, addr = sock.recvfrom(2048)
            sock.sendto(b"\x00" * 12, addr)
            sock.sendto(_make_data_seg(0, content), addr)
            sock.recvfrom(2048)
            sock.sendto(_make_data_seg(1, b"", window=0), addr)
        except socket.timeout:
            pass
        finally:
            sock.close()

    t = threading.Thread(target=server_with_corruption, args=(ready,), daemon=True)
    t.start()
    ready.wait(timeout=2)
    with tempfile.NamedTemporaryFile(delete=False) as f:
        save_path = f.name
    try:
        from client import run_client
        run_client("::1", port, "/f", save_path)
        with open(save_path, "rb") as f:
            result = f.read()
        assert result == content
    finally:
        os.unlink(save_path)
        t.join(timeout=3)