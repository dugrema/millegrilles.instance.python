import React from 'react'
import { Form, Container, Row, Col, Button, InputGroup, FormControl } from 'react-bootstrap'

const RE_DOMAINE = /^((?!-)[A-Za-z0-9-]{1,63}(?<!-)\.)+[A-Za-z]{2,6}$/

export class PageConfigurationInternet extends React.Component {
  state = {
    internetDisponible: false,

    domaine: this.props.fqdnDetecte,
    domaineValide: RE_DOMAINE.test(this.props.fqdnDetecte),
    domainesAdditionnels: '',

    configurationAvancee: false,
    modeTest: false,
    modeCreation: 'webroot',

    cloudns_subauthid: '',
    cloudns_password: '',
    dnssleep: '240',

    attenteServeur: false,
  }

  componentDidMount() {
    console.debug("props : %O", this.props)
  }

  setInternetDisponible = event => {
    console.debug("Set internet disponible : %O", event)
    const eventInfo = event.currentTarget
    console.debug("Set internet disponible eventInfo: %O", eventInfo)
    this.setState({internetDisponible: eventInfo.value === 'true'})
  }

  changerDomaine = event => {
    const {value} = event.currentTarget
    const valide = RE_DOMAINE.test(value)
    this.setState({domaine: value, domaineValide: valide})
  }

  changerTextfield = event => {
    const {name, value} = event.currentTarget
    this.setState({[name]: value})
  }

  setCheckbox = event => {
    const {name, checked} = event.currentTarget
    this.setState({[name]: checked})
  }

  setModeCreation = event => {
    const {value} = event.currentTarget
    this.setState({modeCreation: value}, ()=>{console.debug("State :\n%O", this.state)})
  }

  configurerDomaine = event => {
    // Transmettre la commande de configuration du domaine
    const config = {...this.state}
    if(config.domainesAdditionnels) config.domainesAdditionnels = config.domainesAdditionnels.split(',').map(item=>item.trim())
    this.props.rootProps.setInfoInternet(config)
    this.props.setPage({currentTarget: {value:'ConfigurerNoeud'}})
  }

  revenirPageSaisie = event => {
    this.setState({attenteServeur: false})
  }

  render() {

    return (
      <PageConfigurationDomaineSetup
        rootProps={this.props.rootProps}
        domaine={this.state.domaine}
        domaineValide={this.state.domaineValide}
        internetDisponible={this.state.internetDisponible}
        changerDomaine={this.changerDomaine}
        changerTextfield={this.changerTextfield}
        setInternetDisponible={this.setInternetDisponible}
        setCheckbox={this.setCheckbox}
        configurationAvancee={this.state.configurationAvancee}
        modeTest={this.state.modeTest}
        cloudns_subauthid={this.state.cloudns_subauthid}
        cloudns_password={this.state.cloudns_password}
        dnssleep={this.state.dnssleep}
        setModeCreation={this.setModeCreation}
        modeCreation={this.state.modeCreation}
        configurerDomaine={this.configurerDomaine} />
    )

    // if(this.state.attenteServeur) {
    //   pageAffichee = <PageConfigurationDomaineAttente
    //                     rootProps={this.props.rootProps}
    //                     domaine={this.state.domaine}
    //                     modeCreation={this.state.modeCreation}
    //                     modeTest={this.state.modeTest}
    //                     cloudnsSubid={this.state.cloudnsSubid}
    //                     cloudnsPassword={this.state.cloudnsPassword}
    //                     retour={this.revenirPageSaisie} />
    // } else {
    //   pageAffichee = <PageConfigurationDomaineSetup
    //                     rootProps={this.props.rootProps}
    //                     domaine={this.state.domaine}
    //                     domaineValide={this.state.domaineValide}
    //                     changerDomaine={this.changerDomaine}
    //                     changerTextfield={this.changerTextfield}
    //                     setCheckbox={this.setCheckbox}
    //                     configurationAvancee={this.state.configurationAvancee}
    //                     modeTest={this.state.modeTest}
    //                     cloudnsSubid={this.state.cloudnsSubid}
    //                     cloudnsPassword={this.state.cloudnsPassword}
    //                     setModeCreation={this.setModeCreation}
    //                     modeCreation={this.state.modeCreation}
    //                     configurerDomaine={this.configurerDomaine} />
    // }
    //
    // return pageAffichee
  }
}

