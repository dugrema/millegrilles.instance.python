import React from 'react'
import {Container, Row, Col, Button, Alert} from 'react-bootstrap'
import axios from 'axios'
import https from 'https'

import { InformationCertificat } from './ChargerCleCert'

export class ConfigurerNoeud extends React.Component {

  render() {
    console.debug("ConfigurerNoeud props : %O", this.props)
    const typeNoeud = this.props.typeNoeud

    // Note : le noeud public doit etre configure avec internet

    if(this.props.rootProps.internetDisponible) {
      // Configuration du noeud avec certificat web SSL
      // Combine l'installation du certificat et du noeud en un appel
      return (
        <PageConfigurationDomaineAttente {...this.props} />
      )
    } else if(typeNoeud === 'protege') {
      return (
        <InstallerNoeudProtege {...this.props} />
      )
    } else if(typeNoeud === 'prive') {
      return (
        <ConfigurerNoeudPrive {...this.props} />
      )
    } else if(typeNoeud === 'public') {
      return (
        <ConfigurerNoeudPublic {...this.props} />
      )
    }
    return (<Alert variant="danger">Type noeud inconnu</Alert>)
  }
}

function ConfigurerNoeudPrive(props) {

  const installer = event => {
    configurerNoeudPrive(props, {}, err=>{
      if(err) {
        console.error("Erreur demarrage installation noeud\n%O", err)
        return
      }
      // Recharger page apres 15 secondes
      setTimeout(_=>{window.location.reload()}, 2000)
    })
  }

  const idmg = props.idmg

  return (
    <>
      <h2>Finaliser la configuration</h2>

      <h3>Noeud prive</h3>
      <p>Idmg : {idmg}</p>

      <Row>
        <Col className="bouton">
          <Button onClick={installer} value="true">Demarrer installation</Button>
          <Button onClick={props.annuler} value='false' variant="secondary">Annuler</Button>
        </Col>
      </Row>
    </>
  )

}

function ConfigurerNoeudPublic(props) {
  const installer = event => {
    configurerNoeudPublic(props, {}, err=>{
      if(err) {
        console.error("Erreur demarrage installation noeud\n%O", err)
        return
      }
      // Recharger page apres 15 secondes
      setTimeout(_=>{window.location.reload()}, 2000)
    })
  }

  const idmg = props.idmg

  return (
    <>
      <h2>Finaliser la configuration</h2>

      <h3>Noeud public</h3>
      <p>Idmg : {idmg}</p>

      <Row>
        <Col className="bouton">
          <Button onClick={installer} value="true">Demarrer installation</Button>
          <Button onClick={props.annuler} value='false' variant="secondary">Annuler</Button>
        </Col>
      </Row>
    </>
  )
}

function InstallerNoeudProtege(props) {

  const installer = event => {
    installerNoeudProtege(props, {}, err=>{
      if(err) {
        console.error("Erreur demarrage installation noeud\n%O", err)
        return
      }
      console.debug("Recu reponse demarrage installation noeud")
      // Recharger page apres 15 secondes
      setTimeout(_=>{window.location.reload()}, 15000)
    })
  }

  const intermediaireCert = props.rootProps.intermediaireCert

  return (
    <Container>
      <h2>Finaliser la configuration</h2>

      <h3>Certificat du noeud</h3>
      <InformationCertificat certificat={intermediaireCert} />

      <Row>
        <Col className="bouton">
          <Button onClick={installer} value="true">Demarrer installation</Button>
          <Button onClick={props.annuler} value='false' variant="secondary">Annuler</Button>
        </Col>
      </Row>
    </Container>
  )

}

class PageConfigurationDomaineAttente extends React.Component {

  state = {
    resultatTestAccesUrl: false,
    domaineConfigure: false,
    certificatRecu: false,
    serveurWebRedemarre: false,

    erreur: false,
    messageErreur: '',
    stackErreur: '',

  }

  componentDidMount() {
    // Lancer le processus de configuration
    this.testerAccesUrl()
  }

  testerAccesUrl = async () => {
    this.setState({
      resultatTestAccesUrl: false,
      domaineConfigure: false,
      certificatRecu: false,
      compteurAttenteCertificatWeb: 0,
      compteurAttenteRedemarrageServeur: 0,

      erreur: false,
      messageErreur: '',
      stackErreur: '',
    })

    // const urlDomaine = 'https://' + this.props.domaine + '/installation/api/infoMonitor'
    const urlDomaine = '/installation/api/info'

    // Creer instance AXIOS avec timeout court (5 secondes) et
    // qui ignore cert SSL (... parce que c'est justement ce qu'on va installer!)
    const instanceAxios = axios.create({
      timeout: 5000,
      httpsAgent: new https.Agent({ keepAlive: true, rejectUnauthorized: false, }),
    });

    try {
      const reponseTest = await instanceAxios.get(urlDomaine)
      console.debug("Reponse test\n%O", reponseTest)
      this.setState({resultatTestAccesUrl: true}, ()=>{
        this.configurerDomaine()
      })
    } catch (err) {
      console.error("Erreur connexion\n%O", err)
      this.setState({erreur: true, messageErreur: err.message, stackErreur: err.stack})
    }

  }

