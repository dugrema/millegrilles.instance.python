import axios from 'axios'
// import { openDB } from 'idb'
// import stringify from 'json-stable-stringify'
import { pki as forgePki } from '@dugrema/node-forge'

// import {
//     genererCertificatMilleGrille, genererCertificatIntermediaire
// } from '@dugrema/millegrilles.common/lib/cryptoForge'
import {  encoderIdmg } from '@dugrema/millegrilles.utiljs/src/idmg'

import { 
  genererClePrivee, genererCertificatMilleGrille, genererCertificatIntermediaire,
  chargerPemClePriveeEd25519, 
  genererPassword,
} from '@dugrema/millegrilles.utiljs/src/certificats'

// Importer pour wiring des fonctions de hachage react
import { forgecommon } from '@dugrema/millegrilles.reactjs'

const { chargerClePrivee } = forgecommon  // from '@dugrema/millegrilles.common/lib/forgecommon'

// import { encoderIdmg } from '@dugrema/millegrilles.utiljs/lib/idmg'
// import { CryptageAsymetrique, genererAleatoireBase64 } from '@dugrema/millegrilles.common/lib/cryptoSubtle'

// const cryptageAsymetriqueHelper = new CryptageAsymetrique()

// export async function genererNouvelleCleMillegrille() {
//   // console.debug("Params genererNouvelleCleMillegrille")
//   return await genererNouveauCertificatMilleGrille()
// }

export async function chargerClePriveeForge(clePriveePem, motdepasse) {
  const clePriveeForge = await chargerClePrivee(clePriveePem, {password: motdepasse})
  return clePriveeForge
}

export async function preparerCleCertMillegrille(certificatPem, clePriveePem, motdepasse) {
  // Preparer les cles et calcule le idmg

  // console.debug("Conserver cle chiffree, cert\n%s", certificatPem)
  // const clePriveeForge = await chargerClePrivee(clePriveePem, {password: motdepasse})
  // // console.debug("Cle privee forge\n%O", clePriveeForge)
  // const clePriveeDechiffreePem = sauvegarderPrivateKeyToPEM(clePriveeForge)

  const clePrivee = chargerPemClePriveeEd25519(clePriveePem, {password: motdepasse})
  // console.debug("Cle privee : %O", clePrivee)
  const idmg = await encoderIdmg(certificatPem)
  console.debug("IDMG calcule : %s", idmg)

  // const helperAsymetrique = new CryptageAsymetrique()
  // const {clePriveeDecrypt, clePriveeSigner, clePriveeSignerPKCS1_5} = await helperAsymetrique.preparerClePrivee(clePriveeDechiffreePem)

  // const dictCles = {signer: clePriveeSigner, signerPKCS1_5: clePriveeSignerPKCS1_5, dechiffrer: clePriveeDecrypt}

  //// sauvegarderRacineMillegrille(idmg, certificatPem, dictCles)

  //return {...dictCles, idmg, certificat: certificatPem}

  return {idmg, clePrivee}
}

export async function signerCSRIntermediaire(csrPem, infoClecertMillegrille) {
  const { certificat, clePrivee } = infoClecertMillegrille  //await chargerClecertMillegrilleSignature(idmg)
  const certPem = await genererCertificatIntermediaire(csrPem, certificat, clePrivee)
  return certPem
}

export async function chargerCertificatPem(pem) {
  return forgePki.certificateFromPem(pem)
}

