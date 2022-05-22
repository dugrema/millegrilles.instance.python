/*
  Info sur raison d'utilisation (multiple web workers).

  https://www.npmjs.com/package/worker-loader#worker
  https://webpack.js.org/concepts/loaders/
  https://dev.to/talolard/using-multiple-webworkers-with-create-react-app-246b
  https://github.com/harrysolovay/rescripts#2-define-a-rescripts-field-and-specify-which-to-use
*/
const path = require('path')

function makeMultipleWebworkersWork(config){
    // Change the output file format so that each worker gets a unique name
    config.output.filename = 'static/js/[name].bundle.js'

    const wasmExtensionRegExp = /\.wasm$/;
    config.resolve.extensions.push('.wasm');

    // Override de toutes les rules existantes pour exclure .wasm
    config.module.rules.forEach(rule => {
        (rule.oneOf || []).forEach(oneOf => {
            if (oneOf.loader && oneOf.loader.indexOf('file-loader') >= 0) {
            // make file-loader ignore WASM files
            oneOf.exclude.push(wasmExtensionRegExp);
            }
        })
    })
    
    // Now, we add a rule for processing workers
    const newRules = [{

        test: /\.worker\.js/i,
        type: "javascript/auto",
        include:  config.module.rules[1].include,
        use: [
            {
                loader: "worker-loader",
                options: {
                    // esModule: true,
                    filename: "static/js/[name].[contenthash].worker.js",
                    // chunkFilename: "[id].[contenthash].workerB.js",
                }
            },
            {
                loader: "babel-loader",
                options: {
                    presets: ["@babel/preset-env"],
                },
            },
        ],
    },
    
    // add a dedicated loader for WASM
    {
        test: wasmExtensionRegExp,
        include: path.resolve(__dirname, 'src'),
        use: [{ loader: require.resolve('wasm-loader'), options: {} }]
    },
    
    // Here we append all the old rules
    ...config.module.rules
    
    ]
    // now update Webpack's config with the new rules
    config.module.rules = newRules
    return config
}

module.exports =[
    makeMultipleWebworkersWork,
]
