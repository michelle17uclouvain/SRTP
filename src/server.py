import argparse
import os
import socket
import sys
import time 
from SRTPSegment import SRTPSegment

MAX_DATAGRAM_SIZE=2048
SEQ_MOD=2048
RETRANSMISSION_TIMEOUT=4.0
POLL_TIMEOUT=0.2

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
    while True:
        log("SERVER : en attente d'une requête client...")
        data, client_addr = sock.recvfrom(MAX_DATAGRAM_SIZE)
        log(f"SERVER: segment reçu de {client_addr}, taille={len(data)}")
        try:
            segment = SRTPSegment.decode(data)
        except Exception:
            log("SERVER: segment invalide ingoré")
            continue
        if segment is None:
            log("SERVER : segment invalide ignoré")
            continue
        if segment.ptype != SRTPSegment.PTYPE_DATA:
            log("SERVER : segment non DATA ignoré")
            continue
        return segment, client_addr

def extract_full_path(segment, root_dir):
    try:
        request = segment.payload.decode("ascii")
    except UnicodeDecodeError:
        raise ValueError("La requête du client n'est pas en ascii")
    log(f"SERVER: requette reçue : {request!r}")
    if not request.startswith("GET "):
        raise ValueError("requete doit commencer par GET")
    file_path = request[4:].strip()
    if not file_path.startswith("/"):
        raise ValueError("Le chemin doit commencer par /")
    safe_path = os.path.normpath(file_path.lstrip("/"))
    full_path = os.path.abspath(os.path.join(root_dir, safe_path))
    root_abs = os.path.abspath(root_dir)
    if not full_path.startswith(root_abs + os.sep) and full_path != root_abs:
        raise ValueError("Chemin demandé invalide")
    log(f"SERVER: Chemin resolu : {full_path}")
    return full_path

def read_file_content(full_path):
    with open(full_path,"rb") as f:
        return f.read()
    
def split_file(content):
    blocks=[]
    max_size=SRTPSegment.MAX_LENGTH
    for i in range(0,len(content),max_size):
        block=content[i:i +max_size]
        blocks.append(block)
        log(f"SERVER : bloc crée num={len(blocks)-1}, taille={len(block)}")
    return blocks

def build_data_segment(seqnum, payload):
    return SRTPSegment(
        ptype=SRTPSegment.PTYPE_DATA,
        window=0,
        seqnum=seqnum % SEQ_MOD,
        length=len(payload),
        timestamp=int(time.time() * 1000) & 0xFFFFFFFF,
        payload=payload,
    )

def send_segment(sock,client_addr,segment):
    sock.sendto(segment.encode(),client_addr)

def send_data_segment(sock, client_addr, seqnum, payload):
    segment = build_data_segment(seqnum, payload)
    send_segment(sock, client_addr, segment)
    log(f"SERVER: segment DATA envoyé à {client_addr}, seq={seqnum}, payload={len(payload)}")
    return segment

def ack_is_valid(ack_seq, first_unacked_index, next_index_to_send):
    current_index = first_unacked_index
    while current_index <= next_index_to_send:
        if (current_index % SEQ_MOD) == ack_seq:
            return True
        current_index += 1
    return False

def receive_ack(sock, expected_client_addr):
    while True:
        log("SERVER: En attente d'un ACK...")
        data, client_addr = sock.recvfrom(MAX_DATAGRAM_SIZE)
        log(f"SERVER: ACK reçu de {client_addr}, taille={len(data)} octets")
        if client_addr != expected_client_addr:
            log("SERVER : ACK reçu d'un autre client, ignoré")
            continue
        try:
            segment = SRTPSegment.decode(data)
        except Exception:
            log("SERVER : ACK invalide ignoré")
            continue

        if segment is None:
            log("SERVER : ACK invalide ignoré")
            continue
        if segment.ptype not in (SRTPSegment.PTYPE_ACK, SRTPSegment.PTYPE_SACK):
            log("SERVER : segment reçu non ACK/SACK, ignoré")
            continue
        return segment

def remember_sent_packet(sent_packets, seq_num, block_index, segment):
    sent_packets[seq_num] = {
        "block_index": block_index,
        "segment": segment,
        "sent_time": time.time(),
        "acked": False,
    }

def advance_first_unacked_index(sent_packets, first_unacked_index):
    while True:
        seq_num = first_unacked_index % SEQ_MOD
        if seq_num not in sent_packets:
            break
        if not sent_packets[seq_num]["acked"]:
            break
        del sent_packets[seq_num]
        first_unacked_index += 1
    return first_unacked_index

def retransmit_timeout_packets(sock, client_addr, sent_packets, timeout):
    current_time = time.time()
    for seq_num, packet_info in sent_packets.items():
        if packet_info["acked"]:
            continue
        elapsed_time = current_time - packet_info["sent_time"]
        if elapsed_time>= timeout:
            segment = packet_info["segment"]
            sock.sendto(segment.encode(), client_addr)
            packet_info["sent_time"] = current_time
            log(f"SERVER:retransmission seq={seq_num}")

