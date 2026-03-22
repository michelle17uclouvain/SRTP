# SRTP

## Description
Implémentation d’un protocole du protocle SRTP qui permet de transférer un fichier entre un client et un serveur avec gestion des pertes et retransmissions

-
### Lancer le serveur et logger les infos
python3 src/server_v2.py :: 8000 --root . 2> server.log


## lancer le client et logger les infos
python3 src/client_v2.py http://localhost:8000/test.txt --save resultat.txt 2> client.log 

## lancer les test
pytest test