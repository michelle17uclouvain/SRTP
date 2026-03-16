import argparse
import socket
import sys
import time
from urllib.parse import urlparse

from SRTPSegment import SRTPSegment

TIMEOUT=4.0
MAX_DATAGRAM_SIZE=2048


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

def save_file(save_path,content):
    log(f"CLIENT : sauvegarde du fichier dans : {save_path}")
    with open(save_path,"wb") as f: 
        f.write(content)
    

def build_ack_segment(seqnum):
    return SRTPSegment(
        ptype=SRTPSegment.PTYPE_ACK,
        window=1,
        seqnum=seqnum,
        length=0,
        timestamp=int(time.time()),
        payload=b"",
    )

def send_ack(sock,server_addr,seqnum):
    ack=build_ack_segment(seqnum)
    sock.sendto(ack.encode(),server_addr)
    log(f"CLIENT : ACK envoyé seq={seqnum}")

def run_client(server_host,server_port,file_path,save_path):
    log("CLIENT: lancement du client")
    sock=create_client_socket()
    try:
        server_addr = resolve_server_address(server_host,server_port)
        send_get_request(sock,server_addr,file_path)
        data_segment=receive_data_segment(sock)
        save_file(save_path,data_segment.payload)
        send_ack(sock,server_addr,data_segment.seqnum)

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






