import socket
import argparse
import sys
import os
import time
from srtpsegment import SRTPSegment

WINDOW_SIZE = 32
TIMEOUT = 2.0


def make_data(seqnum, payload, window=WINDOW_SIZE):
    timestamp = int(time.time() * 1000) & 0xFFFFFFFF
    seg = SRTPSegment(
        ptype=SRTPSegment.PTYPE_DATA,
        window=window,
        seqnum=seqnum % 2048,
        length=len(payload),
        timestamp=timestamp,
        payload=payload,
    )
    return seg.encode()


def run_server(hostname, port, root_dir):
    sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)

    try:
        infos = socket.getaddrinfo(hostname, port, socket.AF_INET6, socket.SOCK_DGRAM)
        bind_address = infos[0][4]
    except socket.gaierror as e:
        print(f"Erreur de résolution : {e}", file=sys.stderr)
        sys.exit(1)

    sock.bind(bind_address)
    print(f"Serveur SRTP en attente sur {hostname}:{port}...", file=sys.stderr)

    while True:
        try:
            data, client_address = sock.recvfrom(2048)
        except KeyboardInterrupt:
            print("Serveur arrêté.", file=sys.stderr)
            break

        seg = SRTPSegment.decode(data)
        if seg is None:
            print("Paquet invalide reçu, ignoré.", file=sys.stderr)
            continue

        if seg.ptype != SRTPSegment.PTYPE_DATA:
            print("Paquet non-DATA reçu, ignoré.", file=sys.stderr)
            continue

        try:
            request = seg.payload.decode("ascii").strip()
        except Exception:
            print("Requête non-ASCII, ignorée.", file=sys.stderr)
            continue

        print(f"Requête reçue de {client_address}: {request}", file=sys.stderr)

        if not request.startswith("GET "):
            print("Requête invalide.", file=sys.stderr)
            continue

        file_path = request[4:].strip().lstrip("/")
        full_path = os.path.join(root_dir, file_path)
        print(f"Fichier demandé : {full_path}", file=sys.stderr)

        if not os.path.isfile(full_path):
            print(f"Fichier non trouvé : {full_path}", file=sys.stderr)
            sock.sendto(make_data(0, b"", window=0), client_address)
            continue

        with open(full_path, "rb") as f:
            file_data = f.read()

        print(f"Envoi de {len(file_data)} octets...", file=sys.stderr)

        blocks = [file_data[i:i+1024] for i in range(0, len(file_data), 1024)]
        if not blocks:
            blocks = [b""]

        sock.settimeout(TIMEOUT)

        client_window = 1
        acked_up_to = 0
        i = 0

        while acked_up_to < len(blocks):
            while i < len(blocks) and i < acked_up_to + client_window:
                sock.sendto(make_data(i, blocks[i]), client_address)
                print(f"Envoyé bloc seq={i % 2048}", file=sys.stderr)
                i += 1

            try:
                raw, _ = sock.recvfrom(2048)
            except socket.timeout:
                print("Timeout, retransmission...", file=sys.stderr)
                i = acked_up_to
                continue

            ack_seg = SRTPSegment.decode(raw)
            if ack_seg is None:
                continue
            if ack_seg.ptype not in (SRTPSegment.PTYPE_ACK, SRTPSegment.PTYPE_SACK):
                continue

            client_window = max(1, ack_seg.window)
            new_ack = ack_seg.seqnum

            expected_seqnum = acked_up_to % 2048
            diff = (new_ack - expected_seqnum) % 2048
            if diff > 0:
                acked_up_to += diff
                i = max(i, acked_up_to)
                print(f"ACK reçu : seqnum={new_ack}, acked_up_to={acked_up_to}", file=sys.stderr)

        sock.sendto(make_data(acked_up_to, b"", window=0), client_address)
        print("Transfert terminé.", file=sys.stderr)
        sock.settimeout(None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Serveur SRTP")
    parser.add_argument("hostname", help="Adresse IPv6 d'écoute (ex: ::1)")
    parser.add_argument("port", type=int, help="Port UDP")
    parser.add_argument("--root", default=".", help="Dossier racine (défaut: .)")
    args = parser.parse_args()

    run_server(args.hostname, args.port, args.root)