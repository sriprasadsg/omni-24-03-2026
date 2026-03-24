const http = require('http');

const endpoints = [
    '/api/health',
    '/api/risks',
    '/api/vendors',
    '/api/trust-center/profile',
    '/api/file-share/shares',
    '/api/training/modules'
];

async function checkEndpoint(path) {
    return new Promise((resolve) => {
        const req = http.get({
            hostname: 'localhost',
            port: 5000,
            path: path,
            timeout: 2000
        }, (res) => {
            let data = '';
            res.on('data', (chunk) => data += chunk);
            res.on('end', () => {
                console.log(`[${res.statusCode}] ${path}`);
                resolve(true);
            });
        });

        req.on('error', (e) => {
            console.error(`[ERROR] ${path}: ${e.message}`);
            resolve(false);
        });

        req.on('timeout', () => {
            req.destroy();
            console.error(`[TIMEOUT] ${path}`);
            resolve(false);
        });
    });
}

async function runChecks() {
    console.log("Checking Backend API Health...");
    for (const endpoint of endpoints) {
        await checkEndpoint(endpoint);
    }
}

runChecks();
