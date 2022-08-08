import React from 'react'
import ReactDOM from 'react-dom'

import './index.css'
import App from './containers/App'

import 'bootstrap/dist/css/bootstrap.min.css'
import 'font-awesome/css/font-awesome.min.css'
import './components/i18n'

// Remplacer par webback.providePlugin lorsque possible
// Polyfill hack : https://github.com/WalletConnect/walletconnect-monorepo/issues/748
window.Buffer = window.Buffer || require("buffer").Buffer;

console.debug("WINDOW.Buffer : %O", window.Buffer)

const buffer = Buffer.from([0x1, 0x2, 0x5])
console.debug("Buffer : %O", buffer)

ReactDOM.render(
  <React.StrictMode>
    <App/>
  </React.StrictMode>,
  document.getElementById('root')
);
