import React, {useState, useEffect, useCallback, useMemo} from 'react'
import './App.css'
import Row from 'react-bootstrap/Row'
import Col from 'react-bootstrap/Col'
import Button from 'react-bootstrap/Button'
import Alert from 'react-bootstrap/Alert'
// import QRCode from 'qrcode.react'

import {pki as forgePki} from '@dugrema/node-forge'
import { forgecommon, idmg } from '@dugrema/millegrilles.reactjs'
// import { getIdmg } from '@dugrema/millegrilles.utiljs/src/idmg'

import { LayoutMillegrilles } from './Layout'
import { Installation } from './Installation'
import RenouvellementIntermediaire from './RenouvellementIntermediaire'

const { getIdmg } = idmg
const { splitPEMCerts, extraireExtensionsMillegrille } = forgecommon

// const MAPPING_PAGES = { Installation, RenouvellementIntermediaire }

function App(props) {

  const [idmg, setIdmg] = useState('')
  const [info, setInfo] = useState('')
  // const [infoInternet, setInfoInternet] = useState('')
  const [page, setPage] = useState('Installation')
  const [infoClecertMillegrille, setInfoClecertMillegrille] = useState('')
  const [intermediairePem, setIntermediairePem] = useState('')
  const [intermediaireCert, setIntermediaireCert] = useState('')
  const [manifest, setManifest] = useState({})

  const PageMappee = useMemo(()=>{
    let pageMappee = Installation
    switch(page) {
      case 'AfficherInformationNoeud': pageMappee = AfficherInformationNoeud; break
      case 'RenouvellementIntermediaire': pageMappee = RenouvellementIntermediaire; break
      default:
    }
    return pageMappee
  }, [page])

  const conserverInfo = useCallback(info => {
    if(info.securite && info.idmg) {  // Securite indique que le noeud est deja configure
      console.debug("Configuration MilleGrille completee : %O", info)
      setPage('AfficherInformationNoeud')
    }
    // this.setState(info)
    setInfo(info)
  }, [setPage, setInfo])

  const changerInfoClecertMillegrille = useCallback(infoClecertMillegrille => {
    // this.setState({infoClecertMillegrille, idmg: infoClecertMillegrille.idmg})
    setInfoClecertMillegrille(infoClecertMillegrille)
    setIdmg(infoClecertMillegrille.idmg)
  }, [setInfoClecertMillegrille, setIdmg])

  const setInfoCertificatNoeudProtege = useCallback((pem, cert) => {
    console.debug("Certificat intermediaire PEM\n%s", pem)
    setIntermediairePem(pem)
    setIntermediaireCert(cert)
    // this.setState({intermediairePem: pem, intermediaireCert: cert})
  }, [setIntermediairePem, setIntermediaireCert])

  // console.debug("Nom usager : %s, estProprietaire : %s", this.state.nomUsager, this.state.estProprietaire)

  const rootProps = {
    idmg, info, /*infoInternet,*/ infoClecertMillegrille, 
    intermediairePem, intermediaireCert,
    manifest,

    setInfo: conserverInfo,
    setInfoClecertMillegrille: changerInfoClecertMillegrille,
    setInfoCertificatNoeudProtege,
    // setInfoInternet,
    setManifest,
    // setIdmg,
  }

  let affichage = <PageMappee rootProps={rootProps} changerPage={setPage} />
  return (
    <LayoutApplication
      changerPage={setPage}
      affichage={affichage}
      rootProps={rootProps} />
  )

}

// Layout general de l'application
function LayoutApplication(props) {

  var qrCode = null
  if(props.rootProps.idmgCompte) {
    // qrCode = <QRCode value={'idmg:' + props.rootProps.idmg} size={75} />
  }

  const pageAffichee = (
    <div>
      <h1>Installation MilleGrille</h1>
      <Row>
        <Col sm={10}>
          <p className='idmg'>{props.rootProps.idmg}</p>
        </Col>
        <Col sm={2} className="footer-right">{qrCode}</Col>
      </Row>

      {props.affichage}
    </div>
  )

  return (
    <LayoutMillegrilles changerPage={props.changerPage} page={pageAffichee} rootProps={props.rootProps}/>
  )
}

// function _setTitre(titre) {
//   document.title = titre
// }

