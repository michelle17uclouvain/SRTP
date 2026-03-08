import socket
import struct
import argparse
import sys
from urllib.parse import urlparse

PTYPE_DATA = 1
PTYPE_ACK  = 2
WINDOW_SIZE = 32
TIMEOUT = 2.0

def build_ack(seq_num):
    first_byte = ((PTYPE_ACK & 0x03) << 6) | (WINDOW_SIZE & 0x3F)
    return struct.pack('!BH', first_byte, seq_num & 0xFFFF)

def build_data(seq_num, payload):
    first_byte = ((PTYPE_DATA & 0x03) << 6) | (WINDOW_SIZE & 0x3F)
    return struct.pack('!BH', first_byte, seq_num & 0xFFFF) + payload

def run_client(server_host, server_port, file_path, save_path):
    sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    sock.settimeout(TIMEOUT)

    try:
        infos = socket.getaddrinfo(server_host, server_port, socket.AF_INET6, socket.SOCK_DGRAM)
        server_address = infos[0][4]
    except socket.gaierror as e:
        print(f"Erreur de résolution DNS : {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Connexion au serveur {server_host}:{server_port}...", file=sys.stderr)

    http_request = f"GET {file_path}\r\n".encode("ascii")
    sock.sendto(build_data(0, http_request), server_address)
    print(f"Requête envoyée : GET {file_path}", file=sys.stderr)

    
    recv_buffer = {}
    next_expected = 0
    received_data = []

    while True:
        try:
            data, address = sock.recvfrom(1500)
        except socket.timeout:
            print("Timeout, renvoi du dernier ACK...", file=sys.stderr)
            sock.sendto(build_ack(next_expected), server_address)
            continue

        # Étape de Décodage 
        try:
            header_first_byte, seq_num = struct.unpack('!BH', data[:3])
            packet_type = (header_first_byte >> 6) & 0x03
            window_size = header_first_byte & 0x3F

            payload = data[3:]

            print(f"Type: {packet_type}, Seq: {seq_num}, Win: {window_size}", file=sys.stderr)
            print(f"Reçu {len(payload)} octets de {address}", file=sys.stderr)

        except Exception as e:
            print(f"Erreur de décodage : {e}", file=sys.stderr)
            continue

        if packet_type != PTYPE_DATA:
            continue

        if len(payload) == 0 and seq_num == next_expected:
            print("Fin de transfert reçue.", file=sys.stderr)
            sock.sendto(build_ack(seq_num + 1), server_address)
            break

        in_window = ((seq_num - next_expected) % 65536) < WINDOW_SIZE
        if not in_window:
            print(f"Paquet seq={seq_num} hors fenêtre, ignoré", file=sys.stderr)
            sock.sendto(build_ack(next_expected), server_address)
            continue

        if seq_num not in recv_buffer:
            recv_buffer[seq_num] = payload

        while next_expected in recv_buffer:
            received_data.append(recv_buffer.pop(next_expected))
            next_expected += 1

        # ACK cumulatif
        sock.sendto(build_ack(next_expected), server_address)

    sock.close()

    # --- Sauvegarde du fichier reçu ---
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