function PageConfigurationDomaineSetup(props) {

  return (
    <Container>
      <Row>
        <Col>
          <h3>Configurer le domaine de la MilleGrille</h3>
        </Col>
      </Row>

      <Form.Group>
        <Form.Check id="installation-internet">
          <Form.Check.Input type='checkbox'
                            name="internet-disponible"
                            value='true'
                            onChange={props.setInternetDisponible}
                            checked={props.internetDisponible} />
          <Form.Check.Label>Disponible sur internet</Form.Check.Label>
        </Form.Check>
      </Form.Group>

      <AfficherFormInternet {...props} />

      <Row className="boutons-installer">
        <Col>
          <Button onClick={props.configurerDomaine} value="true" disabled={!props.domaineValide}>Suivant</Button>
        </Col>
      </Row>

    </Container>
  )
}

function AfficherFormInternet(props) {

  if(!props.internetDisponible) return ''

  // var flagDomaineInvalide = null;
  // if( ! props.domaineValide ) {
  //   flagDomaineInvalide = <i className="fa fa-close btn-outline-danger"/>
  // }

  var configurationAvancee = ''
  if(props.configurationAvancee) {
    var cloudnsParams = ''
    if (props.modeCreation === 'dns_cloudns') {
      cloudnsParams = (
        <div>
          <label htmlFor="cloudns-subid">Configuration ClouDNS</label>
          <InputGroup>
            <InputGroup.Text id="cloudns-subid">
              SubID (numero)
            </InputGroup.Text>
            <FormControl id="cloudns-subid"
                         aria-describedby="cloudns-subid"
                         name="cloudns_subauthid"
                         value={props.cloudns_subauthid}
                         onChange={props.changerTextfield} />
          </InputGroup>
          <InputGroup>
            <InputGroup.Text id="cloudns-password">
              Mot de passe
            </InputGroup.Text>
            <FormControl id="cloudns-password"
                         aria-describedby="cloudns-password"
                         type="password"
                         name="cloudns_password"
                         value={props.cloudns_password}
                         onChange={props.changerTextfield} />
          </InputGroup>

          <InputGroup>
            <InputGroup.Text id="dns-sleep">
              DNS sleep
            </InputGroup.Text>
            <FormControl id="dns-sleep"
                         aria-describedby="dns-sleep"
                         name="dnssleep"
                         value={props.dnssleep}
                         onChange={props.changerTextfield} />
          </InputGroup>

        </div>
      )
    }

    configurationAvancee = (
      <div>

        <InputGroup>
          <InputGroup.Text id="domaines-additionnels">
            Domaines additionnels
          </InputGroup.Text>
          <FormControl 
            id="domaines-additionnels"
            aria-describedby="domaines-additionnels"
            name="domainesAdditionnels"
            value={props.domainesAdditionnels}
            onChange={props.changerTextfield} />
        </InputGroup>

        <Form.Check id="certificat-test">
          <Form.Check.Input type='checkbox' name="modeTest" value='true' onChange={props.setCheckbox} checked={props.modeTest}/>
          <Form.Check.Label>Certificat de test</Form.Check.Label>
        </Form.Check>

        <Form.Group controlId="modeCreationCertificat">
          <Form.Label>Mode de creation certificat</Form.Label>
          <Form.Control as="select" value={props.modeCreation} onChange={props.setModeCreation}>
            <option value="webroot">Mode http (port 80)</option>
            <option value="dns_cloudns">ClouDNS</option>
          </Form.Control>
        </Form.Group>

        {cloudnsParams}
      </div>
    )
  }

  return (
    <>
      <Row>
        <Col>
          <h4>Configuration prealable</h4>

          <ul>
            <li>Nom de domaine</li>
            <li>Configurer les ports TCP 443 et 80 sur le routeur</li>
          </ul>

          <p>
            Adresse IPv4 detectee pour le noeud : {props.ipDetectee}
          </p>

        </Col>
      </Row>

      <Row>
        <Col>
          <h3>Configuration</h3>
        </Col>
      </Row>
      <Form>
        <label htmlFor="noeud-url">URL d'acces au noeud {props.flagDomaineInvalide}</label>
        <InputGroup className="mb-3">
          <InputGroup.Text id="noeud-addon3">
            https://
          </InputGroup.Text>
          <FormControl id="noeud-url" aria-describedby="noeud-addon3" value={props.domaine} onChange={props.changerDomaine}/>
        </InputGroup>

        <Form.Check id="configuration-avancee">
          <Form.Check.Input type='checkbox' name="configurationAvancee" value='true' onChange={props.setCheckbox} checked={props.configurationAvancee}/>
          <Form.Check.Label>Configuration avancee</Form.Check.Label>
        </Form.Check>

        {configurationAvancee}

      </Form>
    </>
  )
}
