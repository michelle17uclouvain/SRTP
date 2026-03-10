import struct
import zlib 

class SRTPSegment:
    PTYPE_DATA=1
    PTYPE_ACK=2
    PTYPE_SACK=3

    MAX_WINDOW=63
    MAX_SEQNUM=2047
    MAX_LENGTH=1024

    def __init__(self,ptype,window,seqnum,length,timestamp,payload=b""):
        self.ptype = ptype
        self.window = window
        self.seqnum = seqnum
        self.length = length
        self.timestamp = timestamp
        self.payload = payload


    def __repr__(self):
        return (f"SRTPSegment("f"ptype={self.ptype}," f"window={self.window}," f"seqnum={self.seqnum}," f"length={self.length},"
            f"timestamp={self.timestamp},"
            f"payload={self.payload}"
            f")")

    def validateSegment(self):
        #verifie les valeur des différents champs
        if self.ptype not in (self.PTYPE_DATA,self.PTYPE_ACK,self.PTYPE_SACK):
            raise ValueError("ptype invalide")
        if self.window < 0 or self.window > self.MAX_WINDOW:
            raise ValueError("window doit être entre 0 et 63")
        if self.seqnum < 0 or self.seqnum > self.MAX_SEQNUM:
            raise ValueError("seqnum doit etre entre 0 et 2047")
        if self.length < 0 or self.length > self.MAX_LENGTH:
            raise ValueError("length doit être entre 0 et 1024")
        if self.length != len(self.payload):
            raise ValueError("length doit être égal à lenght du payload")
        if self.timestamp < 0 or self.timestamp > 0xFFFFFFFF:
            raise ValueError("timestamp doit être sur 4 bytes")
        

    def encode(self):
        """ permet d'encoder le segment en big indian"""
        self.validateSegment()

        #Ici on construit le header
        header_start=((self.ptype << 30)| (self.window << 24)| (self.length << 11)| self.seqnum)
        header=struct.pack("!2I",header_start,self.timestamp)

        #calcul du crc du header
        crc1=zlib.crc32(header)&0xFFFFFFFF

        #construction du segment
        segment=header+struct.pack("!I",crc1)

        #si payload alors calcul du crc2 
        if self.length>0:
            crc2=zlib.crc32(self.payload)& 0xFFFFFFFF
            segment+=self.payload+struct.pack("!I",crc2)
        return segment
    

    @staticmethod
    def decode(data):

        """Decode les bytes envoyé en SRTPSegment"""
        if data is None : 
            return None 
        
        if len(data)<12:
            return None
        
        # on recupère le header
        header_start = struct.unpack("!I", data[0:4])[0]
        ptype = (header_start >> 30) & 0b11
        window = (header_start>> 24) & 0b111111
        length = (header_start >> 11) & 0x1FFF
        seqnum = header_start & 0x7FF
        timestamp = struct.unpack("!I", data[4:8])[0]       


        received_crc1 = struct.unpack("!I", data[8:12])[0]
        # verification du crc1
        header_without_crc1 = data[0:8]
        computed_crc1 = zlib.crc32(header_without_crc1) & 0xFFFFFFFF

        if computed_crc1 != received_crc1:
            return None

        payload = b""

        # Ssi payload on verifie avec crc2
        if length > 0:

            if len(data) <12+length+4:
                return None

            payload = data[12:12 + length]
            received_crc2 = struct.unpack("!I", data[12 + length:12 + length + 4])[0]
            computed_crc2 = zlib.crc32(payload) & 0xFFFFFFFF

            if computed_crc2 != received_crc2:
                return None

        # on renvoit le segment décodé 
        segment=SRTPSegment(
                ptype=ptype,
                window=window,
                seqnum=seqnum,
                length=length,
                timestamp=timestamp,
                payload=payload,
            )
        try:
            segment.validateSegment()
        except ValueError:
            return None
        return segment


            
                    
