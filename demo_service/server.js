
const http = require('http');
const fs = require('fs');
const path = require('path');

// Optional: WebSocket client for Self-Healer
let SelfHealerClient;
let selfHealerClient;

try {
    SelfHealerClient = require('../src/websocket_client/js_client.js');
    // Initialize Self-Healer client
    selfHealerClient = new SelfHealerClient({
        serverUrl: process.env.SELF_HEALER_URL || 'ws://localhost:8000/ws/logs/demo-user',
        serviceName: 'demo-node-service'
    });
    selfHealerClient.connect();
} catch (e) {
    console.log('Self-Healer client not available, using file logging');
}

const PORT = process.env.PORT || 9002;
const LOG_FILE = process.env.LOG_FILE || path.join(__dirname, '..', 'logs', 'service.log');

// Ensure log directory exists
const logDir = path.dirname(LOG_FILE);
if (!fs.existsSync(logDir)) {
    fs.mkdirSync(logDir, { recursive: true });
}

// Enhanced Logger utility with payload support
function log(level, message, options = {}) {
    const timestamp = new Date().toISOString();
    const logMessage = `[${timestamp}] [${level}] ${message}`;
    
    // Console output
    console.log(logMessage);
    
    // File output
    fs.appendFileSync(LOG_FILE, logMessage + '\n');
    
    // Send to Self-Healer if connected
    if (selfHealerClient) {
        const method = level.toLowerCase();
        if (typeof selfHealerClient[method] === 'function') {
            // Extract stack trace from error (handles both real Error and synthetic error objects)
            let stackTrace = null;
            if (options.error) {
                if (options.error instanceof Error) {
                    stackTrace = options.error.stack;
                } else if (options.error.stack) {
                    stackTrace = options.error.stack;
                }
            }
            
            selfHealerClient[method](message, options.metadata, {
                endpoint: options.endpoint,
                method: options.httpMethod,
                payload: options.payload,
                stackTrace: stackTrace,  // Pass stack trace directly
                isAutocureTry: options.isAutocureTry || false
            });
        }
    }
}

// Parse request body
function parseBody(req) {
    return new Promise((resolve, reject) => {
        let body = '';
        req.on('data', chunk => {
            body += chunk.toString();
            // Limit body size
            if (body.length > 1e6) {
                req.destroy();
                reject(new Error('Request body too large'));
            }
        });
        req.on('end', () => {
            if (!body) {
                resolve({});
                return;
            }
            try {
                resolve(JSON.parse(body));
            } catch (e) {
                resolve({ raw: body });
            }
        });
        req.on('error', reject);
    });
}

// Check if this is an autocure-try request
function isAutocureTry(payload) {
    return payload && payload['autocure-try'] === true;
}

// ==========================================
// INTENTIONAL ERROR ZONES (for demonstration)
// ==========================================

// Error Zone 1: Undefined variable access
function processUserData(userData) {
    // BUG: userData might be undefined - missing null check
    const userName = userData.name;  // This will throw TypeError if userData is undefined
    const userAge = userData.age;
    
    return {
        displayName: userName.toUpperCase(),
        birthYear: 2024 - userAge
    };
}

// Error Zone 2: Array index out of bounds
function getItemAtIndex(items, index) {
    // BUG: No bounds checking
    return items[index].value;  // Will throw if index is out of bounds or items[index] is undefined
}

// Error Zone 3: Division by zero / NaN handling
function calculateRatio(numerator, denominator) {
    // BUG: No check for zero denominator
    const result = numerator / denominator;
    return result.toFixed(2);  // Will fail if result is NaN or Infinity
}

// Error Zone 4: Async callback issues  
function fetchDataAsync(callback) {
    setTimeout(() => {
        const data = { status: 'success' };
        // BUG: callback might not be a function
        callback(data);  // TypeError if callback is undefined
    }, 100);
}

// Error Zone 5: JSON parsing without try-catch
function parseConfig(configString) {
    // BUG: No error handling for invalid JSON
    const config = JSON.parse(configString);
    return config.settings.theme;  // May throw if structure is different
}

