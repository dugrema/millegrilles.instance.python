const webpack = require('webpack');

module.exports = function override(config, env) {
    const fallback = config.resolve.fallback || {};
    Object.assign(fallback, {
        // assert: 'assert/',  // require.resolve('assert/'),
        buffer: 'buffer/', //require.resolve('buffer/'),
        crypto: 'crypto-browserify/',  // require.resolve('crypto-browserify/'),
        // fs: require.resolve('fs/'),
        http: 'stream-http/',  // require.resolve('stream-http/'),
        https: 'https-browserify/',  // require.resolve('https-browserify/'),
        // os: 'os-browserify/',   // require.resolve('os-browserify/'),
        path: 'path-browserify/',   // require.resolve('os-browserify/'),
        // stream: 'stream-browserify/',  // require.resolve('stream-browserify/'),
        // url: 'url/',  // require.resolve('url/')
    })
    config.resolve.fallback = fallback;
    
    let plugins = config.plugins || [];
    plugins.push(
        new webpack.ProvidePlugin({
            // process: 'process/browser',
            Buffer: ['buffer', 'Buffer'],
            // 'window.Buffer': ['buffer', 'Buffer'],
        })
    );
    config.plugins = plugins

    return config;
}