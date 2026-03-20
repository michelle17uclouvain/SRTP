import sys
import os
import socket

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from SRTPSegment import SRTPSegment
from helpers import make_data_seg, run_client_with_server_thread


def test_client_receives_file():
    port = 19920
    content = b"hello world"
    def server_simple(ready):
        sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        sock.bind(("::1", port))
        sock.settimeout(5.0)
        ready.set()
        try:
            _, addr = sock.recvfrom(2048)
            sock.sendto(make_data_seg(0, content), addr)

            try:
                sock.recvfrom(2048)
            except socket.timeout:
                pass
            sock.sendto(make_data_seg(1, b"", window=0), addr)
        finally:
            sock.close()
    result = run_client_with_server_thread(port, server_simple)
    assert result == content

def test_client_sends_valid_ack():
    port = 19921
    received_acks = []

    def server_capture(ready):
        sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        sock.bind(("::1", port))
        sock.settimeout(5.0)
        ready.set()
        try:
            _, addr = sock.recvfrom(2048)
            sock.sendto(make_data_seg(0, b"hi"), addr)
            raw, _ = sock.recvfrom(2048)
            received_acks.append(raw)
            sock.sendto(make_data_seg(1, b"", window=0), addr)
        finally:
            sock.close()
    run_client_with_server_thread(port, server_capture, file_path="/f")
    assert len(received_acks) >= 1
    ack = SRTPSegment.decode(received_acks[0])
    assert ack is not None
    assert ack.ptype == SRTPSegment.PTYPE_ACK
    assert ack.length == 0
    assert ack.seqnum == 1