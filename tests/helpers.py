import os
import threading
import tempfile
import sys
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from SRTPSegment import SRTPSegment

def make_data_seg(seqnum, payload, window=32):
    seg = SRTPSegment(
        ptype=SRTPSegment.PTYPE_DATA,
        window=window,
        seqnum=seqnum % 2048,
        length=len(payload),
        timestamp=seqnum,
        payload=payload,
    )
    return seg.encode()


def make_ack_seg(seqnum, window=32, timestamp=0):
    seg = SRTPSegment(
        ptype=SRTPSegment.PTYPE_ACK,
        window=window,
        seqnum=seqnum % 2048,
        length=0,
        timestamp=timestamp,
        payload=b"",
    )
    return seg.encode()


def run_client_with_server_thread(port, server_func, file_path="/test"):
    ready = threading.Event()
    t = threading.Thread(target=server_func, args=(ready,), daemon=True)
    t.start()
    ready.wait(timeout=2)
    with tempfile.NamedTemporaryFile(delete=False) as f:
        save_path = f.name
    try:
        from client_v2 import run_client
        run_client("::1", port, file_path, save_path)
        with open(save_path, "rb") as f:
             return f.read()
    finally:
        if os.path.exists(save_path):
            os.unlink(save_path)
        t.join(timeout=3)