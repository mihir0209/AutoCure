import React, { useState, useEffect, useRef, useCallback } from "react";

const WS_URL = "ws://localhost:8000/ws/dashboard";

const EVENT_COLORS = {
  error:    "bg-red-900/40 border-red-700/50 text-red-300",
  warning:  "bg-amber-900/40 border-amber-700/50 text-amber-300",
  analysis: "bg-blue-900/40 border-blue-700/50 text-blue-300",
  fix:      "bg-green-900/40 border-green-700/50 text-green-300",
  pr:       "bg-purple-900/40 border-purple-700/50 text-purple-300",
  info:     "bg-slate-800 border-slate-700 text-slate-300",
};

const EVENT_ICONS = {
  error: "🔴", warning: "🟡", analysis: "🔍",
  fix: "✅", pr: "🔀", info: "ℹ️",
};

export default function LiveFeed() {
  const [events, setEvents] = useState([]);
  const [connected, setConnected] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const [paused, setPaused] = useState(false);
  const [filter, setFilter] = useState("all");
  const wsRef = useRef(null);
  const scrollRef = useRef(null);
  const reconnectTimer = useRef(null);

  const connect = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState <= 1) return;
    setReconnecting(true);

    try {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        setReconnecting(false);
        addSystemEvent("Connected to AutoCure live feed");
      };

      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (!paused) {
            setEvents((prev) => [
              ...prev.slice(-499), // keep last 500
              {
                id: Date.now() + Math.random(),
                time: new Date().toISOString(),
                type: data.type || data.event_type || "info",
                message: data.message || data.msg || JSON.stringify(data),
                details: data,
              },
            ]);
          }
        } catch {
          if (!paused) {
            setEvents((prev) => [
              ...prev.slice(-499),
              {
                id: Date.now(),
                time: new Date().toISOString(),
                type: "info",
                message: e.data,
                details: null,
              },
            ]);
          }
        }
      };

      ws.onclose = () => {
        setConnected(false);
        addSystemEvent("Disconnected – will retry in 5s");
        reconnectTimer.current = setTimeout(connect, 5000);
      };

      ws.onerror = () => {
        setConnected(false);
      };
    } catch {
      setReconnecting(false);
    }
  }, [paused]);

  function addSystemEvent(msg) {
    setEvents((prev) => [
      ...prev.slice(-499),
      { id: Date.now(), time: new Date().toISOString(), type: "info", message: msg, details: null },
    ]);
  }

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [connect]);

  // auto-scroll
  useEffect(() => {
    if (!paused && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events, paused]);

  const filtered = filter === "all" ? events : events.filter((e) => e.type === filter);

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* toolbar */}
      <div className="bg-slate-800 border-b border-slate-700 px-4 py-2 flex items-center gap-3 shrink-0">
        <span className="flex items-center gap-1.5 text-sm font-medium">
          <span
            className={`w-2 h-2 rounded-full ${connected ? "bg-green-400 animate-pulse-dot" : "bg-red-500"}`}
          />
          {connected ? "Live" : reconnecting ? "Connecting…" : "Offline"}
        </span>

        <div className="flex gap-1 ml-4">
          {["all", "error", "warning", "analysis", "fix", "pr"].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-2 py-0.5 rounded text-xs font-medium capitalize transition-colors ${
                filter === f ? "bg-blue-600 text-white" : "bg-slate-700 text-slate-400 hover:text-white"
              }`}
            >
              {f}
            </button>
          ))}
        </div>

        <div className="flex-1" />

        <button
          onClick={() => setPaused((p) => !p)}
          className={`px-3 py-1 rounded text-xs font-medium ${
            paused ? "bg-amber-600 text-white" : "bg-slate-700 text-slate-400 hover:text-white"
          }`}
        >
          {paused ? "▶ Resume" : "⏸ Pause"}
        </button>
        <button
          onClick={() => setEvents([])}
          className="px-3 py-1 rounded text-xs font-medium bg-slate-700 text-slate-400 hover:text-white"
        >
          🗑 Clear
        </button>
        <span className="text-xs text-slate-500">{filtered.length} events</span>
      </div>

      {/* event stream */}
      <div ref={scrollRef} className="flex-1 overflow-auto p-4 space-y-1.5">
        {filtered.length === 0 ? (
          <div className="flex items-center justify-center h-full text-slate-500 text-sm">
            <div className="text-center">
              <div className="text-4xl mb-3">📡</div>
              <p>Waiting for events…</p>
              <p className="text-xs mt-1">
                {connected ? "Connected – events will appear here" : "Trying to connect to backend"}
              </p>
            </div>
          </div>
        ) : (
          filtered.map((ev) => {
            const colorClass = EVENT_COLORS[ev.type] || EVENT_COLORS.info;
            const icon = EVENT_ICONS[ev.type] || "📌";
            return (
              <div
                key={ev.id}
                className={`px-3 py-2 rounded-lg border text-sm font-mono ${colorClass}`}
              >
                <span className="text-slate-500 text-xs mr-2">
                  {new Date(ev.time).toLocaleTimeString()}
                </span>
                <span className="mr-1">{icon}</span>
                {ev.message}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
