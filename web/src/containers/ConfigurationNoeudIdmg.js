import React from 'react'
import { Row, Col, Button, InputGroup, FormControl } from 'react-bootstrap'

export class ConfigurerNoeudIdmg extends React.Component {

  state = {
    idmg: '',
  }

  componentDidMount() {
    if(this.props.rootProps.idmg) {
      console.debug("ConfigurerNoeudIdmg IDMG = %s, aller a la page suivante", this.props.rootProps.idmg)
      this.props.setPage({currentTarget: {value: 'ConfigurerNoeud'}})
    }
  }

  changerChamp = event => {
    const {name, value} = event.currentTarget
    this.setState({[name]: value})
  }

  suivant = event => {
    console.debug("Props - %O", this.props)
    this.props.setIdmg(this.state.idmg)
    this.props.setPage(event)
  }

  render() {

    var pageSuivante = 'ConfigurerNoeud'
    // if(this.props.internetDisponible) {
    //   pageSuivante = 'PageConfigurationInternet'
    // }

    return (
      <>
        <h2>Configurer IDMG</h2>

        <p>Saisir le IDMG pour empecher un tiers de prendre possession du noeud</p>

        <FormIdmg idmg={this.state.idmg}
                  changerChamp={this.changerChamp} />

        <Row>
          <Col>
            <Button onClick={this.suivant} value={pageSuivante}>Suivant</Button>
            <Button variant="secondary">Retour</Button>
          </Col>
        </Row>
      </>
    )
  }

}

function FormIdmg(props) {
  return (
    <InputGroup className="mb-3">
      <InputGroup.Text id="idmg">
        IDMG du noeud
      </InputGroup.Text>
      <FormControl id="idmg"
                   aria-describedby="idmg"
                   name="idmg"
                   value={props.idmg}
                   onChange={props.changerChamp} />
    </InputGroup>
  )
}
