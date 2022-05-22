import React from 'react'
import { Container, Row, Col, Button, Alert } from 'react-bootstrap'

import { genererNouveauCertificatMilleGrille } from '../components/pkiHelper'
import { PageBackupCles } from './PemUtils'
import { genererUrlDataDownload } from '../components/pemDownloads'

export class GenererNouvelleCle extends React.Component {

  state = {
    certificatRacinePret: false,
    credentialsRacine: '',

    etapeVerifierCle: false,
    etapeGenererIntermediaire: false,
    etapeDemarrerInstallation: false,
    etapeSurveillerInstallation: false,

    idmg: '',
    backupComplete: false,
    certPem: '',
    clePriveePem: '',
    motdepasseCle: '',

    url: '',
  }

  componentDidMount() {
    if( ! this.state.certificatRacinePret ) {
      // Generer un nouveau certificat racine
      genererNouveauCertificatMilleGrille()
      .then( credentialsRacine => {

        console.debug("Credentials racine : %O", credentialsRacine)

        this.setState({
          certificatRacinePret: true,
          idmg: credentialsRacine.idmg,
          certPem: credentialsRacine.certPem,
          clePriveePem: credentialsRacine.clePriveePem,
          motdepasseCle: credentialsRacine.motdepasseCle,
        })
      })
      .catch(err=>{
        console.error("Erreur generation nouvelle cle MilleGrille\n%O", err)
      })
    }

  }

  setCertificatMillegrille = certificatMillegrillePem => {
    this.setState({certificatMillegrillePem})
  }

  setCertificatIntermediaire = certificatIntermediairePem => {
    this.setState({certificatIntermediairePem})
  }

  setBackupFait = event => {
    this.setState({backupComplete: true})
  }

  imprimer = event => {
    window.print()
    this.setState({backupComplete: true})
  }

  render() {

    return (
      <GenererCle
        {...this.props}
        setConfigurationEnCours={this.setConfigurationEnCours}
        imprimer={this.imprimer}
        setPage={this.props.setPage}
        certPem={this.state.certPem}
        clePriveePem={this.state.clePriveePem}
        motdepasseCle={this.state.motdepasseCle}
        idmg={this.state.idmg}
        setBackupFait={this.setBackupFait}
        backupComplete={this.state.backupComplete}
        />
    )

  }

}

function GenererCle(props) {

  var boutonDownload = null

  if(props.idmg) {
    const {dataUrl} = genererUrlDataDownload(
      props.idmg,
      props.certPem,
      props.clePriveePem
    )

    var fichierDownload = 'backupCle_' + props.idmg + ".json";
    boutonDownload = (
      <Button href={dataUrl} download={fichierDownload} onClick={props.setBackupFait} variant="outline-secondary">Telecharger cle</Button>
    );
  }

  return (
    <Container>

      <Row>
        <Col className="screen-only">
          <h2>Nouvelle cle de MilleGrille</h2>
        </Col>
      </Row>

      <Alert variant="warning">
        <p>
          Le proprietaire de la MilleGrille est le seul qui devrait etre en
          possession de cette cle.
        </p>

        <p>Il ne faut pas perdre ni se faire voler la cle de MilleGrille.</p>
      </Alert>

      <div>IDMG : {props.idmg}</div>

      <PageBackupCles
        rootProps={props.rootProps}
        certificatRacine={props.certPem}
        motdepasse={props.motdepasseCle}
        cleChiffreeRacine={props.clePriveePem}
        idmg={props.idmg}
        />

      <div className="bouton">
        <Row>
          <Col>
            Utiliser au moins une des deux actions suivantes pour conserver la cle
            et le certificat de MilleGrille.
          </Col>
        </Row>
        <Row>
          <Col>
            <Button onClick={props.imprimer} variant="outline-secondary">Imprimer</Button>
            {boutonDownload}
          </Col>
        </Row>

        <Row>
          <Col className="boutons-installer">
            <Button onClick={props.setPage} value="ChargementClePrivee" disabled={!props.backupComplete}>Suivant</Button>
            <Button onClick={props.setPage} value='' variant="secondary">Retour</Button>
          </Col>
        </Row>
      </div>

    </Container>
  )

}
