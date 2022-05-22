import React from 'react'
import { Container, Row, Col} from 'react-bootstrap'
import { Trans } from 'react-i18next'
import QRCode from 'qrcode.react'

import Menu from './Menu'

import './Layout.css'

export function LayoutMillegrilles(props) {

  return (
    <div className="flex-wrapper">
      <div>
        <Entete changerPage={props.changerPage} rootProps={props.rootProps}/>
        <Contenu changerPage={props.changerPage} page={props.page}/>
      </div>
      <Footer rootProps={props.rootProps}/>
    </div>
  )

}

function Entete(props) {
  return (
    <Container>
      <Menu changerPage={props.changerPage} rootProps={props.rootProps}/>
      <h1>MilleGrilles</h1>
    </Container>
  )
}

function Contenu(props) {
  return (
    <Container>
      {props.page}
    </Container>
  )
}

function Footer(props) {

  const idmg = props.rootProps.idmg
  var qrCode = null

  if(props.rootProps.idmg) {
    qrCode = <QRCode value={'idmg:' + idmg} size={75} />
  }

  return (
    <Container fluid className="footer bg-info">
      <Row>
        <Col sm={2} className="footer-left"></Col>
        <Col sm={8} className="footer-center">
          <div className="millegrille-footer">
            <div>IDMG : {idmg}</div>
            <div>
              <Trans>application.advert</Trans>{' '}
              <span title={props.rootProps.manifest.date}>
                <Trans values={{version: props.rootProps.manifest.version}}>application.version</Trans>
              </span>
            </div>
          </div>
        </Col>
        <Col sm={2} className="footer-right">{qrCode}</Col>
      </Row>
    </Container>
  )
}
