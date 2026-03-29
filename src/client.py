import argparse
import socket
import sys
import time
from urllib.parse import urlparse

from SRTPSegment import SRTPSegment

TIMEOUT=4.0
MAX_DATAGRAM_SIZE=2048
WINDOWS_SIZE=63
SEQ_MOD=2048


def log(message):
    print(message,file=sys.stderr)

def parse_args():
    parser=argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--save",default="llm.model")
    return parser.parse_args()


def parse_url(url):
    parsed_url=urlparse(url)
    log(f"CLIENT : analyse de l'URL : {url}")
    if parsed_url.scheme!="http":
        raise ValueError("l'URL doit commencer par http://")
    if not parsed_url.hostname or not parsed_url.port or not parsed_url.path:
        raise ValueError("URL invalide")
    log(f"CLIENT: host={parsed_url.hostname}, port={parsed_url.port}, path={parsed_url.path}")
    return parsed_url.hostname, parsed_url.port,parsed_url.path

def create_client_socket():
    log("CLIENT : creation du socket ")
    sock=socket.socket(socket.AF_INET6,socket.SOCK_DGRAM)
    sock.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,0)
    sock.settimeout(TIMEOUT)
    return sock

def resolve_server_address(host, port):
    log(f"CLIENT:resolution de l'adresse du serveur  {host}:{port}")
    server_info=socket.getaddrinfo(host,port,socket.AF_INET6,socket.SOCK_DGRAM)
    server_addr = server_info[0][4]
    log(f"CLIENT: adresse resolue : {server_addr}")
    return server_addr

def build_get_segment(file_path):
    payload=f"GET {file_path}".encode("ascii")
    return SRTPSegment(
        ptype=SRTPSegment.PTYPE_DATA,
        window=WINDOWS_SIZE,
        seqnum=0,
        length=len(payload),
        timestamp=int(time.time()),
        payload=payload,
    )

def send_get_request(sock,server_addr,file_path):
    segment=build_get_segment(file_path)
    sock.sendto(segment.encode(),server_addr)
    log(f"CLIENT : requette GET envoyé {file_path}")
    log(f"CLIENT Segment envoyé : seq={segment.seqnum}, length={segment.length}")


def receive_data_segment(sock, server_addr):
    log("CLIENT : en attente d'un segment DATA..")
    data, addr = sock.recvfrom(MAX_DATAGRAM_SIZE)
    log(f"CLIENT : datagramme recu de {addr}, taille={len(data)} octet")
    if addr != server_addr:
        raise ValueError("segment reçu d'une autre adresse")
    try :
        segment = SRTPSegment.decode(data)
    except Exception:
        raise ValueError("segment invalide")
    if segment is None:
        raise ValueError("segment invalide")
    if segment.ptype != SRTPSegment.PTYPE_DATA:
        raise ValueError("Le serveur doit répondre avec un segment de type DATA")
    return segment

def get_receive_window(recv_buffer):
    free_slots = WINDOWS_SIZE - len(recv_buffer)
    return max(0, min(63, free_slots))

def save_file(save_path,content):
    log(f"CLIENT : sauvegarde du fichier dans : {save_path}")
    with open(save_path,"wb") as f: 
        f.write(content)

def encode_sack_payload(out_of_order_seqnums):
    """Encode une liste de seqnums hors-séquence en payload SACK (11 bits par seqnum, paddé à multiple de 4 octets)."""
    bits = []
    for seq in out_of_order_seqnums[:744]:  # max 744 seqnums dans 1024 octets
        for bit_pos in range(10, -1, -1):   # 11 bits MSB first
            bits.append((seq >> bit_pos) & 1)
    # padding pour arriver à un multiple de 32 bits (4 octets)
    while len(bits) % 32 != 0:
        bits.append(0)
    payload = bytearray()
    for i in range(0, len(bits), 8):
        byte = 0
        for b in bits[i:i+8]:
            byte = (byte << 1) | b
        payload.append(byte)
    return bytes(payload)

def build_ack_segment(next_expected, recv_buffer, last_timestamp):
    out_of_order = sorted(recv_buffer.keys())
    if not out_of_order:
        # pas de paquet hors-séquence → ACK simple
        return SRTPSegment(
            ptype=SRTPSegment.PTYPE_ACK,
            window=get_receive_window(recv_buffer),
            seqnum=next_expected % SEQ_MOD,
            length=0,
            timestamp=last_timestamp,
            payload=b"",
        )
    # paquets hors-séquence présents → SACK
    payload = encode_sack_payload(out_of_order)
    return SRTPSegment(
        ptype=SRTPSegment.PTYPE_SACK,
        window=get_receive_window(recv_buffer),
        seqnum=next_expected % SEQ_MOD,
        length=len(payload),
        timestamp=last_timestamp,
        payload=payload,
    )

