# AutoCure Handler Integration Guide

> Drop-in error handlers that stream errors to the Self-Healing (AutoCure) system over WebSocket.

## How It Works

Your service connects to the AutoCure server via WebSocket at:

```
ws://<host>:<port>/ws/logs/<user_id>
```

When an error occurs, the handler sends a **LogEntry** JSON message:

```json
{
  "timestamp": "2026-03-11T09:30:00.000Z",
  "level": "ERROR",
  "message": "ZeroDivisionError: division by zero",
  "source": "my-service",
  "source_file": "/app/routes.py",
  "line_number": 42,
  "stack_trace": "Traceback (most recent call last):\n  ...",
  "metadata": {}
}
```

The server then: analyzes the error with AI → traces the AST → generates fix proposals → sends an email report.

---

## Python

### Install

```bash
pip install websocket-client python-dotenv
# OR for async apps:
pip install websockets python-dotenv
```

### Setup

1. Copy `autocure_handler.py` to your project root.
2. Create a `.env` file:

```env
AUTOCURE_WS_URL=ws://localhost:9000/ws/logs/my-service
AUTOCURE_SERVICE=my-service
```

3. Add **two lines** at the top of your main file:

```python
from autocure_handler import attach_autocure
attach_autocure()
```

That's it. Every `logging.error()` or unhandled exception caught by your global error handler will be sent to AutoCure.

### Flask Example

```python
from flask import Flask, jsonify, request
import logging
from autocure_handler import attach_autocure

attach_autocure()

app = Flask(__name__)

@app.errorhandler(Exception)
def handle_exception(e):
    logging.error("Unhandled: %s %s: %s", request.method, request.path, e, exc_info=True)
    return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    app.run(port=5000)
```

### FastAPI Example

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import logging
from autocure_handler import attach_autocure

attach_autocure()

app = FastAPI()

