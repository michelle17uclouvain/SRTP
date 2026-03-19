import os
import sys
import threading
import time

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from client import run_client
from server import run_server


def test_step3_simple_transfer(tmp_path):
    root_dir = tmp_path / "files"
    root_dir.mkdir()

    source_file = root_dir / "test.txt"
    source_content = b"hello step 3"
    source_file.write_bytes(source_content)

    save_path = tmp_path / "resultat.txt"

    host = "::1"
    port = 19930

    server_thread = threading.Thread(
        target=run_server,
        args=(host, port, str(root_dir)),
        daemon=True,
    )
    server_thread.start()

    time.sleep(0.5)

    run_client(host, port, "/test.txt", str(save_path))

    assert save_path.exists()
    assert save_path.read_bytes() == source_content