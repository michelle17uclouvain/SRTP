import sys
import os
import socket

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from helpers import make_data_seg, run_client_with_server_thread

def test_client_ignores_corrupted_packet():
    port = 19923
    content = b"valid data"
    def server_with_corruption(ready):
        sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        sock.bind(("::1", port))
        sock.settimeout(5.0)
        ready.set()
        try:
            _, addr = sock.recvfrom(2048)
            bad = bytearray(make_data_seg(0, content))
            bad[-1] ^= 0x01
            sock.sendto(bytes(bad), addr)
            sock.sendto(make_data_seg(0, content), addr)
            try:
                sock.recvfrom(2048)
            except socket.timeout:
                pass
            sock.sendto(make_data_seg(1, b"", window=0), addr)
        finally:
            sock.close()
    result = run_client_with_server_thread(port, server_with_corruption, file_path="/f")
    assert result == content

def test_client_handles_out_of_order():
    port = 19924
    content1 = b"hello "
    content2 = b"world"

    def server_out_of_order(ready):
        sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        sock.bind(("::1", port))
        sock.settimeout(5.0)
        ready.set()
        try:
            _, addr = sock.recvfrom(2048)
            sock.sendto(make_data_seg(1, content2), addr)
            sock.sendto(make_data_seg(0, content1), addr)
            try:
                sock.recvfrom(2048)
            except socket.timeout:
                pass
            sock.sendto(make_data_seg(2, b"", window=0), addr)
        finally:
            sock.close()
    result = run_client_with_server_thread(port, server_out_of_order, file_path="/f")
    assert result == b"hello world"