@app.exception_handler(Exception)
async def global_handler(request: Request, exc: Exception):
    logging.error("Unhandled: %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse({"error": str(exc)}, status_code=500)
```

### Django Example

In `settings.py`:
```python
from autocure_handler import attach_autocure
attach_autocure()

LOGGING = {
    'version': 1,
    'handlers': {
        'autocure': {
            'class': 'autocure_handler._SyncWSHandler',
            'ws_url': 'ws://localhost:9000/ws/logs/my-django',
            'service_name': 'my-django',
        }
    },
    'root': {
        'handlers': ['autocure'],
        'level': 'ERROR',
    },
}
```

Or simply call `attach_autocure()` in your `wsgi.py` / `asgi.py`.

---

## JavaScript / Node.js

### Install

```bash
npm install ws dotenv
```

### Setup

1. Copy `autocure_handler.js` to your project root.
2. Create a `.env` file:

```env
AUTOCURE_WS_URL=ws://localhost:9000/ws/logs/my-service
AUTOCURE_SERVICE=my-service
```

3. Add to your entry point:

```javascript
require('dotenv').config();
const autocure = require('./autocure_handler');
autocure.attach();
```

### Express Example

```javascript
require('dotenv').config();
const express = require('express');
const autocure = require('./autocure_handler');

autocure.attach();

const app = express();

app.get('/test-error', (req, res) => {
  throw new Error('Test error');
});

// AutoCure error middleware — MUST be after all routes
app.use(autocure.expressErrorHandler());

// Default error handler
app.use((err, req, res, next) => {
  res.status(500).json({ error: err.message });
});

app.listen(3000);
```

### Fastify Example

```javascript
require('dotenv').config();
const fastify = require('fastify')();
const autocure = require('./autocure_handler');

autocure.attach();
fastify.register(autocure.fastifyPlugin);

fastify.get('/test-error', async () => {
  throw new Error('Test error');
});

fastify.listen({ port: 3000 });
```

### Manual Error Sending

```javascript
const autocure = require('./autocure_handler');
autocure.attach();

try {
  riskyOperation();
} catch (err) {
  autocure.sendError(err, { context: 'payment processing', userId: 123 });
}
```

---

## Java (Spring Boot)

No pre-built handler — implement using the WebSocket protocol directly.

### Dependencies (Maven)

```xml
<dependency>
  <groupId>org.java-websocket</groupId>
  <artifactId>Java-WebSocket</artifactId>
  <version>1.5.4</version>
</dependency>
```

### Handler

```java
import org.java_websocket.client.WebSocketClient;
import org.java_websocket.handshake.ServerHandshake;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.net.URI;
import java.time.Instant;
import java.util.Map;

public class AutoCureHandler {
    private static final Logger log = LoggerFactory.getLogger(AutoCureHandler.class);
    private static WebSocketClient ws;
    private static String wsUrl;
    private static String serviceName;
    private static final ObjectMapper mapper = new ObjectMapper();

    public static void attach(String url, String service) {
        wsUrl = url;
        serviceName = service;
        connect();
    }

    private static void connect() {
        try {
            ws = new WebSocketClient(new URI(wsUrl)) {
                @Override public void onOpen(ServerHandshake h) { log.info("[AutoCure] Connected"); }
                @Override public void onMessage(String msg) {}
                @Override public void onClose(int code, String reason, boolean remote) { ws = null; }
                @Override public void onError(Exception ex) { ws = null; }
            };
            ws.connect();
        } catch (Exception e) {
            log.warn("[AutoCure] Connection failed: {}", e.getMessage());
        }
    }

    public static void sendError(Throwable error, Map<String, Object> metadata) {
        if (ws == null || !ws.isOpen()) connect();
        if (ws == null || !ws.isOpen()) return;

        try {
            var payload = Map.of(
                "timestamp", Instant.now().toString(),
                "level", "ERROR",
                "message", error.getClass().getSimpleName() + ": " + error.getMessage(),
                "source", serviceName,
                "source_file", error.getStackTrace().length > 0 ? error.getStackTrace()[0].getFileName() : "",
                "line_number", error.getStackTrace().length > 0 ? error.getStackTrace()[0].getLineNumber() : 0,
                "stack_trace", getStackTraceString(error),
                "metadata", metadata != null ? metadata : Map.of()
            );
            ws.send(mapper.writeValueAsString(payload));
        } catch (Exception e) {
            log.warn("[AutoCure] Send failed: {}", e.getMessage());
        }
    }

    private static String getStackTraceString(Throwable t) {
        var sw = new java.io.StringWriter();
        t.printStackTrace(new java.io.PrintWriter(sw));
        return sw.toString();
    }
}
```

### Spring Boot Integration

```java
@ControllerAdvice
public class GlobalExceptionHandler {
    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, String>> handleAll(Exception ex) {
        AutoCureHandler.sendError(ex, Map.of("trigger", "globalHandler"));
        return ResponseEntity.status(500).body(Map.of("error", ex.getMessage()));
    }
}

// In your Application class:
@PostConstruct
public void initAutoCure() {
    AutoCureHandler.attach(
        "ws://localhost:9000/ws/logs/my-spring-app",
        "my-spring-app"
    );
}
```

---

## Go

### Handler

```go
package autocure

import (
	"encoding/json"
	"fmt"
	"runtime"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

var (
	conn        *websocket.Conn
	wsURL       string
	serviceName string
	mu          sync.Mutex
)

type LogEntry struct {
	Timestamp  string            `json:"timestamp"`
	Level      string            `json:"level"`
	Message    string            `json:"message"`
	Source     string            `json:"source"`
	SourceFile string            `json:"source_file"`
	LineNumber int               `json:"line_number"`
	StackTrace string            `json:"stack_trace,omitempty"`
	Metadata   map[string]string `json:"metadata,omitempty"`
}

func Attach(url, service string) {
	wsURL = url
	serviceName = service
	connect()
}

func connect() {
	mu.Lock()
	defer mu.Unlock()
	var err error
	conn, _, err = websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		conn = nil
	}
}

func SendError(err error, metadata map[string]string) {
	mu.Lock()
	defer mu.Unlock()

	if conn == nil {
		mu.Unlock()
		connect()
		mu.Lock()
	}
	if conn == nil {
		return
	}

	_, file, line, _ := runtime.Caller(1)

	entry := LogEntry{
		Timestamp:  time.Now().UTC().Format(time.RFC3339),
		Level:      "ERROR",
		Message:    fmt.Sprintf("%T: %s", err, err.Error()),
		Source:     serviceName,
		SourceFile: file,
		LineNumber: line,
		StackTrace: fmt.Sprintf("%+v", err),
		Metadata:   metadata,
	}

	data, _ := json.Marshal(entry)
	if writeErr := conn.WriteMessage(websocket.TextMessage, data); writeErr != nil {
		conn.Close()
		conn = nil
	}
}

// RecoverMiddleware is an HTTP middleware for net/http or chi/mux.
func RecoverMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			if rec := recover(); rec != nil {
				err, ok := rec.(error)
				if !ok {
					err = fmt.Errorf("%v", rec)
				}
				SendError(err, map[string]string{
					"method": r.Method,
					"path":   r.URL.Path,
				})
				http.Error(w, "Internal Server Error", 500)
			}
		}()
		next.ServeHTTP(w, r)
	})
}
```

### Usage

```go
func main() {
    autocure.Attach("ws://localhost:9000/ws/logs/my-go-app", "my-go-app")

    mux := http.NewServeMux()
    mux.HandleFunc("/test-error", func(w http.ResponseWriter, r *http.Request) {
        panic("intentional error for testing")
    })

    handler := autocure.RecoverMiddleware(mux)
    http.ListenAndServe(":3000", handler)
}
```

---

## Ruby (Rails)

### Gemfile

```ruby
gem 'websocket-client-simple'
```

### Initializer (`config/initializers/autocure.rb`)

```ruby
require 'websocket-client-simple'
require 'json'

