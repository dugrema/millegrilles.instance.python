import React from 'react'
import {Container, Row, Col, Form, Button, Alert} from 'react-bootstrap'

export class SelectionnerTypeNoeud extends React.Component {

  state = {
    afficherAide: false,
  }

  fermerAide = event => {
    this.setState({afficherAide: false})
  }

  render() {

    var informationTypes = (
      <Row>
        <Col>
          <Button onClick={event=>{this.setState({afficherAide: true})}}><i className="fa fa-question-circle"/></Button>
        </Col>
      </Row>
    )
    if(this.state.afficherAide) {
      informationTypes = <AideTypes fermer={this.fermerAide}/>
    }

    return (
      <Container>
        <Row>
          <Col>
            <h3>Configurer la nouvelle instance</h3>

            Nouvelle instance de MilleGrille. Veuillez suivre les etapes pour demarrer l'installation.
          </Col>
        </Row>

        {informationTypes}

        <Row>
          <Col>
            <h3>Type d'instance</h3>
          </Col>
        </Row>


        <FormTypeNoeud {...this.props}/>

      </Container>
    )
  }
}

function AideTypes(props) {
  return (
    <Alert variant="info" onClose={props.fermer} dismissible>
      <Alert.Heading>Information sur les types d'instances</Alert.Heading>
      <Row>
        <Col md={2}>Protege</Col>
        <Col md={10}>
          Instance centrale de la MilleGrille. Contient un systeme de messagerie et supporte
          toutes applications et services de MilleGrille (incluant services secures, prives et publics).
          Si les services secures sont executes sur cette instance, il faut placer l'instance protegee dans
          un environnement physique a acces restreint.
        </Col>
      </Row>
      <Row>
        <Col md={2}>Secure</Col>
        <Col md={10}>
          Instance satellite avec un certificat intermediaire qui permet de signer tous les autres certificats de
          la millegrille. Aucune connexion directe n'est permise (e.g. via https). Une instance secure
          permet de travailler avec des donnees dechiffrees et de les conserver sur disque sans chiffrage. 
          L'instance secure devrait etre placee sur un serveur dans un endroit physique a acces restreint.
        </Col>
      </Row>
      <Row>
        <Col md={2}>Prive</Col>
        <Col md={10}>
          Instances satellite qui supporte des services et des applications privees (senseurs, backup, etc.).
          Doit etre associe a une instance protegee. Peut aussi agir comme instance publique
          s'il est configure avec acces a internet.
          L'instance privee peut conserver des donnees dechiffrees dans quelques cas specifiques (e.g. video streaming).
        </Col>
      </Row>
      <Row>
        <Col md={2}>Public</Col>
        <Col md={10}>
          Instance satellite specialisee pour la publication et dissemination sur internet. Doit etre
          associe a une instance protege. Cette instance doit aussi etre configuree avec un acces
          internet (adresse DNS, ports ouverts sur le routeur).
          L'instance privee peut conserver des donnees dechiffrees dans quelques cas specifiques (e.g. video streaming).
        </Col>
      </Row>
    </Alert>
  )
}

function FormTypeNoeud(props) {
  return (
    <>
      <Form>

        <fieldset>
          <Form.Group>
            <Form.Check id="typenoeud-protege">
              <Form.Check.Input type='radio' name="type-noeud" value='protege'
                                onChange={props.setTypeNoeud} />
              <Form.Check.Label>Protege</Form.Check.Label>
            </Form.Check>
            <Form.Check id="typenoeud-secure">
              <Form.Check.Input type='radio' name="type-noeud" value='secure'
                                onChange={props.setTypeNoeud} />
              <Form.Check.Label>Secure</Form.Check.Label>
            </Form.Check>
            <Form.Check id="typenoeud-prive">
              <Form.Check.Input type='radio' name="type-noeud" value='prive'
                                onChange={props.setTypeNoeud} />
              <Form.Check.Label>Prive</Form.Check.Label>
            </Form.Check>
            <Form.Check id="typenoeud-public">
              <Form.Check.Input type='radio' name="type-noeud" value='public'
                                onChange={props.setTypeNoeud} />
              <Form.Check.Label>Public</Form.Check.Label>
            </Form.Check>
          </Form.Group>
        </fieldset>

      </Form>
      <Row className="boutons-installer">
        <Col>
          <Button onClick={props.afficherPageTypeInstallation} value="true"
                  disabled={!props.typeNoeud}>Suivant</Button>
        </Col>
      </Row>
    </>
  )
}