  async configurerDomaine() {
    const infoInternet = this.props.rootProps.infoInternet
    console.debug("Configurer le domaine %s", infoInternet)

    const paramsDomaine = {
      domaine: infoInternet.domaine,
      modeTest: infoInternet.modeTest,
    }

    if(this.props.modeCreation === 'dns_cloudns') {
      paramsDomaine['modeCreation'] = infoInternet.modeCreation
      paramsDomaine['cloudnsSubid'] = infoInternet.cloudnsSubid
      paramsDomaine['cloudnsPassword'] = infoInternet.cloudnsPassword
    }

    try {
      //const reponseCreation = await axios.post('/installation/api/configurerDomaine', paramsDomaine)
      // console.debug("Transmettre parametres d'installation, domaine web: \n%O", paramsDomaine)

      const callback = err => {
        if(err) {
          console.error("Erreur demarrage installation noeud\n%O", err)
          this.setState({err: ''+err})
          return
        }
        this.setState({domaineConfigure: true}, ()=>{
          // Declencher attente du certificat
          this.attendreCertificatWeb()
        })
      }

      if(this.props.typeNoeud === 'protege') {
        installerNoeudProtege(this.props, paramsDomaine, callback)
      } else if(this.props.typeNoeud === 'prive') {
        configurerNoeudPrive(this.props, paramsDomaine, callback)
      } else if(this.props.typeNoeud === 'public') {
        configurerNoeudPublic(this.props, paramsDomaine, callback)
      }

    } catch(err) {
      console.error("Erreur configuration domaine\n%O", err)
      this.setState({erreur: true, messageErreur: err.message, stackErreur: err.stack})
    }

  }

  attendreCertificatWeb = async() => {
    console.debug("Attente certificat web - debut")

    if(this.state.compteurAttenteCertificatWeb > 25) {
      // Echec, timeout
      this.setState({erreur: true, messageErreur:'Timeout attente certificat SSL'})
      return
    }

    console.debug("Attente certificat web")
    try {
      const reponse = await axios.get('/installation/api/etatCertificatWeb')
      if(!reponse.data.pret) {
        console.debug("Certificat n'est pas pret")
        this.setState({compteurAttenteCertificatWeb: this.state.compteurAttenteCertificatWeb + 1 })
        setTimeout(this.attendreCertificatWeb, 5000) // Reessayer dans 5 secondes
      } else {
        console.debug("Certificat pret")
        this.setState({certificatRecu: true}, ()=>{
          // Declencher attente du redemarrage du serveur
          setTimeout(this.attendreRedemarrageServeur, 15000) // Verifier dans 15 secondes
        })
      }
    } catch(err) {
      console.error("Erreur configuration domaine\n%O", err)
      this.setState({erreur: true, messageErreur: err.message, stackErreur: err.stack})
    }

  }

  attendreRedemarrageServeur = async() => {
    console.debug("Attente redemarrage serveur - debut")

    if(this.state.compteurAttenteRedemarrageServeur > 10) {
      // Echec, timeout
      this.setState({erreur: true, messageErreur:'Timeout redemarrage serveur'})
      return
    }

    console.debug("Attente redemarrage web")
    try {
      await axios.get('/installation/api/etatCertificatWeb')
      console.debug("Certificat pret")
      this.setState({serveurWebRedemarre: true}, ()=>{
        // Declencher attente du certificat
        this.configurationCompletee()
      })
    } catch(err) {
      console.error("Erreur test nouveau certificat serveur\n%O", err)
      setTimeout(this.attendreRedemarrageServeur, 5000) // Reessayer dans 10 secondes
      this.setState({compteurAttenteRedemarrageServeur: this.state.compteurAttenteRedemarrageServeur + 1 })
    }

  }

  configurationCompletee = async() => {
    console.debug("Configuration completee")
  }

