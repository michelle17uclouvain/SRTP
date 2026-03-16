import argparse
import os
import socket
import sys
import time 


from SRTPSegment import SRTPSegment

MAX_DATAGRAM_SIZE=2048

def log(message):
    print(message,file=sys.stderr)


def parse_args():
    parser=argparse.ArgumentParser()
    parser.add_argument("host")
    parser.add_argument("port",type=int)
    parser.add_argument("--root",default=".")
    return parser.parse_args()


def create_server_socket(host, port):
    log(f"SERVER : creation du socket UDP sur [{host}]:{port}")
    sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    sock.bind((host, port))
    return sock

def receive_request(sock):
    log("SERVER : en attente d'une requête client...")
    data,client_addr=sock.recvfrom(MAX_DATAGRAM_SIZE)
    log(f"SERVER:segment reçu de {client_addr}, taille={len(data)} ")
    segment=SRTPSegment.decode(data)
    if(segment.ptype!=SRTPSegment.PTYPE_DATA):
        raise ValueError("le client doit envoyer un segment de type DATA")
    return segment, client_addr


def extract_full_path(segment,root_dir):
    try:
        request=segment.payload.decode("ascii")
    except UnicodeDecodeError:
        raise ValueError("La requête du client n'est pas en ascii")
    log(f"SERVER: requette reçue : {request!r}")
    
    if not request.startswith("GET "):
        raise ValueError("Requête doit commencer par GET")
    
    file_path=request[4:].strip()

    if not file_path.startswith("/"):
        raise ValueError("Le chemin doit commencer par /")
    
    safe_path = os.path.normpath(file_path.lstrip("/"))
    full_path = os.path.join(root_dir, safe_path)
    log(f"SERVER: Chemin résolu : {full_path}")
    return full_path

def read_file_content(full_path):
    with open(full_path,"rb") as f:
        return f.read()
    
def build_data_segment(seqnum,payload):
     return SRTPSegment(
        ptype=SRTPSegment.PTYPE_DATA,
        window=1,
        seqnum=seqnum,
        length=len(payload),
        timestamp=int(time.time()),
        payload=payload,
    ) 

def send_data_segment(sock,client_addr,seqnum,payload):
    segment=build_data_segment(seqnum,payload)
    sock.sendto(segment.encode(),client_addr)
    log(f"SERVER: Segment DATA envoyé à {client_addr}, seq={seqnum}, payload={len(payload)}")

def receive_ack(sock):
    log("SERVER: En attente d'un ACK...")
    data,client_addr=sock.recvfrom(MAX_DATAGRAM_SIZE)
    log(f"SERVER: ACK reçu de {client_addr}, taille={len(data)} octets")
    segment=SRTPSegment.decode(data)

    if segment.ptype!=SRTPSegment.PTYPE_ACK:
        raise ValueError("le client doit répondre avec un ack")
    
    return segment, client_addr

def run_server(host, port,root_dir):
    log("SERVER: lancement du serveur")
    sock=create_server_socket(host,port)
    log(f"serveur ecoute sur le port [{host}]:{port}")
    try :
        request_segment,client_addr=receive_request(sock)
        log("Requete recu du client ")
        full_path=extract_full_path(request_segment,root_dir)

        if not os.path.isfile(full_path):
            raise FileNotFoundError(f"Fichier introuvable :{full_path}")
        
        content=read_file_content(full_path)

        if len(content) > SRTPSegment.MAX_LENGTH:
            log(f":SERVER: fichier trop grand pour l'étape simple, troncature à {SRTPSegment.MAX_LENGTH} octets")
            content=content[:SRTPSegment.MAX_LENGTH]
        
        send_data_segment(sock,client_addr,0,content)

        ack_segment,addr=receive_ack(sock)
        log(f"SERVEUR : ACK recu seq={ack_segment.seqnum}")
        log("transfert simple terminé")
    finally:
        sock.close()
        log("SERVEUR : fermeture du socket")


def main():
    args=parse_args()
    run_server(args.host,args.port,args.root)

if __name__=="__main__":
    main()
    