def send_ack(sock, server_addr, next_expected, recv_buffer, last_timestamp):
    ack = build_ack_segment(next_expected, recv_buffer, last_timestamp)
    ptype_str = "SACK" if ack.ptype == SRTPSegment.PTYPE_SACK else "ACK"
    log(f"CLIENT: {ptype_str} envoyé, seqnum={ack.seqnum}, hors-séquence={sorted(recv_buffer.keys())}")
    sock.sendto(ack.encode(), server_addr)

def is_in_window(seqnum,next_expected):
     return ((seqnum - next_expected) % SEQ_MOD) < WINDOWS_SIZE

def empty_buffer(recv_buffer,next_expected,file_content):
    finished=False
    last_timestamp=0
    while next_expected in recv_buffer:
        segment=recv_buffer.pop(next_expected)
        last_timestamp=segment.timestamp
        if segment.length==0:
            finished=True
            next_expected=(next_expected +1)%SEQ_MOD
            break
        file_content.extend(segment.payload)
        next_expected=(next_expected+1)%SEQ_MOD
    return next_expected,finished,last_timestamp


def receive_file(sock, server_addr,file_path):
    file_content = bytearray()
    recv_buffer = {}
    next_expected = 0
    while True:
        try:
            segment = receive_data_segment(sock, server_addr)
        except socket.timeout:
            log("CLIENT: timeout de reception")
            if next_expected == 0 and not recv_buffer:
                log("CLIENT: retransmission GET")
                send_get_request(sock, server_addr, file_path)
            continue
        except (ValueError, OSError):
            log("CLIENT: paquet invalide ignore")
            continue

        log(f"CLIENT: segment DATA reçu seq={segment.seqnum}, length={segment.length}")

        # paquet attendu
        if segment.seqnum == next_expected:
            if segment.length == 0:
                log("CLIENT: fin de transfert")
                next_expected = (next_expected + 1) % SEQ_MOD
                send_ack(sock, server_addr, next_expected, recv_buffer, segment.timestamp)
                break

            file_content.extend(segment.payload)
            next_expected = (next_expected + 1) % SEQ_MOD
            next_expected, finished, _ = empty_buffer(recv_buffer, next_expected, file_content)
            send_ack(sock, server_addr, next_expected, recv_buffer, segment.timestamp)

            if finished:
                log("CLIENT: fin de transfert venu du buffer")
                break
            continue

        # paquet en avance mais encore dans la fenetre
        if is_in_window(segment.seqnum, next_expected):
            if segment.seqnum not in recv_buffer:
                recv_buffer[segment.seqnum] = segment
                log(f"CLIENT: segment pas en ordre stocke seq={segment.seqnum}")
            else:
                log(f"CLIENT: doublon dans le buffer seq={segment.seqnum}")

            send_ack(sock, server_addr, next_expected, recv_buffer, segment.timestamp)
            continue

        # paquet ddeja recu ou ancien paquet on renvoit l'ack en cours
        if ((next_expected - segment.seqnum) % SEQ_MOD) < WINDOWS_SIZE:
            log(f"CLIENT: doublon reçu seq={segment.seqnum}, ACK répété seq={next_expected}")
            send_ack(sock, server_addr, next_expected, recv_buffer, segment.timestamp)
            continue

        # paquet totalement hors fenêtre
        log(f"CLIENT: segment ignoré seq={segment.seqnum}")

    return bytes(file_content)


def run_client(server_host,server_port,file_path,save_path):
    log("CLIENT: lancement du client")
    sock=create_client_socket()
    try:
        server_addr = resolve_server_address(server_host,server_port)
        send_get_request(sock,server_addr,file_path)
        content=receive_file(sock,server_addr,file_path)
        save_file(save_path,content)
        log("CLIENT : tranfert simple terminé")
    finally:
        sock.close()
        log("CLIENT : fermerture du socket ")

def main():
    args=parse_args()
    host,port,path=parse_url(args.url)
    run_client(host,port,path,args.save)


if __name__ == "__main__":
    main()