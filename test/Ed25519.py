import binascii

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

CLE_PUBLIQUE = binascii.unhexlify("822463e3c9c97e0439c0da0cfbae3a3c09571fe2af0a8dec694855c618a50aca")
cle_publique = Ed25519PublicKey.from_public_bytes(CLE_PUBLIQUE)

message = b"salut le monde des terres a courir pour des choses en entree"
signature = binascii.unhexlify("7f911468656b490e6ae6765e1279f32af9ea3ee8aa948f74027088bf9f1a1342df91431c8a1c77478c7df336369bb790a7183ca56acf5039fd085efe3201f205")

resultat = cle_publique.verify(signature, message)
print("Resultat verification : %s" % resultat)


# b4:3a:39:69:1d:bb:bf:d8:04:02:76:63:92:38:e3:cb:b4:0c:93:ed:b9:30:5e:46:80:53:93:b1:55:f6:e3:6d
# b4:3a:39:69:1d:bb:bf:d8:04:02:76:63:92:38:e3:cb:b4:0c:93:ed:b9:30:5e:46:80:53:93:b1:55:f6:e3:6d
