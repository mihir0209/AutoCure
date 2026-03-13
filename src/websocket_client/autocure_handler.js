/**
 * AutoCure Error Handler — Lightweight WebSocket Logger for Node.js
 * =================================================================
 *
 * Drop-in error handler for any Node.js / Express / Fastify service.
 * Captures unhandled errors and sends them to the AutoCure (Self-Healing)
 * WebSocket server.
 *
 * Design:
 *   - Runs in the CODE'S OWN THREAD (Node.js single-thread model).
 *   - Lazy-connects on first error, auto-reconnects on failure.
 *   - Tiny footprint: one WebSocket send() per error, no polling.
 *
 * Quick start (any Node.js app):
 *
 *   require('dotenv').config();                 // optional
 *   const autocure = require('./autocure_handler');
 *
 *   autocure.attach();                          // reads env vars
 *
 *   // Errors are now captured automatically via:
 *   //   process.on('uncaughtException')
 *   //   process.on('unhandledRejection')
 *
 * Express middleware:
 *
 *   const autocure = require('./autocure_handler');
 *   autocure.attach();
 *
 *   app.use(autocure.expressErrorHandler());    // after all routes
 *
 * Manual send:
 *
 *   autocure.sendError(new Error('Something broke'), { route: '/api/users' });
 *
 * Environment variables (or .env file):
 *   AUTOCURE_WS_URL    = ws://localhost:9000/ws/logs/<user_id>
 *   AUTOCURE_SERVICE   = my-service-name    (default: node-service)
 */

'use strict';

let WebSocket;
try {
  WebSocket = require('ws');
} catch (_) {
  // Will warn on attach()
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let _ws = null;
let _wsUrl = '';
let _serviceName = 'node-service';
let _connected = false;
let _connecting = false;
let _attached = false;

// ---------------------------------------------------------------------------
// Connection management (lazy + reconnect)
// ---------------------------------------------------------------------------
function _ensureConnected() {
  if (_connected && _ws && _ws.readyState === WebSocket.OPEN) {
    return true;
  }
  if (_connecting) return false;

  _connecting = true;
  try {
    _ws = new WebSocket(_wsUrl);

    _ws.on('open', () => {
      _connected = true;
      _connecting = false;
    });

    _ws.on('close', () => {
      _connected = false;
      _ws = null;
    });

    _ws.on('error', (err) => {
      _connected = false;
      _connecting = false;
      _ws = null;
    });
  } catch (err) {
    _connecting = false;
    _ws = null;
    return false;
  }
  return false; // not yet open — caller should retry on next error
}

function _close() {
  try {
    if (_ws) _ws.close();
  } catch (_) {}
  _ws = null;
  _connected = false;
}

// ---------------------------------------------------------------------------
// Payload builder
// ---------------------------------------------------------------------------
function _buildPayload(error, metadata) {
  const stack = error.stack || '';
  // Try to extract source file and line from stack trace
  let sourceFile = '';
  let lineNumber = 0;
  const match = stack.match(/at\s+.+?\s+\((.+?):(\d+):\d+\)/);
  if (match) {
    sourceFile = match[1];
    lineNumber = parseInt(match[2], 10);
  } else {
    const match2 = stack.match(/at\s+(.+?):(\d+):\d+/);
    if (match2) {
      sourceFile = match2[1];
      lineNumber = parseInt(match2[2], 10);
    }
  }

  return {
    timestamp: new Date().toISOString(),
    level: 'ERROR',
    message: `${error.name || 'Error'}: ${error.message}`,
    source: _serviceName,
    source_file: sourceFile,
    line_number: lineNumber,
    stack_trace: stack,
    metadata: Object.assign({ type: error.name || 'Error' }, metadata || {}),
  };
}

// ---------------------------------------------------------------------------
// Send function
// ---------------------------------------------------------------------------
function _send(payload) {
  try {
    if (!_connected || !_ws || _ws.readyState !== WebSocket.OPEN) {
      _ensureConnected();
      // Queue a retry after connection opens
      if (_ws) {
        const handler = () => {
          try {
            _ws.send(JSON.stringify(payload));
          } catch (_) {}
          _ws.removeListener('open', handler);
        };
        _ws.on('open', handler);
      }
      return;
    }
    _ws.send(JSON.stringify(payload));
  } catch (err) {
    _close();
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Send an error to the AutoCure server.
 * @param {Error} error - The error object
 * @param {Object} [metadata] - Optional metadata (route, method, etc.)
 */
function sendError(error, metadata) {
  if (!_wsUrl) return;
  const payload = _buildPayload(error, metadata);
  _send(payload);
}

/**
 * Attach AutoCure to global error handlers.
 * @param {Object} [options]
 * @param {string} [options.wsUrl]       - WebSocket URL (default: env AUTOCURE_WS_URL)
 * @param {string} [options.serviceName] - Service name (default: env AUTOCURE_SERVICE)
 */
function attach(options) {
  if (_attached) return;

  if (!WebSocket) {
    console.warn('[AutoCure] "ws" package not installed. Run: npm install ws');
    return;
  }

  const opts = options || {};
  _wsUrl = opts.wsUrl || process.env.AUTOCURE_WS_URL || '';
  _serviceName = opts.serviceName || process.env.AUTOCURE_SERVICE || 'node-service';

  if (!_wsUrl) {
    console.warn('[AutoCure] AUTOCURE_WS_URL not set — handler disabled');
    return;
  }

  // Hook into global unhandled errors
  process.on('uncaughtException', (err) => {
    sendError(err, { trigger: 'uncaughtException' });
    // Let the default handler run (which exits the process)
  });

  process.on('unhandledRejection', (reason) => {
    const err = reason instanceof Error ? reason : new Error(String(reason));
    sendError(err, { trigger: 'unhandledRejection' });
  });

  _attached = true;

  // Eagerly connect
  _ensureConnected();

  console.log(`[AutoCure] Handler attached → ${_wsUrl}`);
}

/**
 * Returns Express error-handling middleware.
 * Place AFTER all routes:  app.use(autocure.expressErrorHandler())
 */
function expressErrorHandler() {
  return function autocureErrorMiddleware(err, req, res, next) {
    sendError(err, {
      method: req.method,
      path: req.originalUrl || req.url,
      trigger: 'expressMiddleware',
    });
    next(err);
  };
}

/**
 * Returns a Fastify error handler plugin.
 * Usage:  fastify.register(autocure.fastifyPlugin)
 */
function fastifyPlugin(fastify, _opts, done) {
  fastify.setErrorHandler((error, request, reply) => {
    sendError(error, {
      method: request.method,
      path: request.url,
      trigger: 'fastifyErrorHandler',
    });
    reply.status(500).send({ error: error.message });
  });
  done();
}

module.exports = {
  attach,
  sendError,
  expressErrorHandler,
  fastifyPlugin,
};