// Error Zone 6: Property access on null
function getUserEmail(user) {
    // BUG: user.contact might be null
    return user.contact.email;  // TypeError if contact is null
}

// Error Zone 7: Async/await without error handling
async function fetchExternalData(url) {
    // BUG: No try-catch, no timeout handling
    const response = await fetch(url);  // Will fail if fetch fails
    const data = await response.json();
    return data.results[0];  // Will fail if results is empty
}

// ==========================================
// Server Request Handler
// ==========================================

const server = http.createServer(async (req, res) => {
    const url = req.url;
    const method = req.method;
    
    // Parse request body for POST/PUT/PATCH
    let payload = {};
    if (['POST', 'PUT', 'PATCH'].includes(method)) {
        try {
            payload = await parseBody(req);
        } catch (e) {
            log('ERROR', 'Failed to parse request body', {
                endpoint: url,
                httpMethod: method,
                error: e
            });
            res.writeHead(400, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'Invalid request body' }));
            return;
        }
    }
    
    const autocureTry = isAutocureTry(payload);
    
    log('INFO', `Request received: ${method} ${url}`, {
        endpoint: url,
        httpMethod: method,
        payload: payload,
        isAutocureTry: autocureTry,
        metadata: { autocureTry }
    });
    
    try {
        // Route: Home / Health
        if (url === '/' || url === '/health') {
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ status: 'healthy', timestamp: new Date().toISOString() }));
            return;
        }
        
        // ==========================================
        // ERRORFUL API ENDPOINTS (for testing)
        // ==========================================
        
        // POST /api/user - Trigger TypeError on undefined user data
        if (url === '/api/user' && method === 'POST') {
            log('INFO', 'Processing user data request', {
                endpoint: url,
                httpMethod: method,
                payload: payload
            });
            
            // BUG: Uses payload.userData which might be undefined
            const result = processUserData(payload.userData);
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify(result));
            return;
        }
        
        // POST /api/items - Trigger array bounds error
        if (url === '/api/items' && method === 'POST') {
            log('INFO', 'Fetching item by index', {
                endpoint: url,
                httpMethod: method,
                payload: payload
            });
            
            const items = [{ value: 'a' }, { value: 'b' }];
            const index = payload.index || 10;  // Default to invalid index
            // BUG: No bounds checking
            const item = getItemAtIndex(items, index);
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ item }));
            return;
        }
        
        // POST /api/calculate - Trigger division by zero
        if (url === '/api/calculate' && method === 'POST') {
            log('INFO', 'Performing calculation', {
                endpoint: url,
                httpMethod: method,
                payload: payload
            });
            
            const numerator = payload.numerator || 100;
            const denominator = payload.denominator || 0;  // Default to zero
            // BUG: No check for zero denominator
            const ratio = calculateRatio(numerator, denominator);
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ ratio }));
            return;
        }
        
        // POST /api/profile - Trigger null property access
        if (url === '/api/profile' && method === 'POST') {
            log('INFO', 'Getting user email', {
                endpoint: url,
                httpMethod: method,
                payload: payload
            });
            
            // BUG: user.contact might be null/undefined
            const email = getUserEmail(payload.user || { contact: null });
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ email }));
            return;
        }
        
        // POST /api/config - Trigger JSON parsing error
        if (url === '/api/config' && method === 'POST') {
            log('INFO', 'Loading configuration', {
                endpoint: url,
                httpMethod: method,
                payload: payload
            });
            
            const configString = payload.configString || '{ invalid json }';
            // BUG: No error handling for invalid JSON
            const config = parseConfig(configString);
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ config }));
            return;
        }
        
        // Legacy GET endpoints (still errorful)
        if (url === '/api/user') {
            const result = processUserData(undefined);
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify(result));
            return;
        }
        
        if (url === '/api/items') {
            const items = [{ value: 'a' }, { value: 'b' }];
            const item = getItemAtIndex(items, 10);
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ item }));
            return;
        }
        
        // 404 for unknown routes
        res.writeHead(404, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Not Found' }));
        
    } catch (error) {
        // Log the error with full details for Self-Healer
        log('ERROR', `${error.name}: ${error.message}`, {
            endpoint: url,
            httpMethod: method,
            payload: payload,
            error: error,
            isAutocureTry: autocureTry,
            metadata: {
                stack: error.stack
            }
        });
        
        // Also write stack to file
        fs.appendFileSync(LOG_FILE, `${error.stack}\n`);
        
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ 
            error: error.name,
            message: error.message 
        }));
    }
});

