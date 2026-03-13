/**
 * WebSocket Client Snippet for Node.js Services
 * Self-Healing Software System v2.0
 *
 * Add this to your Node.js service to stream logs to the Self-Healing system.
 *
 * Usage:
 *   1. Copy this file to your project
 *   2. Install: npm install ws
 *   3. Import and initialize the client
 *
 * Example:
 *   const SelfHealerClient = require('./self-healer-client');
 *
 *   const client = new SelfHealerClient({
 *     serverUrl: 'ws://localhost:9292/ws/logs/your-user-id',
 *     serviceName: 'my-node-service'
 *   });
 *
 *   client.connect();
 *
 *   // Later in your code:
 *   client.info('Request processed', { requestId: '123' });
 *   client.error('Failed to save user', { userId: 456 }, { endpoint: '/api/users', method: 'POST' });
 */

const WebSocket = require('ws');

class SelfHealerClient {
    /**
     * Create a new Self-Healer client.
     * @param {Object} options - Configuration options
     * @param {string} options.serverUrl - WebSocket URL (e.g., ws://localhost:9292/ws/logs/user123)
     * @param {string} [options.serviceName='unknown'] - Name of your service
     * @param {boolean} [options.autoReconnect=true] - Auto-reconnect on disconnect
     * @param {number} [options.reconnectDelay=5000] - Milliseconds before reconnecting
     */
    constructor(options) {
        this.serverUrl = options.serverUrl;
        this.serviceName = options.serviceName || 'unknown';
        this.autoReconnect = options.autoReconnect !== false;
        this.reconnectDelay = options.reconnectDelay || 5000;

        this.ws = null;
        this.connected = false;
        this.messageQueue = [];
        this.reconnectTimeout = null;
    }

    /**
     * Connect to the Self-Healer server.
     */
    connect() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            return;
        }

        try {
            this.ws = new WebSocket(this.serverUrl);

            this.ws.on('open', () => {
                console.log(`[Self-Healer] Connected to ${this.serverUrl}`);
                this.connected = true;
                this._flushQueue();
            });

            this.ws.on('message', (data) => {
                try {
                    const message = JSON.parse(data.toString());
                    this._handleMessage(message);
                } catch (e) {
                    console.error('[Self-Healer] Failed to parse message:', e);
                }
            });

            this.ws.on('close', () => {
                console.log('[Self-Healer] Disconnected');
                this.connected = false;
                this._scheduleReconnect();
            });

            this.ws.on('error', (error) => {
                console.error('[Self-Healer] Connection error:', error.message);
                this.connected = false;
            });
        } catch (error) {
            console.error('[Self-Healer] Failed to connect:', error.message);
            this._scheduleReconnect();
        }
    }

    /**
     * Disconnect from the server.
     */
    disconnect() {
        this.autoReconnect = false;
        if (this.reconnectTimeout) {
            clearTimeout(this.reconnectTimeout);
        }
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }

    /**
     * Handle incoming messages from the server.
     * @private
     */
    _handleMessage(message) {
        switch (message.type) {
            case 'error_received':
                console.log('[Self-Healer] Error acknowledged');
                break;
            case 'error':
                console.warn('[Self-Healer] Server error:', message.payload?.message);
                break;
            default:
                console.log('[Self-Healer] Message:', message);
        }
    }

    /**
     * Schedule a reconnection attempt.
     * @private
     */
    _scheduleReconnect() {
        if (!this.autoReconnect) return;

        this.reconnectTimeout = setTimeout(() => {
            console.log('[Self-Healer] Attempting to reconnect...');
            this.connect();
        }, this.reconnectDelay);
    }

    /**
     * Flush queued messages after connecting.
     * @private
     */
    _flushQueue() {
        while (this.messageQueue.length > 0) {
            const message = this.messageQueue.shift();
            this._send(message);
        }
    }

    /**
     * Send a message to the server.
     * @private
     */
    _send(message) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(message));
        } else {
            // Queue for later if not connected
            this.messageQueue.push(message);
        }
    }

    /**
     * Queue a log entry.
     * @private
     */
    _log(level, message, metadata = null, options = {}) {
        const logEntry = {
            timestamp: new Date().toISOString(),
            level: level,
            message: message,
            source: this.serviceName,
            metadata: metadata,
            payload: options.payload || null,
            api_endpoint: options.endpoint || options.apiEndpoint || null,
            http_method: options.method || options.httpMethod || null,
            stack_trace: options.stackTrace || null,
            is_autocure_try: options.isAutocureTry || false,
        };

        this._send(logEntry);
    }

    /**
     * Log a debug message.
     * @param {string} message - Log message
     * @param {Object} [metadata] - Additional context
     * @param {Object} [options] - Additional options
     */
    debug(message, metadata = null, options = {}) {
        this._log('DEBUG', message, metadata, options);
    }

    /**
     * Log an info message.
     * @param {string} message - Log message
     * @param {Object} [metadata] - Additional context
     * @param {Object} [options] - Additional options
     */
    info(message, metadata = null, options = {}) {
        this._log('INFO', message, metadata, options);
    }

    /**
     * Log a warning message.
     * @param {string} message - Log message
     * @param {Object} [metadata] - Additional context
     * @param {Object} [options] - Additional options
     */
    warning(message, metadata = null, options = {}) {
        this._log('WARNING', message, metadata, options);
    }

    /**
     * Log an error message.
     * @param {string} message - Error message
     * @param {Object} [metadata] - Additional context
     * @param {Object} [options] - Additional options
     * @param {Object} [options.payload] - Request payload that caused the error
     * @param {string} [options.endpoint] - API endpoint
     * @param {string} [options.method] - HTTP method
     * @param {Error} [options.error] - Error object (will extract stack trace)
     */
    error(message, metadata = null, options = {}) {
        if (options.error instanceof Error) {
            options.stackTrace = options.error.stack;
        }
        this._log('ERROR', message, metadata, options);
    }

    /**
     * Log a critical message.
     * @param {string} message - Log message
     * @param {Object} [metadata] - Additional context
     * @param {Object} [options] - Additional options
     */
    critical(message, metadata = null, options = {}) {
        this._log('CRITICAL', message, metadata, options);
    }

    /**
     * Create a middleware for Express.js to automatically log requests.
     * @returns {Function} Express middleware
     */
    expressMiddleware() {
        return (req, res, next) => {
            const start = Date.now();

            // Capture original end
            const originalEnd = res.end;
            res.end = (...args) => {
                const duration = Date.now() - start;
                const level = res.statusCode >= 500 ? 'ERROR' : 
                              res.statusCode >= 400 ? 'WARNING' : 'INFO';

                this._log(level, `${req.method} ${req.path} - ${res.statusCode}`, {
                    duration: `${duration}ms`,
                    userAgent: req.get('user-agent'),
                    ip: req.ip,
                }, {
                    endpoint: req.path,
                    method: req.method,
                    payload: req.body,
                    isAutocureTry: req.body?.['autocure-try'] === true,
                });

                originalEnd.apply(res, args);
            };

            next();
        };
    }

    /**
     * Create an error handler middleware for Express.js.
     * @returns {Function} Express error handler middleware
     */
    expressErrorHandler() {
        return (err, req, res, next) => {
            this.error(err.message, {
                path: req.path,
                method: req.method,
            }, {
                endpoint: req.path,
                method: req.method,
                payload: req.body,
                error: err,
                isAutocureTry: req.body?.['autocure-try'] === true,
            });

            // Pass to next error handler
            next(err);
        };
    }
}