function AfficherInformationNoeud(props) {

  const info = props.rootProps.info || {}
  const { securite, domaine } = info
  const pemCertificat = info.certificat
  const pemCa = info.ca

  // const pemCertificat = props.rootProps.certificat
  // const pemCa = props.rootProps.ca

  const [certificat, setCertificat] = useState()
  const [certificatIntermediaire, setCertificatIntermediaire] = useState()
  const [idmgCalcule, setIdmgCalcule] = useState()
  const [extensions, setExtensions] = useState()

  useEffect(()=>{
    if(pemCertificat) {
      console.debug("Lecture du certificat %O", pemCertificat)
      let pems = pemCertificat
      if(typeof(pemCertificat) === 'string') pems = splitPEMCerts(pemCertificat)
      const cert = forgePki.certificateFromPem(pems[0])
      const interCert = forgePki.certificateFromPem(pems[1])
      console.debug("Cert : %O, inter : %O", cert, interCert)
      setCertificat(cert)
      setCertificatIntermediaire(interCert)
      const exts = extraireExtensionsMillegrille(cert)
      console.debug("Extensions : %O", exts)
      setExtensions(exts)
    }
  }, [pemCertificat])
  useEffect(()=>{
    if(pemCa) {
      getIdmg(pemCa).then(idmg=>{
        setIdmgCalcule(idmg)
      })
    }
  }, [pemCa])

  console.debug("Props - %O", props)

  let certificatExpire, certificatJoursExpiration, intermediaireExpire
  const maintenant = new Date().getTime()
  const msJour = 24 * 60 * 60000
  if(certificat) {
    const tempsExpiration = certificat.validity.notAfter.getTime()
    certificatExpire = tempsExpiration < maintenant
    certificatJoursExpiration = Math.floor(Math.min((tempsExpiration - maintenant) / msJour))
    console.debug("Jours expiration : %O", certificatJoursExpiration)
    if(certificatJoursExpiration < 1) certificatJoursExpiration = null
  }
  if(certificatIntermediaire) {
    intermediaireExpire = certificatIntermediaire.validity.notAfter.getTime() < maintenant
  }

  const listeInfo = []
  listeInfo.push(
    <Row key='idmg'><Col sm={3}>Idmg calcule</Col><Col className="idmg">{idmgCalcule || 'N/D'}</Col></Row>
  )
  listeInfo.push(
    <Row key='securite'><Col sm={3}>Securite</Col><Col>{securite}</Col></Row>
  )
  if(domaine) {
    listeInfo.push(
      <Row key='domaineWeb'><Col sm={3}>Domaine web</Col><Col>{domaine}</Col></Row>
    )
  }
  if(extensions) {
    if(extensions.roles) {
      listeInfo.push(
        <Row key='roles'><Col sm={3}>Roles</Col><Col>{extensions.roles.toString()}</Col></Row>
      )
    }
    if(extensions.niveauxSecurite) {
      listeInfo.push(
        <Row key='securite_liste'><Col sm={3}>Exchanges</Col><Col>{extensions.niveauxSecurite.toString()}</Col></Row>
      )
    }
  }
  if(certificat) {
    listeInfo.push(
      <Row key='noeudId'><Col sm={3}>Instance Id</Col><Col>{certificat.subject.getField('CN').value}</Col></Row>
    )
    listeInfo.push(
      <Row key='validity_end'>
        <Col sm={3}>Expiration</Col>
        <Col className={certificatExpire?'expire':''}>
          {certificat.validity.notAfter.toString()}
          {' '}
          {certificatJoursExpiration?'(' + certificatJoursExpiration + ' jours)':<strong>Expire aujourd'hui</strong>}
        </Col>
      </Row>
    )
    if(securite === '3.protege') {
      listeInfo.push(
        <Row key='validity_inter_end'>
          <Col sm={3}>Expiration intermediaire</Col>
          <Col className={intermediaireExpire?'expire':''}>{certificatIntermediaire.validity.notAfter.toString()}</Col>
        </Row>
      )
    }
  }
  if(pemCertificat) {
    listeInfo.push(
      <Row key='certificat'>
        <Col sm={3}>Certificat</Col>
        <Col><pre>{pemCertificat.join("\n")}</pre></Col>
      </Row>
    )
  }

  var etat = null, 
      // pret = false, 
      boutons = ''
  if(certificat) {
    if(intermediaireExpire) {
      etat = (
        <Alert variant="danger">
          <Alert.Heading>Certificat intermediaire expire</Alert.Heading>
          <p>Le certificat intermediaire est expire. <strong>Action avec cle de MilleGrille requise des que possible.</strong></p>
        </Alert>
      )
    } else if(certificatExpire) {
      etat = (
        <Alert variant="danger">
          <Alert.Heading>Certificat expire</Alert.Heading>
          <p>Le certificat de l'instance est expire. <strong>Action requise</strong>.</p>
        </Alert>
      )
    } else {
      etat = <Alert variant="success">L'instance est initialisee et active.</Alert>
    }
    // pret = true
    boutons = (
      <Row>
        <Col>
          <Button href="/millegrilles">Acceder</Button>
          <Button disabled={securite!=='3.protege'} variant="secondary" onClick={()=>props.changerPage('RenouvellementIntermediaire')}>Renouveller</Button>
        </Col>
      </Row>
    )
  } else if(props.rootProps.idmg) {
    etat = (
      <Alert variant="warning">L'instance est associee a une MilleGrille mais pas encore initialisee.</Alert>
    )
  } else {
    etat = (
      <Alert variant="warning">L'instance n'est pas associe a une MilleGrille</Alert>
    )
  }

  return (
    <div>
      <h2>Information</h2>

      {etat}

      {listeInfo}

      {boutons}

    </div>
  )
}

export default App;