// Genere un nouveau certificat de MilleGrille racine
export async function genererNouveauCertificatMilleGrille() {

  // Preparer secret pour mot de passe partiel navigateur
  const motdepasseCle = genererPassword()

  const {
    // pemPublic, 
    pem, 
    pemChiffre, 
    publicKey: publicKeyCrypto, 
    privateKey: privateKeyCrypto
  } = await genererClePrivee({password: motdepasseCle, dechiffre: true})
  console.debug("Public Key : %O", publicKeyCrypto)
  console.debug("Private Key : %O", privateKeyCrypto)

  // Afficher PEMS
  // debug("PEM Public: %s", '\n'+pemPublic)
  console.debug("PEM prive : %s", '\n'+pem)
  console.debug("PEM chiffre : %s", '\n'+pemChiffre)

  const {idmg, pem: certPem} = await genererCertificatMilleGrille(pem)

  console.debug("Nouveau certificat CA\n%s", certPem)
  return {idmg, certPem, clePriveePem: pemChiffre, motdepasseCle}

  // const {clePriveePkcs8, clePubliqueSpki, clePriveeSigner} =
  //   await cryptageAsymetriqueHelper.genererKeysNavigateur({modulusLength: 3072})

  // const infoCles = await genererClePrivee({password: motdepasseCle})
  // console.debug("Info Cles : %O", infoCles)
  // const clePriveePEM = enveloppePEMPrivee(clePriveePkcs8, true),
  //       clePubliquePEM = enveloppePEMPublique(clePubliqueSpki)

  // // console.debug("Cle privee PEM\n%O \nCle publique PEM\n%O", clePriveePEM, clePubliquePEM)

  // const clePriveeChiffree = await chiffrerPrivateKeyPEM(clePriveePEM, motdepasseCle)

  // // console.debug("Cle Privee Chiffree")
  // // console.debug(clePriveeChiffree)

  // // Importer dans forge, creer certificat de MilleGrille
  // const {cert, pem: certPEM, idmg} = await genererCertificatMilleGrille(clePriveePEM, clePubliquePEM)

  // return {
  //   clePriveePEM, clePubliquePEM, cert, certPEM, idmg, clePriveeChiffree, motdepasseCle, clePriveeSigner
  // }
}

// Recupere un CSR a signer avec la cle de MilleGrille
export async function preparerInscription(url, pkiMilleGrille) {
  console.debug("PKI Millegrille params")
  console.debug(pkiMilleGrille)

  // const {certMillegrillePEM, clePriveeMillegrilleChiffree, motdepasseCleMillegrille} = pkiMilleGrille

  // Extraire PEM vers objets nodeforge
  // const certMillegrille = forgePki.certificateFromPem(certMillegrillePEM)
  // const clePriveeMillegrille = chargerClePrivee(clePriveeMillegrilleChiffree, {password: motdepasseCleMillegrille})

  // Calculer IDMG a partir du certificat de millegrille
  // const idmg = await encoderIdmg(certMillegrillePEM)

  const parametresRequete = {nomUsager: pkiMilleGrille.nomUsager}
  if(pkiMilleGrille.u2f) {
    parametresRequete.u2fRegistration = true
  }

  // Aller chercher un CSR pour le nouveau compte
  const reponsePreparation = await axios.post(url, parametresRequete)
  console.debug("Reponse preparation inscription compte :\n%O", reponsePreparation.data)

  // Creer le certificat intermediaire
  // const { csrPem: csrPEM, u2fRegistrationRequest, challengeCertificat } = reponsePreparation.data
  
  throw new Error("Fix me")
  // const {cert, pem: certPem} = await genererCertificatIntermediaire(idmg, certMillegrille, clePriveeMillegrille, {csrPEM})

  // return {
  //   certPem,
  //   u2fRegistrationRequest,
  //   challengeCertificat,
  // }
}

// export async function sauvegarderCertificatPem(usager, certificatPem, chainePem) {
//   const nomDB = 'millegrilles.' + usager

//   const db = await openDB(nomDB)

//   console.debug("Sauvegarde du nouveau cerfificat de navigateur usager (%s) :\n%O", usager, certificatPem)

//   const txUpdate = db.transaction('cles', 'readwrite');
//   const storeUpdate = txUpdate.objectStore('cles');
//   await Promise.all([
//     storeUpdate.put(certificatPem, 'certificat'),
//     storeUpdate.put(chainePem, 'fullchain'),
//     storeUpdate.delete('csr'),
//     txUpdate.done,
//   ])
// }

// export async function sauvegarderRacineMillegrille(idmg, certificatPem, clesPriveesSubtle) {
//   const nomDB = 'millegrille.' + idmg
//   // console.debug("Conserver cles %s\n%O", nomDB, clesPriveesSubtle)

//   const db = await openDB(nomDB, 1, {
//     upgrade(db) {
//       db.createObjectStore('cles')
//     },
//   })

//   const {signer: cleSigner, dechiffrer: cleDechiffrer, signerPKCS1_5} = clesPriveesSubtle

