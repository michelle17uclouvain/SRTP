import os
import sys
import socket
import tempfile
import threading

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from SRTPSegment import SRTPSegment
from client import run_client


def make_data_segment(seqnum, payload, window=1):
    return SRTPSegment(
        ptype=SRTPSegment.PTYPE_DATA,
        window=window,
        seqnum=seqnum,
        length=len(payload),
        timestamp=123,
        payload=payload,
    )


def make_end_segment(seqnum):
    return SRTPSegment(
        ptype=SRTPSegment.PTYPE_DATA,
        window=0,
        seqnum=seqnum,
        length=0,
        timestamp=123,
        payload=b"",
    )


def mini_server(port, payload, ready, received_acks):
    sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    sock.bind(("::1", port))
    sock.settimeout(5.0)
    ready.set()

    try:
        _, client_addr = sock.recvfrom(2048)

        data_seg = make_data_segment(0, payload)
        sock.sendto(data_seg.encode(), client_addr)

        raw_ack, _ = sock.recvfrom(2048)
        ack = SRTPSegment.decode(raw_ack)
        received_acks.append(ack)

        end_seg = make_end_segment(1)
        sock.sendto(end_seg.encode(), client_addr)

    finally:
        sock.close()


def run_client_with_server(port, payload):
    ready = threading.Event()
    received_acks = []

    server_thread = threading.Thread(
        target=mini_server,
        args=(port, payload, ready, received_acks),
        daemon=True,
    )
    server_thread.start()
    ready.wait(timeout=2)

    with tempfile.NamedTemporaryFile(delete=False) as f:
        save_path = f.name

    try:
        run_client("::1", port, "/test", save_path)

        with open(save_path, "rb") as f:
            content = f.read()

        return content, received_acks

    finally:
        os.unlink(save_path)
        server_thread.join(timeout=2)


def test_step3_simple_transfer():
    payload = b"hello step 3"

    content, received_acks = run_client_with_server(19930, payload)

    assert content == payload
    assert len(received_acks) == 1
    assert received_acks[0].ptype == SRTPSegment.PTYPE_ACK
    assert received_acks[0].length == 0