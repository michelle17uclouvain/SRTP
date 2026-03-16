import socket
import threading
import tempfile
import os
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


def create_server_socket(port):
    sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    sock.bind(("::1", port))
    sock.settimeout(5.0)
    return sock


def run_client_with_server(port, server_function, payload):
    ready = threading.Event()

    server_thread = threading.Thread(
        target=server_function,
        args=(port, payload, ready),
        daemon=True
    )

    server_thread.start()
    ready.wait(timeout=2)

    with tempfile.NamedTemporaryFile(delete=False) as f:
        save_path = f.name

    try:
        run_client("::1", port, "/test", save_path)

        with open(save_path, "rb") as f:
            content = f.read()

        return content

    finally:
        os.unlink(save_path)
        server_thread.join(timeout=2)