/**
 * Demo Node.js Server with Intentional Errors
 * This server is designed to demonstrate the Self-Healing System capabilities.
 * It contains various intentional errors that will be triggered over time.
 */

const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = process.env.PORT || 3000;
const LOG_FILE = process.env.LOG_FILE || path.join(__dirname, '..', 'logs', 'service.log');

// Ensure log directory exists
const logDir = path.dirname(LOG_FILE);
if (!fs.existsSync(logDir)) {
    fs.mkdirSync(logDir, { recursive: true });
}

// Logger utility
function log(level, message) {
    const timestamp = new Date().toISOString();
    const logMessage = `[${timestamp}] [${level}] ${message}\n`;
    console.log(logMessage.trim());
    fs.appendFileSync(LOG_FILE, logMessage);
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

// ==========================================
// Server Request Handler
// ==========================================

const server = http.createServer((req, res) => {
    const url = req.url;
    log('INFO', `Request received: ${req.method} ${url}`);
    
    try {
        // Route: Home
        if (url === '/' || url === '/health') {
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ status: 'healthy', timestamp: new Date().toISOString() }));
            return;
        }
        
        // Route: Trigger Error 1 - Undefined user data
        if (url === '/api/user') {
            log('INFO', 'Processing user data request');
            // This will trigger an error - userData is undefined
            const result = processUserData(undefined);
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify(result));
            return;
        }
        
        // Route: Trigger Error 2 - Array bounds
        if (url === '/api/items') {
            log('INFO', 'Fetching items');
            const items = [{ value: 'a' }, { value: 'b' }];
            // This will trigger an error - accessing index 10 in a 2-element array
            const item = getItemAtIndex(items, 10);
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ item }));
            return;
        }
        
        // Route: Trigger Error 3 - Division
        if (url === '/api/calculate') {
            log('INFO', 'Performing calculation');
            // This will cause issues with zero denominator
            const ratio = calculateRatio(100, 0);
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ ratio }));
            return;
        }
        
        // Route: Trigger Error 4 - Callback
        if (url === '/api/fetch') {
            log('INFO', 'Fetching async data');
            // This will trigger an error - undefined callback
            fetchDataAsync(undefined);
            res.writeHead(202, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ status: 'processing' }));
            return;
        }
        
        // Route: Trigger Error 5 - JSON parsing
        if (url === '/api/config') {
            log('INFO', 'Loading configuration');
            // This will trigger an error - invalid JSON
            const config = parseConfig('{ invalid json }');
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ config }));
            return;
        }
        
        // 404 for unknown routes
        res.writeHead(404, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Not Found' }));
        
    } catch (error) {
        // Log the error with full stack trace (this is what the self-healer will catch)
        log('ERROR', `${error.name}: ${error.message}`);
        console.error(error.stack);
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
    log('ERROR', `Uncaught Exception: ${error.message}`);
    console.error(error.stack);
    fs.appendFileSync(LOG_FILE, `${error.stack}\n`);
});

process.on('unhandledRejection', (reason, promise) => {
    log('ERROR', `Unhandled Rejection: ${reason}`);
    console.error(reason);
    fs.appendFileSync(LOG_FILE, `Unhandled Promise Rejection: ${reason}\n`);
});

// ==========================================
// Auto-Trigger Errors (for demonstration)
// ==========================================

function triggerRandomError() {
    const errors = [
        () => processUserData(undefined),
        () => getItemAtIndex([], 5),
        () => calculateRatio(1, 0),
        () => fetchDataAsync(undefined),
        () => parseConfig('not valid json'),
    ];
    
    const randomIndex = Math.floor(Math.random() * errors.length);
    try {
        errors[randomIndex]();
    } catch (error) {
        log('ERROR', `${error.name}: ${error.message}`);
        fs.appendFileSync(LOG_FILE, `${error.stack}\n`);
    }
}

// Start server
server.listen(PORT, () => {
    log('INFO', `Demo server starting on port ${PORT}`);
    log('INFO', 'Self-Healing Demo Server initialized');
    log('INFO', `Log file: ${LOG_FILE}`);
    
    // Trigger an error after 5 seconds for demonstration
    setTimeout(() => {
        log('INFO', 'Triggering demonstration error...');
        triggerRandomError();
    }, 5000);
    
    // Continue triggering errors periodically (every 30 seconds)
    setInterval(() => {
        log('INFO', 'Triggering periodic error for demonstration...');
        triggerRandomError();
    }, 30000);
});

module.exports = { server, processUserData, getItemAtIndex, calculateRatio };
