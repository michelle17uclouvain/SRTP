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
    log(f"CLIENT:  Résolution de l'adresse du serveur  {host}:{port}")
    server_addr=socket.getaddrinfo(host,port,socket.AF_INET6,socket.SOCK_DGRAM)
    log(f"[CLIENT: adresse resolue : {server_addr}")
    return server_addr[0][4]

def build_get_segment(file_path):
    payload=f"GET {file_path}".encode("ascii")
    return SRTPSegment(
        ptype=SRTPSegment.PTYPE_DATA,
        window=1,
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


def receive_data_segment(sock):
    log("CLIENT : en attente d'un segment DATA..")
    data,addr=sock.recvfrom(MAX_DATAGRAM_SIZE)
    log(f"CLIENT : datagramme recu de {addr}, taille={len(data)} octet")
    segment=SRTPSegment.decode(data)
    if segment.ptype!=SRTPSegment.PTYPE_DATA:
        raise ValueError("Le serveur foit répondre avec un segment de type DATA")
    return segment

def get_receive_window(recv_buffer):
    return WINDOWS_SIZE-len(recv_buffer)

def receive_file(sock, server_addr):
    file_content = bytearray()
    recv_buffer = {}
    next_expected = 0

    while True:
        try:
            segment = receive_data_segment(sock)
        except socket.timeout:
            log(f"CLIENT: timeout de réception")
            continue
        except (ValueError, OSError):
            log(f"CLIENT: paquet invalide ignore")
            continue
        log(f"CLIENT: segment DATA reçu seq={segment.seqnum}, length={segment.length}")

        #paquet attendu
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
        #paquet pas en ordre mais dans la fenetre donc on accepte 
        if is_in_window(segment.seqnum, next_expected):
            if segment.seqnum not in recv_buffer:
                recv_buffer[segment.seqnum] = segment
                log(f"CLIENT: segment pas en  ordre stocke seq={segment.seqnum}")

            send_ack(sock, server_addr, next_expected, recv_buffer, segment.timestamp)
            continue

        #paquet qui n'est pas dans la fenete
        log(f"CLIENT: segment ignoré seq={segment.seqnum}")

    return bytes(file_content)

def save_file(save_path,content):
    log(f"CLIENT : sauvegarde du fichier dans : {save_path}")
    with open(save_path,"wb") as f: 
        f.write(content)
    

def build_ack_segment(next_expected,recv_buffer,last_timestamp):
    return SRTPSegment(
        ptype=SRTPSegment.PTYPE_ACK,
        window=get_receive_window(recv_buffer),
        seqnum=next_expected%SEQ_MOD,
        length=0,
        timestamp=int(last_timestamp),
        payload=b"",
    )
def build_sack_segment(seqnum,payload):
    return None

def send_ack(sock,server_addr,next_expected, recv_buffer, last_timestamp):
    ack=build_ack_segment(next_expected,recv_buffer,last_timestamp)
    sock.sendto(ack.encode(),server_addr)
    log(f"CLIENT : ACK envoyé seq={next_expected}, window={ack.window}")

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


def run_client(server_host,server_port,file_path,save_path):
    log("CLIENT: lancement du client")
    sock=create_client_socket()
    try:
        server_addr = resolve_server_address(server_host,server_port)
        send_get_request(sock,server_addr,file_path)
        content=receive_file(sock,server_addr)
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






