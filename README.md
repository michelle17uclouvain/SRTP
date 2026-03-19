# SRTP
python3 client_v2.py http://localhost:8000/test.txt --save resultat.txt 2> client.log

python3 server_v2.py :: 8000 --root . 2> server.log