module AutoCure
  @ws = nil
  @url = ENV['AUTOCURE_WS_URL'] || ''
  @service = ENV['AUTOCURE_SERVICE'] || 'rails-app'

  def self.connect
    return if @url.empty?
    @ws = WebSocket::Client::Simple.connect(@url)
  rescue => e
    Rails.logger.warn "[AutoCure] Connect failed: #{e.message}"
    @ws = nil
  end

  def self.send_error(exception, metadata = {})
    connect if @ws.nil?
    return if @ws.nil?

    payload = {
      timestamp: Time.now.utc.iso8601,
      level: 'ERROR',
      message: "#{exception.class}: #{exception.message}",
      source: @service,
      source_file: exception.backtrace&.first&.split(':')&.first || '',
      line_number: exception.backtrace&.first&.split(':')&.[](1)&.to_i || 0,
      stack_trace: exception.backtrace&.join("\n") || '',
      metadata: metadata,
    }
    @ws.send(payload.to_json)
  rescue => e
    @ws = nil
  end
end

# Hook into Rails exception reporting
Rails.application.config.after_initialize do
  ActiveSupport::Notifications.subscribe('process_action.action_controller') do |*args|
    event = ActiveSupport::Notifications::Event.new(*args)
    if event.payload[:exception_object]
      AutoCure.send_error(event.payload[:exception_object])
    end
  end
end
```

---

## Generic: Any Language

Any language that supports WebSocket can integrate. The protocol is simple:

1. **Connect** to `ws://<host>:<port>/ws/logs/<user_id>`
2. **Send** a JSON message on each error:

```json
{
  "timestamp": "ISO 8601 string",
  "level": "ERROR",
  "message": "ErrorType: description",
  "source": "your-service-name",
  "source_file": "/path/to/file.ext",
  "line_number": 42,
  "stack_trace": "full stack trace string",
  "metadata": { "any": "extra context" }
}
```

3. The server responds with `{"type": "error_received", ...}` and begins analysis.

### Required fields
| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | string | ISO 8601 UTC timestamp |
| `level` | string | `ERROR`, `FATAL`, or `CRITICAL` |
| `message` | string | Error description |
| `source` | string | Service name |

### Optional fields
| Field | Type | Description |
|-------|------|-------------|
| `source_file` | string | File where error occurred |
| `line_number` | int | Line number |
| `stack_trace` | string | Full stack trace |
| `metadata` | object | Any extra context |
| `payload` | object | Additional data |
| `is_autocure_try` | bool | True if this is an auto-fix retry |

---

## Registration

Before your handler can connect, the service must be registered:

```bash
curl -X POST http://localhost:9000/api/v1/register \
  -H "Content-Type: application/json" \
  -b "session_token=<token>" \
  -d '{
    "user_id": "my-service",
    "repo_url": "https://github.com/org/repo",
    "email": "dev@example.com",
    "base_branch": "main"
  }'
```

Or register through the dashboard UI at `http://localhost:9000/`.