def send_packets_in_window(sock,client_addr, blocks,first_unacked_index,next_index_to_send,client_window,sent_packets):
    send_limit=first_unacked_index+client_window
    while(next_index_to_send<len(blocks) and next_index_to_send<send_limit):
        seq_num=next_index_to_send%SEQ_MOD
        payload=blocks[next_index_to_send] 
        segment=build_data_segment(seq_num,payload)
        send_segment(sock,client_addr,segment)
        log(f"SERVER: DATA envoyé seq={seq_num}, taille={len(payload)}")
        remember_sent_packet(sent_packets, seq_num, next_index_to_send, segment)
        next_index_to_send += 1
    return next_index_to_send

def mark_acked_packet(sent_packets,seq_num):
    if seq_num in sent_packets:
        sent_packets[seq_num]["acked"]=True
        log(f"SERVER: paquet acquitté ACK seq={seq_num}")

def mark_acked_packets_from_response(ack_segment, sent_packets, first_unacked_index,next_index_to_send):
    current_index = first_unacked_index
    while current_index < next_index_to_send:
        seq_num = current_index % SEQ_MOD
        if seq_num == ack_segment.seqnum:
            break
        mark_acked_packet(sent_packets, seq_num)
        current_index += 1

def update_after_response(ack_segment,sent_packets,first_unacked_index,next_index_to_send):
    mark_acked_packets_from_response(ack_segment,sent_packets,first_unacked_index,next_index_to_send)
    first_unacked_index = advance_first_unacked_index(sent_packets,first_unacked_index)
    return first_unacked_index
         
def send_end_segment(sock,client_addr,seqnum):
    end_segment=SRTPSegment(
        ptype=SRTPSegment.PTYPE_DATA,
        window=0,
        seqnum=seqnum%SEQ_MOD,
        length=0,
        timestamp=int(time.time() * 1000) & 0xFFFFFFFF,
        payload=b"",
    )
    sock.sendto(end_segment.encode(), client_addr)
    log(f"SERVER : segment de fin envoyé seq={seqnum%SEQ_MOD}")

def send_file_block(sock,client_addr,content):
    blocks=split_file(content)
    log(f"SERVER : fichier decoupe en {len(blocks)} bloc(s)")
    sent_packets={}
    first_unacked_index=0
    next_index_to_send=0
    client_window=1
    sock.settimeout(POLL_TIMEOUT)


    try:
        while first_unacked_index<len(blocks):
            next_index_to_send=send_packets_in_window(sock,client_addr,blocks,first_unacked_index,next_index_to_send,client_window,sent_packets)
            try:
                ack_segment = receive_ack(sock, client_addr)
                if ack_segment.ptype == SRTPSegment.PTYPE_ACK:
                    log(f"SERVER: ACK recu ack={ack_segment.seqnum}")
                if not ack_is_valid(ack_segment.seqnum, first_unacked_index, next_index_to_send):
                    log(f"SERVER : vieux ACK ignore seq={ack_segment.seqnum}")
                    continue
                client_window = max(0, min(63, ack_segment.window))
                first_unacked_index=update_after_response(ack_segment,sent_packets,first_unacked_index,next_index_to_send)

            except socket.timeout:
                retransmit_timeout_packets(sock,client_addr,sent_packets,RETRANSMISSION_TIMEOUT)
        log("SERVER : tous les blocs ont ete acquites")
        end_seq=len(blocks)%SEQ_MOD

        while True:
            send_end_segment(sock, client_addr, end_seq)
            try:
                while True:
                    ack_segment = receive_ack(sock, client_addr)
                    if ack_segment.seqnum == (end_seq + 1) % SEQ_MOD:
                        log(f"SERVER : ACK de fin reçu seq={ack_segment.seqnum}")
                        return
                    log(f"SERVER : ACK non final ignoré seq={ack_segment.seqnum}")
            except socket.timeout:
                log("SERVER : timeout sur le segment de fin, retransmission")
    finally:
        sock.settimeout(None)

def run_server(host, port,root_dir):
    log("SERVER: lancement du serveur")
    sock=create_server_socket(host,port)
    log(f"serveur ecoute sur le port [{host}]:{port}")
    try :
        request_segment,client_addr=receive_request(sock)
        log(" SERVEUR : Requete recu du client ")
        try:
            full_path=extract_full_path(request_segment,root_dir)
        except ValueError as e:
            log(f"SERVER :requete invalide : {e}")
            send_end_segment(sock, client_addr, 0)
            return
        if not os.path.isfile(full_path):
            log(f"SERVER : fichier introuvable : {full_path}")
            send_end_segment(sock, client_addr, 0)
            return
        
        content=read_file_content(full_path)
        send_file_block(sock,client_addr,content)
    finally:
        sock.close()
        log("SERVEUR : fermeture du socket")

def main():
    args=parse_args()
    run_server(args.host,args.port,args.root)

if __name__=="__main__":
    main()
    
