import React from 'react'
import { Row, Col, Button, Alert } from 'react-bootstrap'
import axios from 'axios'

export class ConfigurationCompletee extends React.Component {

  state = {
    err: '',
    attente: false,
  }

  redemarrer = event => {
    // Transmettre information d'installation
    // console.debug("Redemarrer, params: %O", this.props)
    const infoCertificatNoeudProtege = this.props.rootProps.infoCertificatNoeudProtege,
          infoClecertMillegrille = this.props.rootProps.infoClecertMillegrille

    const paramsInstallation = {
      certificatPem: infoCertificatNoeudProtege.pem,
      chainePem: [infoCertificatNoeudProtege.pem, infoClecertMillegrille.certificat],
      securite: '3.protege',
    }

    console.debug("Transmettre parametres d'installation: \n%O", paramsInstallation)

    axios.post('/installation/api/initialisation', paramsInstallation)
    .then(response=>{
      console.debug("Recu reponse demarrage installation noeud\n%O", response)
      this.setState({attente: true})
      setTimeout(_=>{window.location.reload()}, 15000) // Attendre 15 secondes et recharger la page
    })
    .catch(err=>{
      console.error("Erreur demarrage installation noeud\n%O", err)
      this.setState({err: ''+err})
    })
  }


  render() {

    var etat = (
      <Alert variant="success">
        <Alert.Heading>Configuration prete</Alert.Heading>
        <p>
          La configuration du noeud est prete.
        </p>
        <p>
          Cliquez sur Redemarrer pour lancer l'installation du logiciel.
        </p>
      </Alert>
    )
    if(this.state.err) {
      etat = (
        <Alert variant="danger">
          <Alert.Heading>Erreur installation</Alert.Heading>
          <p>{this.state.err}</p>
        </Alert>
      )
    } else if(this.state.attente) {
      etat = (
        <Alert variant="info">
          <p>Redemarrage en cours</p>
        </Alert>
      )
    }

    return (
      <div>
        {etat}

        <Row>
          <Col>
            <Button onClick={this.redemarrer} disabled={this.state.attente}>Redemarrer</Button>
          </Col>
        </Row>
      </div>
    )
  }

}

// class EtatInstallation extends React.Component {

//   SERVICES_ATTENDUS = [
//     'acme', 'nginx',
//     'mq', 'mongo', 'maitrecles', 'transaction',
//     'fichiers', 'principal', 'domaines_dynamiques', 'web_protege'
//   ]

//   // Liste des services qui, s'ils sont actifs, on peut considerer que
//   // l'installation a reussie
//   SERVICES_CLES = ['nginx', 'principal', 'web_protege']

//   state = {
//     erreur: false,
//     erreurArret: false,
//     servicesPrets: false,
//     installationComplete: false,
//   }

//   componentDidMount() {
//     this.surveillerProgres()
//   }

//   terminer = event => {
//     window.location = '/millegrilles'
//   }

//   surveillerProgres = async () => {
//     try {
//       const reponse = await axios('/installation/api/services')
//       const dictServices = reponse.data

//       // Comparer liste des services demarres a la liste des services cles
//       const listeServicesDemarres = Object.keys(dictServices).filter(nomService=>{
//         var infoService = dictServices[nomService]
//         return infoService.message_tache === 'started'
//       })
//       const listeServicesClesDemarres = listeServicesDemarres.filter(nomService=>{
//         return this.SERVICES_CLES.includes(nomService)
//       })
//       const servicesPrets = listeServicesClesDemarres.length === this.SERVICES_CLES.length
//       const installationComplete = listeServicesDemarres.length === this.SERVICES_ATTENDUS.length

//       // Conserver information
//       this.setState({...dictServices, installationComplete, servicesPrets, erreur: false}, ()=>{
//         if(!installationComplete) {
//           setTimeout(this.surveillerProgres, 5000)
//         } else {
//           console.debug("Installation complete")
//         }
//       })

//     } catch(err) {
//       console.error("Erreur verification etat des services\n%O", err)

//       if(!this.state.erreur) {
//         this.setState({erreur: true, erreurMessage: err.message})
//         setTimeout(this.surveillerProgres, 20000)  // 20 secondes avant de reessayer
//       } else {
//         console.error("2e erreur de rafraichissement, on arrete. Echec installation.")
//         this.setState({erreurArret: true, erreurMessage: err.message})
//       }
//     } finally {

//     }
//   }

//   render() {

//     const complet = <i key="spinner" className="fa fa-check-square fa-2x fa-fw btn-outline-success"/>

//     var compteServicesDemarres = 0

//     const listeServices = this.SERVICES_ATTENDUS.map( nomService => {

//       var infoService = this.state[nomService]
//       var etat = ''
//       if(infoService && infoService.message_tache === 'started') {
//         etat = complet
//         compteServicesDemarres++
//       }

//       return (
//         <Row key={nomService}>
//           <Col xs={10}>
//             {nomService}
//           </Col>
//           <Col xs={2}>
//             {etat}
//           </Col>
//         </Row>
//       )
//     })

//     const pctProgres = Math.abs(compteServicesDemarres * 100 / this.SERVICES_ATTENDUS.length)

//     return (
//       <Container>
//         <h2>Installation en cours</h2>
//         <p>Progres : {pctProgres}%</p>

//         <h3>Services</h3>
//         {listeServices}

//         <Button onClick={this.terminer} disabled={!this.state.servicesPrets}>Terminer</Button>
//       </Container>
//     )
//   }
// }
