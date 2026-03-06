import socket
import struct

def run_server(port=8080):
    # AF_INET6 pour IPv6, SOCK_DGRAM pour UDP
    sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    
    # On lie le serveur à toutes les interfaces sur le port choisi
    server_address = ('::', port)
    sock.bind(server_address)
    
    print(f"Serveur SRTP en attente sur le port {port}...")

    while True:
        # On reçoit les données (max 1500 octets pour l'Ethernet standard)
        data, address = sock.recvfrom(1500)
        print(f"Reçu {len(data)} octets de {address}")

        # --- Étape de Décodage ---
        # Le header fait au moins 3 octets (Type/Win + Seq Num)
        # On utilise struct.unpack para extraire les infos
        # '!' signifie Big-Endian, 'B' un octet (8 bits), 'H' un unsigned short (16 bits)
        try:
            header_first_byte, seq_num = struct.unpack('!BH', data[:3])
            packet_type = (header_first_byte >> 6) & 0x03 # On récupère les 2 premiers bits
            window_size = header_first_byte & 0x3F        # Les 6 bits restants
            
            payload = data[3:]
            
            print(f"Type: {packet_type}, Seq: {seq_num}, Win: {window_size}")
            print(f"Contenu : {payload}")
            
        except Exception as e:
            print(f"Erreur de décodage : {e}")

if __name__ == "__main__":
    run_server()