// Global error handlers
process.on('uncaughtException', (error) => {
    log('ERROR', `Uncaught Exception: ${error.message}`, {
        error: error,
        metadata: { type: 'uncaughtException' }
    });
    fs.appendFileSync(LOG_FILE, `${error.stack}\n`);
});

process.on('unhandledRejection', (reason, promise) => {
    log('ERROR', `Unhandled Rejection: ${reason}`, {
        metadata: { type: 'unhandledRejection', reason: String(reason) }
    });
    fs.appendFileSync(LOG_FILE, `Unhandled Promise Rejection: ${reason}\n`);
});

// ==========================================
// Auto-Trigger Errors (for demonstration)
// ==========================================

function triggerRandomError() {
    const errorScenarios = [
        {
            name: 'TypeError',
            message: "Cannot read property 'name' of undefined",
            file: 'user_service.js',
            line: 42,
            fn: 'getUserName'
        },
        {
            name: 'ReferenceError', 
            message: "userDatabase is not defined",
            file: 'database.js',
            line: 128,
            fn: 'connectToDatabase'
        },
        {
            name: 'TypeError',
            message: "Cannot call method 'forEach' on null",
            file: 'data_processor.js',
            line: 67,
            fn: 'processItems'
        },
        {
            name: 'RangeError',
            message: "Maximum call stack size exceeded",
            file: 'recursive_util.js',
            line: 23,
            fn: 'calculateFactorial'
        },
        {
            name: 'SyntaxError',
            message: "Unexpected token 'undefined' in JSON at position 0",
            file: 'config_loader.js',
            line: 15,
            fn: 'parseConfig'
        },
        {
            name: 'TypeError',
            message: "Cannot convert undefined or null to object",
            file: 'object_utils.js',
            line: 89,
            fn: 'mergeObjects'
        }
    ];
    
    const scenario = errorScenarios[Math.floor(Math.random() * errorScenarios.length)];
    
    // Create a realistic stack trace
    const stack = `${scenario.name}: ${scenario.message}
    at ${scenario.fn} (${scenario.file}:${scenario.line}:12)
    at processRequest (server.js:145:8)
    at Server.handleRequest (server.js:89:5)
    at emitTwo (events.js:126:13)
    at Server.emit (events.js:214:7)`;
    
    log('ERROR', `${scenario.name}: ${scenario.message}`, {
        error: { 
            name: scenario.name, 
            message: scenario.message,
            stack: stack 
        },
        metadata: { 
            triggered: 'demo',
            file: scenario.file,
            line: scenario.line,
            function: scenario.fn
        }
    });
    
    fs.appendFileSync(LOG_FILE, `${stack}\n`);
}

// Start server (only when run directly)
if (require.main === module) {
    server.listen(PORT, () => {
        log('INFO', `Demo server starting on port ${PORT}`);
        log('INFO', 'Self-Healing Demo Server v2.0 initialized');
        log('INFO', `Log file: ${LOG_FILE}`);
        if (selfHealerClient) {
            log('INFO', 'Connected to Self-Healer WebSocket');
        }
        
        // Trigger an error after 5 seconds for demonstration
        setTimeout(() => {
            log('INFO', 'Triggering demonstration error...');
            triggerRandomError();
        }, 5000);
        
        // Continue triggering errors periodically (every 60 seconds)
        setInterval(() => {
            log('INFO', 'Triggering periodic error for demonstration...');
            triggerRandomError();
        }, 15000);
    });
}

// Export for testing
module.exports = { 
    server, 
    processUserData, 
    getItemAtIndex, 
    calculateRatio,
    getUserEmail,
    parseConfig
};
