import React from 'react'
import axios from 'axios'
// import https from 'https'
// import { Form, Container, Row, Col, Button, InputGroup, FormControl, Alert } from 'react-bootstrap';

// import { InstallationNouvelle } from './InstallationNouvelle'
import { SelectionnerTypeNoeud } from './SelectionTypeNoeud'
import { ChargementClePrivee } from './ChargerCleCert'
import { GenererNouvelleCle } from './GenererNouvelleCle'
import { ConfigurationCompletee } from './PagesEtat'
import { ConfigurerNoeudIdmg } from './ConfigurationNoeudIdmg'
import { ConfigurerNoeud } from './ConfigurationNoeud'

const RE_DOMAINE = /^((?!-)[A-Za-z0-9-]{1,63}(?<!-)\.)+[A-Za-z]{2,6}$/
const MAPPING_PAGES = {
  SelectionnerTypeNoeud,
  ChargementClePrivee,
  GenererNouvelleCle,
  ConfigurationCompletee,
  ConfigurerNoeud,
  ConfigurerNoeudIdmg,
}

export class Installation extends React.Component {

  state = {
    infoMonitorChargee: false,
    erreurAcces: false,

    domaine: '',
    typeNoeud: '',

    page: 'SelectionnerTypeNoeud',

    fqdnDetecte: '',
    idmg: '',
  }

  componentDidMount() {
    // Lire etat de l'installation de la MilleGrille
    axios.get('/installation/api/info')
    .then(reponse=>{
      console.debug("Reponse recue\n%O", reponse)
      const dataReponse = reponse.data

      const info = {
        idmg: dataReponse.idmg,
        domaine: dataReponse.domaine,
        securite: dataReponse.securite,
        noeudId: dataReponse.instance_id,
        certificat: dataReponse.certificat,
        ca: dataReponse.ca,
      }

      var typeNoeud = this.state.typeNoeud
      if(info.securite) {
        typeNoeud = info.securite.split('.')[1]
      }

      this.props.rootProps.setInfo(info)

      var domaineDetecte = window.location.hostname
      if( ! RE_DOMAINE.test(domaineDetecte) ) {
        domaineDetecte = dataReponse.fqdn_detecte
      }

      // Set page courante selon etat de configuration
      var page = this.state.page
      if( ! info.securite ) {
        console.debug("Ouvrir configuration type noeud")
        page = 'SelectionnerTypeNoeud'
      } else if( ! info.idmg && info.securite === '3.protege' ) {
        console.debug("Ouvrir configuration idmg")
        page = 'ChargementClePrivee'  // Page config cle MilleGrille
      } else if( ! info.idmg ) {
        page = 'ConfigurerNoeudIdmg'  // Page set IDMG
      } else if( ! info.domaine ) {
        console.debug("Ouvrir configuration domaine internet")
        page = 'PageConfigurationInternet'
      }

      this.setState({
        infoMonitorChargee: true,
        erreurAcces: false,
        fqdnDetecte: domaineDetecte,
        ipDetectee: dataReponse.ip_detectee,
        domaine: dataReponse.domaine,
        page, typeNoeud,
      })
    })
    .catch(err=>{
      console.error("Erreur lecture info monitor\n%O", err)
      this.setState({infoMonitorChargee: false, erreurAcces: true})
    })
  }

  setPage = event => { 
    const page = event.currentTarget.value
    console.debug("Page : %s", page)
    this.setState({page}) 
  }

  setTypeNoeud = event => {
    this.setState({typeNoeud: event.currentTarget.value})
  }

  setIdmg = idmg => {
    this.setState({idmg})
  }

  afficherPageTypeInstallation = event => {
    // Transfere l'ecran a la page selon le type d'installation choisi (noeud, internet)
    console.debug("Affiche page, etat %O", this.state)
    if(this.state.typeNoeud === 'protege') {
      this.setState({page: 'ChargementClePrivee'})
    } else if(['prive', 'public'].includes(this.state.typeNoeud)) {
      this.setState({page: 'ConfigurerNoeudIdmg'})
    }

  }

  render() {
    console.debug("!!! Info monitor state : %O", this.state)
    if(this.state.infoMonitorChargee) {
      // Domaine est configure, on procede a l'installation
      var Page = SelectionnerTypeNoeud

      if(this.state.page) {
        Page = MAPPING_PAGES[this.state.page]
      }

      var pageInstallation = (
        <Page rootProps={this.props.rootProps}
              setPage={this.setPage}
              setTypeNoeud={this.setTypeNoeud}
              setIdmg={this.setIdmg}
              setInternetDisponible={this.setInternetDisponible}
              afficherPageTypeInstallation={this.afficherPageTypeInstallation}
              annuler={()=>this.setState({page: ''})}
              {...this.state} />
      )

      return pageInstallation
    } else {
      return <PageAttente />
    }

  }

}

function PageAttente(props) {
  return (
    <p>Chargement en cours</p>
  )
}
