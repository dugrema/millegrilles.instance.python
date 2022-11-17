import binascii

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

CLE_PUBLIQUE = binascii.unhexlify("822463e3c9c97e0439c0da0cfbae3a3c09571fe2af0a8dec694855c618a50aca")
cle_publique = Ed25519PublicKey.from_public_bytes(CLE_PUBLIQUE)

message = b"salut le monde des terres a courir pour des choses en entree"
signature = binascii.unhexlify("7f911468656b490e6ae6765e1279f32af9ea3ee8aa948f74027088bf9f1a1342df91431c8a1c77478c7df336369bb790a7183ca56acf5039fd085efe3201f205")

resultat = cle_publique.verify(signature, message)
print("Resultat verification : %s" % resultat)


