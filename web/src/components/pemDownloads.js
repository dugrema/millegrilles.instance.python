export function genererUrlDataDownload(idmg, certificatRacine, cleChiffreeRacine) {
  const jsonContent = {
    idmg
  }
  // var urlCleRacine = null, urlCertRacine = null;

  const racine = {
    certificat: certificatRacine,
    cleChiffree: cleChiffreeRacine,
  }
  jsonContent.racine = racine;
  const stringContent = JSON.stringify(jsonContent);

  const blobFichier = new Blob([stringContent], {type: 'application/json'});
  let dataUrl = window.URL.createObjectURL(blobFichier);
  return {dataUrl}
}
