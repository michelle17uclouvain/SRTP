import socket
import argparse
import sys
import time
from urllib.parse import urlparse
from SRTPSegment import SRTPSegment

WINDOW_SIZE = 32
TIMEOUT = 2.0


def send_ack(sock, address, next_seq, last_timestamp=0):
    seg = SRTPSegment(
        ptype=SRTPSegment.PTYPE_ACK,
        window=WINDOW_SIZE,
        seqnum=next_seq % 2048,
        length=0,
        timestamp=last_timestamp,
        payload=b"",
    )
    sock.sendto(seg.encode(), address)


def run_client(server_host, server_port, file_path, save_path):
    sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    sock.settimeout(TIMEOUT)

    try:
        infos = socket.getaddrinfo(server_host, server_port, socket.AF_INET6, socket.SOCK_DGRAM)
        server_address = infos[0][4]
    except socket.gaierror as e:
        print(f"Erreur de résolution DNS : {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Connexion au serveur {server_host}:{server_port}...", file=sys.stderr)

    http_request = f"GET {file_path}\r\n".encode("ascii")
    timestamp = int(time.time() * 1000) & 0xFFFFFFFF
    req_seg = SRTPSegment(
        ptype=SRTPSegment.PTYPE_DATA,
        window=WINDOW_SIZE,
        seqnum=0,
        length=len(http_request),
        timestamp=timestamp,
        payload=http_request,
    )
    sock.sendto(req_seg.encode(), server_address)
    print(f"Requête envoyée : GET {file_path}", file=sys.stderr)

    recv_buffer = {}
    next_expected = 0
    received_data = []

    while True:
        try:
            data, address = sock.recvfrom(2048)
        except socket.timeout:
            print("Timeout, renvoi du dernier ACK...", file=sys.stderr)
            send_ack(sock, server_address, next_expected % 2048)
            continue

        seg = SRTPSegment.decode(data)
        if seg is None:
            print("Paquet invalide reçu, ignoré.", file=sys.stderr)
            continue

        if seg.ptype != SRTPSegment.PTYPE_DATA:
            continue

        print(f"Reçu DATA seq={seg.seqnum}, len={seg.length}", file=sys.stderr)

        if seg.length == 0 and seg.seqnum == next_expected % 2048:
            print("Fin de transfert reçue.", file=sys.stderr)
            send_ack(sock, server_address, (next_expected + 1) % 2048, last_timestamp=seg.timestamp)
            break

        in_window = ((seg.seqnum - next_expected % 2048) % 2048) < WINDOW_SIZE
        if not in_window:
            print(f"Paquet seq={seg.seqnum} hors fenêtre, ignoré.", file=sys.stderr)
            send_ack(sock, server_address, next_expected % 2048)
            continue

        if seg.seqnum not in recv_buffer:
            recv_buffer[seg.seqnum] = seg.payload

        while next_expected % 2048 in recv_buffer:
            received_data.append(recv_buffer.pop(next_expected % 2048))
            next_expected += 1

        send_ack(sock, server_address, next_expected % 2048, last_timestamp=seg.timestamp)

    sock.close()

    file_content = b"".join(received_data)
    try:
        with open(save_path, "wb") as f:
            f.write(file_content)
        print(f"Fichier sauvegardé dans '{save_path}' ({len(file_content)} octets)", file=sys.stderr)
    except IOError as e:
        print(f"Erreur lors de la sauvegarde : {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Client SRTP")
    parser.add_argument("url", help="http://hostname:port/path/to/file")
    parser.add_argument("--save", default="llm.model", help="Chemin de sauvegarde (défaut: llm.model)")
    args = parser.parse_args()

    parsed = urlparse(args.url)
    if parsed.scheme != "http":
        print("Erreur : l'URL doit commencer par http://", file=sys.stderr)
        sys.exit(1)

    run_client(parsed.hostname, parsed.port, parsed.path or "/", args.save)