import React from 'react'
import { Row, Col, Alert } from 'react-bootstrap'
// import QRCode from 'qrcode.react'
import { Trans } from 'react-i18next';

export class RenderPEM extends React.Component {

  render() {
    const tailleMaxQR = 800;
    const qrCodes = [];

    if(this.props.pem) {
      var lignesPEM = this.props.pem.trim().split('\n')
      if(lignesPEM[0].startsWith('---')) {
        lignesPEM = lignesPEM.slice(1)
      }
      const derniereLigne = lignesPEM.length - 1
      if(lignesPEM[derniereLigne].startsWith('---')) {
        lignesPEM = lignesPEM.slice(0, derniereLigne)
      }
      const pemFiltre = lignesPEM.join('')

      const nbCodes = Math.ceil(pemFiltre.length / tailleMaxQR);
      const tailleMaxAjustee = pemFiltre.length / nbCodes + nbCodes

      for(let idx=0; idx < nbCodes; idx++) {
        var debut = idx * tailleMaxAjustee, fin = (idx+1) * tailleMaxAjustee;
        if(fin > pemFiltre.length) fin = pemFiltre.length;
        var pemData = pemFiltre.slice(debut, fin);
        // Ajouter premiere ligne d'info pour re-assemblage
        pemData = this.props.nom + ';' + (idx+1) + ';' + nbCodes + '\n' + pemData;
        qrCodes.push(
          <Col xs={6} key={idx} className='qr-code'>
            {/*<QRCode className="qrcode" value={pemData} size={300} />*/}
          </Col>
        );
      }
    }

    return(
      <Row>
        {qrCodes}
      </Row>
    );
  }

}

function RenderPair(props) {
  var certificat = null, clePrivee = null;

  if(props.certificat) {
    certificat = (
      <div className="pem">
        <p>Certificat</p>
        <RenderPEM pem={props.certificat} nom={props.nom + '.cert'}/>
      </div>
    );
  }

  if(props.clePrivee) {
    clePrivee = (
      <div className="cle-pem">
        <p>{props.idmg}</p>

        <Alert variant="warning">
          Conserver cette page separement de celle avec le mot de passe.
        </Alert>

        <p>Cle chiffree de la MilleGrille</p>

        <RenderPEM pem={props.clePrivee} nom={props.nom + '.cle'}/>

      </div>
    );
  }

  return (
    <div>
      {certificat}
      {clePrivee}
    </div>
  );

}

export function PageBackupCles(props) {
  if(props.certificatRacine && props.motdepasse && props.cleChiffreeRacine) {

    return (
      <div>
        <Row className="motdepasse">
          <Col lg={8}>
            <Trans>backup.cles.motDePasse</Trans>
            <p>{props.motdepasse}</p>
          </Col>
          <Col lg={4}>
            {/*<QRCode value={props.motdepasse} size={75} />*/}
          </Col>
        </Row>

        <div className="print-only">
          <RenderPair
            certificat={props.certificatRacine}
            clePrivee={props.cleChiffreeRacine}
            nom="racine"
            idmg={props.idmg}
            />
        </div>
      </div>
    );
  } else {
    return <div></div>
  }
}
