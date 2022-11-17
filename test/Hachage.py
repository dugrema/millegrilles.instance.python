from millegrilles_messages.messages.Hachage import Hacheur

binput = bytearray(b"salut le monde des terres a courir pour des choses en entree")

hachage_blake2b = Hacheur('blake2b-512', 'base16')
hachage_blake2b.update(binput)
resultat_blake2b = hachage_blake2b.finalize()

print("Resultat BLAKE2b : %s" % resultat_blake2b[9:])

hachage_blake2s = Hacheur('blake2s-256', 'base16')
hachage_blake2s.update(binput)
resultat_blake2s = hachage_blake2s.finalize()

print("Resultat BLAKE2s : %s" % resultat_blake2s[9:])
