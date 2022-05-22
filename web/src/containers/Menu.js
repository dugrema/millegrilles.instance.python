import React from 'react'
import { Nav, Navbar } from 'react-bootstrap';
import { Trans } from 'react-i18next';

export default function Menu(props) {

  // let boutonProtege
  // if(props.rootProps.modeProtege) {
  //   boutonProtege = <i className="fa fa-lg fa-lock protege"/>
  // } else {
  //   boutonProtege = <i className="fa fa-lg fa-unlock"/>
  // }

  // const iconeHome = <span><i className="fa fa-home"/> {props.rootProps.nomMilleGrille}</span>

  return (
    <Navbar collapseOnSelect expand="md" bg="info" variant="dark" fixed="top">
      <Nav.Link className="navbar-brand" onClick={props.changerPage} eventKey='Accueil'>
        <Trans>application.nom</Trans>
      </Nav.Link>
      <Navbar.Toggle aria-controls="responsive-navbar-menu" />
      <Navbar.Collapse id="responsive-navbar-menu">
        <Nav>
          <Nav.Link href='/'></Nav.Link>
        </Nav>
        <Nav className="mr-auto">
        </Nav>
        <Nav className="justify-content-end">
          <Nav.Link onClick={props.rootProps.changerLanguage}><Trans>menu.changerLangue</Trans></Nav.Link>
        </Nav>
      </Navbar.Collapse>
    </Navbar>
  )
}
