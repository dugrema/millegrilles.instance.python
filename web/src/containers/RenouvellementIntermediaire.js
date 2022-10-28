import React, {useState, useCallback, useEffect} from 'react'
import Button from 'react-bootstrap/Button'
import Alert from 'react-bootstrap/Alert'
import axios from 'axios'

import {ChargementClePrivee} from './ChargerCleCert'

export default function RenouvellementIntermediaire(props) {

  const [csr, setCsr] = useState('')

  const { intermediairePem } = props.rootProps
  const infoClecertMillegrille = props.rootProps.infoClecertMillegrille
  const certificatMillegrillePem = infoClecertMillegrille.certificat

  const [confirmation, setConfirmation] = useState('')
  const [erreur, setErreur] = useState('')

  const erreurCb = useCallback((err, message)=>setErreur({err, message}), [setErreur])

  useEffect(()=>{
    demanderCsr().then(csr=>{
      setCsr(csr)
    }).catch(e=>{
      console.error("Erreur preparation CSR : %O", e)
      erreurCb(''+e)
    })
  }, [setCsr, erreurCb])

  return (
    <>
      <h2>Renouveller certificat intermediaire</h2>

      <br/>

      {csr!==''?
        <ChargementClePrivee rootProps={props.rootProps} csr={csr} cacherBoutons={true} />
        :<p>Preparation du CSR en cours ...</p>
      }

      {intermediairePem?
        <>
          <p>Nouveau certificat intermediaire</p>
          <pre>{intermediairePem}</pre>
        </>
        :''
      }

      {certificatMillegrillePem?
        <>
          <p>Certificat de la MilleGrille</p>
          <pre>{certificatMillegrillePem}</pre>
        </>
      :''}

      <br/>
      <Button variant="secondary" onClick={()=>props.changerPage('Installation')}>Retour</Button>
      <Button disabled={!(intermediairePem && certificatMillegrillePem)}
              onClick={()=>soumettreIntermediaire({...props, erreurCb, confirmationCb: setConfirmation})}>
        Soumettre
      </Button>

      <br/>

      <Alert show={confirmation!==''} variant="success">
          <Alert.Heading>Succes</Alert.Heading>
          <p>{confirmation}</p>
      </Alert>

      <Alert show={erreur?true:false} variant="danger">
          <Alert.Heading>Erreur</Alert.Heading>
          <p>{erreur?erreur.message:''}</p>
          <pre>{erreur.err?erreur.err.stack:''}</pre>
      </Alert>

    </>
  )
}

async function demanderCsr() {
  console.debug("Charger csr")

  // const urlCsr = '/installation/api/csrIntermediaire'
  const urlCsr = '/installation/api/csr'
  const csrResponse = await axios.get(urlCsr)
  console.debug("CSR recu : %O", csrResponse)
  if(csrResponse.status !== 200) {
    throw new Error("Erreur axios code : %s", csrResponse.status)
  }
  return csrResponse.data
}

async function soumettreIntermediaire(props) {

  console.debug("soumettreIntermediaire proppys!\n%O", props)

  const { confirmationCb, erreurCb } = props
  const rootProps = props.rootProps || {}
  const {intermediairePem, infoClecertMillegrille} = rootProps
  const info = rootProps.info || {}
  const { idmg, securite } = info

  // const idmg = props.rootProps.idmg,
  //       intermediairePem = props.rootProps.intermediairePem,
  //       infoClecertMillegrille = props.rootProps.infoClecertMillegrille

  var paramsInstallation = {
    idmg,
    // chainePem: [intermediairePem, infoClecertMillegrille.certificat],
    securite: securite || '3.protege',
    certificatIntermediaire: intermediairePem,
    certificatMillegrille: infoClecertMillegrille.certificat,
  }

  if(props.rootProps.infoInternet) {
    // Ajouter les parametres de configuration internet
    paramsInstallation = {...props.rootProps.infoInternet, ...paramsInstallation}
  }

  await axios.post('/installation/api/installer', paramsInstallation)
  .then(reponse=>{
    console.debug("Configuration appliquee avec succes\n%O", reponse)
    confirmationCb('Configuration appliquee avec succes')
  })
  .catch(err=>{
    console.error("Erreur application du certificat/configuration \n%O", err)
    erreurCb(err, 'Erreur application du certificat/configuration')
    throw err
  })


  // const urlCsr = '/certissuer/issuer'
  // const params = {pem}
  // console.debug("Soumettre vers %s : %O", urlCsr, params)
  // const response = await axios.post(urlCsr, params)
  // console.debug("Response : %O", response)
  // if(response.status !== 200) {
  //   throw new Error("Erreur axios code : %s", response.status)
  // }
}
