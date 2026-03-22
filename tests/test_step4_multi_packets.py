import sys
import os
import socket
import time

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from helpers import make_data_seg, run_client_with_server_thread

def test_client_receives_file_with_latency():
    port = 19922
    content = b"Y" * 3000

    def server_with_latency(ready):
        sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        sock.bind(("::1", port))
        sock.settimeout(5.0)
        ready.set()
        try:
            _, addr = sock.recvfrom(2048)
            blocks = [content[i:i + 1024] for i in range(0, len(content), 1024)]
            for seq, block in enumerate(blocks):
                time.sleep(0.2)
                sock.sendto(make_data_seg(seq, block), addr)
                try:
                    sock.recvfrom(2048)
                except socket.timeout:
                    pass
            time.sleep(0.2)
            sock.sendto(make_data_seg(len(blocks), b"", window=0), addr)
        finally:
            sock.close()

    result = run_client_with_server_thread(port, server_with_latency)
    assert result == content