/**
 * Create and connect a Self-Healer client.
 * @param {string} userId - Your user ID in the Self-Healing system
 * @param {Object} [options] - Additional options
 * @returns {SelfHealerClient} Connected client instance
 */
function createClient(userId, options = {}) {
    const serverHost = options.serverHost || 'localhost';
    const serverPort = options.serverPort || 9292;
    const serverUrl = `ws://${serverHost}:${serverPort}/ws/logs/${userId}`;

    const client = new SelfHealerClient({
        serverUrl,
        serviceName: options.serviceName || 'node-service',
        autoReconnect: options.autoReconnect,
        reconnectDelay: options.reconnectDelay,
    });

    client.connect();
    return client;
}

module.exports = SelfHealerClient;
module.exports.createClient = createClient;


// Example usage (run this file directly to test)
if (require.main === module) {
    console.log('Testing Self-Healer client...');

    const client = createClient('demo-user', {
        serviceName: 'demo-node-service'
    });

    setTimeout(() => {
        client.info('Service started', { version: '1.0.0' });
    }, 1000);

    setTimeout(() => {
        client.info('Processing request', {
            requestId: 'req-123'
        }, {
            endpoint: '/api/users',
            method: 'POST',
            payload: { name: 'John', email: 'john@example.com' }
        });
    }, 2000);

    setTimeout(() => {
        // Simulate an error
        try {
            throw new Error('Something went wrong!');
        } catch (e) {
            client.error('Failed to process request', {
                function: 'processUser'
            }, {
                endpoint: '/api/users',
                method: 'POST',
                payload: { name: 'John', email: 'john@example.com' },
                error: e
            });
        }
    }, 3000);

    setTimeout(() => {
        console.log('Done! Check the Self-Healer server for received logs.');
        client.disconnect();
        process.exit(0);
    }, 5000);
}