//   // console.debug("Sauvegarde du nouveau cerfificat et cle de MilleGrille (idmg: %s) :\n%O", idmg, certificatPem)

//   const txUpdate = db.transaction('cles', 'readwrite');
//   const storeUpdate = txUpdate.objectStore('cles');

//   const listeTransactions = [storeUpdate.put(certificatPem, 'millegrille.certificat'), txUpdate.done]

//   // Cles optionnelles
//   if(cleSigner) listeTransactions.push(storeUpdate.put(cleSigner, 'millegrille.signer'))
//   if(cleDechiffrer) listeTransactions.push(storeUpdate.put(cleDechiffrer, 'millegrille.dechiffrer'))
//   if(signerPKCS1_5) listeTransactions.push(storeUpdate.put(signerPKCS1_5, 'millegrille.signerPKCS1_5'))

//   // Attendre fin de traitement des transactions
//   await Promise.all(listeTransactions)
// }

// export async function signerChallenge(usager, challengeJson) {

//   const contenuString = stringify(challengeJson)

//   const nomDB = 'millegrilles.' + usager
//   const db = await openDB(nomDB)
//   const tx = await db.transaction('cles', 'readonly')
//   const store = tx.objectStore('cles')
//   const cleSignature = (await store.get('signer'))
//   await tx.done

//   const challengeStr = stringify(challengeJson)
//   const signature = await new CryptageAsymetrique().signerContenuString(cleSignature, contenuString)

//   return signature
// }

// async function chargerClecertMillegrilleSignature(idmg) {

//   const nomDB = 'millegrille.' + idmg
//   const db = await openDB(nomDB)
//   const tx = await db.transaction('cles', 'readonly')
//   const store = tx.objectStore('cles')
//   const cleSignature = (await store.get('millegrille.signer'))
//   const cleSignaturePKCS1_5 = (await store.get('millegrille.signerPKCS1_5'))
//   const certificat = (await store.get('millegrille.certificat'))
//   await tx.done

//   return {certificat, signer: cleSignature, signerPKCS1_5: cleSignaturePKCS1_5}
// }

// // Initialiser le contenu du navigateur
// export async function initialiserNavigateur(usager, opts) {
//   if(!opts) opts = {}

//   const nomDB = 'millegrilles.' + usager
//   const db = await openDB(nomDB, 1, {
//     upgrade(db) {
//       db.createObjectStore('cles')
//     },
//   })

//   // console.debug("Database %O", db)
//   const tx = await db.transaction('cles', 'readonly')
//   const store = tx.objectStore('cles')
//   const certificat = (await store.get('certificat'))
//   const fullchain = (await store.get('fullchain'))
//   const csr = (await store.get('csr'))
//   await tx.done

//   if( opts.regenerer || ( !certificat && !csr ) ) {
//     console.debug("Generer nouveau CSR")
//     // Generer nouveau keypair et stocker
//     const keypair = await new CryptageAsymetrique().genererKeysNavigateur()
//     console.debug("Key pair : %O", keypair)

//     const clePriveePem = enveloppePEMPrivee(keypair.clePriveePkcs8),
//           clePubliquePem = enveloppePEMPublique(keypair.clePubliqueSpki)
//     console.debug("Cles :\n%s\n%s", clePriveePem, clePubliquePem)

//     const clePriveeForge = chargerClePrivee(clePriveePem),
//           clePubliqueForge = chargerClePubliquePEM(clePubliquePem)

//     // console.debug("CSR Genere : %O", resultat)
//     const csrNavigateur = await genererCsrNavigateur('idmg', 'nomUsager', clePubliqueForge, clePriveeForge)

//     console.debug("CSR Navigateur :\n%s", csrNavigateur)

//     const txPut = db.transaction('cles', 'readwrite');
//     const storePut = txPut.objectStore('cles');
//     await Promise.all([
//       storePut.put(keypair.clePriveeDecrypt, 'dechiffrer'),
//       storePut.put(keypair.clePriveeSigner, 'signer'),
//       storePut.put(keypair.clePublique, 'public'),
//       storePut.put(csrNavigateur, 'csr'),
//       txPut.done,
//     ])

//     return { csr: csrNavigateur }
//   } else {
//     return { certificat, fullchain, csr }
//   }

// }
