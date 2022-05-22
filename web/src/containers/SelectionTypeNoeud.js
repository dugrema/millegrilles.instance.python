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
            <h3>Configurer le nouveau noeud</h3>

            Nouveau noeud de MilleGrille. Veuillez suivre les etapes pour demarrer votre noeud.
          </Col>
        </Row>

        {informationTypes}

        <Row>
          <Col>
            <h3>Type de noeud</h3>
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
      <Alert.Heading>Information sur les types de noeud</Alert.Heading>
      <Row>
        <Col md={2}>Protege</Col>
        <Col md={10}>
          Noeud central de la MilleGrille. Contient une base de donnees,
          un systeme de messagerie et un certificat special lui permettant
          d'autoriser les autres composants systeme. Le noeud protege supporte
          toutes les fonctionnalites protegees, privees et publiques.
        </Col>
      </Row>
      <Row>
        <Col md={2}>Prive</Col>
        <Col md={10}>
          Noeud additionnel qui supporte des services et des applications (senseurs, backup, etc.).
          Doit etre associe a un noeud protege. Peut aussi agir comme noeud public
          s'il est configure avec acces a internet.
        </Col>
      </Row>
      <Row>
        <Col md={2}>Public</Col>
        <Col md={10}>
          Noeud specialise pour la publication et dissemination sur internet. Doit etre
          associe a un noeud protege. Ce noeud doit aussi etre configure avec un acces
          internet (adresse DNS, ports ouverts sur le routeur).
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