  render() {

    const etapes = []
    var spinner = ''
    if(this.state.erreur) {
      spinner = <i className="fa fa-close fa-2x btn-outline-danger"/>
    } else {
      spinner = <i key="spinner" className="fa fa-spinner fa-pulse fa-2x fa-fw"/>
    }
    const complet = <i key="spinner" className="fa fa-check-square fa-2x fa-fw btn-outline-success"/>

    const etatTest = this.state.resultatTestAccesUrl?complet:spinner
    etapes.push(<li key="1">Verifier acces au serveur {this.props.domaine} {etatTest}</li>)

    if(this.state.resultatTestAccesUrl) {
      const etatConfigurationDomaine = this.state.domaineConfigure?complet:spinner
      etapes.push(<li key="2">Configuration du domaine {etatConfigurationDomaine}</li>)
    }
    if(this.state.domaineConfigure) {
      const etatConfigurationSsl = this.state.certificatRecu?complet:spinner
      etapes.push(<li key="3">Configuration du certificat SSL {etatConfigurationSsl}</li>)
    }
    if(this.state.certificatRecu) {
      etapes.push(<li key="4">Certificat recu, serveur pret {complet}</li>)
    }

    var page = ''
    if(this.state.erreur) {
      page = <AfficherErreurConnexion
              domaine={this.props.domaine}
              retour={this.props.retour}
              reessayer={this.testerAccesUrl}
              {...this.state} />
    }

    return (
      <>
        <h3>Configuration en cours ...</h3>
        <ol>
          {etapes}
        </ol>
        {page}
      </>
    )
  }
}

function AfficherErreurConnexion(props) {
  return (
    <>
      <Alert variant="danger">
        <Alert.Heading>Erreur de connexion au domaine demande</Alert.Heading>
        <p>Domaine : {props.domaine}</p>
        <hr />
        <p>{props.messageErreur}</p>
      </Alert>
      <Row>
        <Col>
          <Button onClick={props.retour}>Retour</Button>
          <Button onClick={props.reessayer}>Reessayer</Button>
        </Col>
      </Row>
    </>
  )
}

async function installerNoeudProtege(props, params, callback) {
  console.debug("Pour installation, proppys!\n%O", props)

  const idmg = props.idmg || props.rootProps.idmg,
        intermediairePem = props.rootProps.intermediairePem,
        certificatMillegrillePem = props.rootProps.infoClecertMillegrille.certificat

//throw new Error("fix me")

  // Set certificat intermediaire dans le certissuer
  // const paramsIssuer = {
  //   idmg,
  //   chainePem: [infoCertificatNoeudProtege.pem, infoClecertMillegrille.certificat],
  // }
  // await axios.post('/certissuer/issuer', paramsIssuer)
  // .then(reponse=>{
  //   console.debug("Recu reponse demarrage installation noeud\n%O", reponse)
  //   callback() // Aucune erreur
  // })
  // .catch(err=>{
  //   console.error("Erreur demarrage installation noeud\n%O", err)
  //   callback(err)
  // })

  var paramsInstallation = {
    ...params,
    // certificatMillegrillePem: this.props.certificatMillegrillePem,
    // certificatPem: infoCertificatNoeudProtege.pem,
    idmg,
    // chainePem: [intermediairePem, certificatMillegrillePem],
    certificatMillegrille: certificatMillegrillePem,
    certificatIntermediaire: intermediairePem,
    securite: '3.protege',
  }

  if(props.rootProps.infoInternet) {
    // Ajouter les parametres de configuration internet
    paramsInstallation = {...props.rootProps.infoInternet, ...paramsInstallation}
  }

  axios.post('/installation/api/installer', paramsInstallation)
  .then(reponse=>{
    console.debug("Recu reponse demarrage installation noeud\n%O", reponse)
    callback() // Aucune erreur
  })
  .catch(err=>{
    console.error("Erreur demarrage installation noeud\n%O", err)
    callback(err)
  })

}

async function configurerNoeudPrive(props, params, callback) {

  const infoInternet = props.rootProps.infoInternet

  var paramsInstallation = {
    ...params,
    idmg: props.idmg,
    securite: '2.prive',
  }
  console.debug("Transmettre parametres installation noeud prive : %O", paramsInstallation)

  if(infoInternet) {
    // Ajouter les parametres de configuration internet
    paramsInstallation = {...props.rootProps.infoInternet, ...paramsInstallation}
  }

  axios.post('/installation/api/configurerIdmg', paramsInstallation)
  .then(reponse=>{
    console.debug("Recu reponse demarrage installation noeud\n%O", reponse)
    callback() // Aucune erreur
  })
  .catch(err=>{
    console.error("Erreur demarrage installation noeud\n%O", err)
    callback(err)
  })

}

async function configurerNoeudPublic(props, params, callback) {

  const paramsInstallation = {
    ...params,
    idmg: props.idmg,
    securite: '1.public',
  }
  console.debug("Transmettre parametres installation noeud public : %O", paramsInstallation)

  axios.post('/installation/api/configurerIdmg', paramsInstallation)
  .then(reponse=>{
    console.debug("Recu reponse demarrage installation noeud public\n%O", reponse)
    callback() // Aucune erreur
  })
  .catch(err=>{
    console.error("Erreur demarrage installation noeud public\n%O", err)
    callback(err)
  })

}
