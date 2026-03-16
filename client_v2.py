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

    if parsed_url.scheme!="http":
        raise ValueError("l'URL doit commencer par http://")
    
    if not parsed_url.hostname or not parsed_url.port or not parsed_url.path:
        raise ValueError("URL invalide")
    return parsed_url.hostname, parsed_url.port,parsed_url.path

def create_client_socket():
    sock=socket.socket(socket.AF_INET6,socket.SOCK_DGRAM)
    sock.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,0)
    sock.settimeout(TIMEOUT)
    return sock

def resolve_server_address(host, port):
    addr=socket.getaddrinfo(host,port,socket.AF_INET6,socket.SOCK_DGRAM)
    return addr[0][4]

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
    log(f"requette GET envoyé {file_path}")


def receive_data_segment(sock):
    data,addr=sock.recvfrom(MAX_DATAGRAM_SIZE)
    segment=SRTPSegment.decode(data)
    if segment.ptype!=SRTPSegment.PTYPE_DATA:
        raise ValueError("Le serveur foit répondre avec un segment de type DATA")
    
    return segment

def save_file(save_path,content):
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
    log(f"ACKenvoyé pour seq={seqnum}")

def run_client(server_host,server_port,file_path,save_path):
    sock=create_client_socket()
    try:
        server_addr = resolve_server_address(server_host,server_port)
        send_get_request(sock,server_addr,file_path)
        data_segment=receive_data_segment(sock)
        save_file(save_path,data_segment.payload)
        send_ack(sock,server_addr,data_segment.seqnum)

        log("tranfert simple terminé")
    finally:
        sock.close()

def main():
    args=parse_args()
    host,port,path=parse_url(args.url)
    run_client(host,port,path,args.save)


if __name__ == "__main__":
    main()






