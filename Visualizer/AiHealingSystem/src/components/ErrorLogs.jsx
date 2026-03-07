import React, { useState, useEffect, useRef, useCallback } from "react";

const BACKEND = "";

/**
 * ErrorLogs – real-time error log viewer.
 *
 * - Fetches recent logs from the REST API
 * - Optionally opens a WebSocket for live streaming
 * - Filter by level, search text
 * - Click an error to see full details
 */
export default function ErrorLogs() {
  const [userId, setUserId] = useState("");
  const [inputUser, setInputUser] = useState("");
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("ALL");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const logEndRef = useRef(null);
  const wsRef = useRef(null);

  // ── Fetch logs via REST ────────────────────────────────────────
  const fetchLogs = useCallback(async (uid) => {
    if (!uid) return;
    setLoading(true);
    try {
      const res = await fetch(`${BACKEND}/api/v1/logs/${uid}?limit=500`);
      if (res.ok) {
        const data = await res.json();
        setLogs(data.logs || []);
      }
    } catch {
      /* backend not running */
    } finally {
      setLoading(false);
    }
  }, []);

  // ── Connect / Disconnect ───────────────────────────────────────
  const connectWs = useCallback((uid) => {
    if (!uid) return;
    // Close existing
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${protocol}//${window.location.host}/ws/logs/${uid}`;
    const socket = new WebSocket(url);
    socket.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);
        if (msg.type === "log" || msg.type === "error_received" || msg.type === "analysis_complete") {
          setLogs((prev) => [...prev.slice(-999), msg.payload || msg]);
        }
      } catch { /* ignore non-json */ }
    };
    socket.onclose = () => {
      wsRef.current = null;
    };
    wsRef.current = socket;
  }, []);

  useEffect(() => () => wsRef.current?.close(), []);

  // Auto-scroll
  useEffect(() => {
    if (autoScroll) logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs, autoScroll]);

  // ── Handlers ───────────────────────────────────────────────────
  const handleConnect = () => {
    const uid = inputUser.trim();
    if (!uid) return;
    setUserId(uid);
    fetchLogs(uid);
  };

  // ── Filter ─────────────────────────────────────────────────────
  const filtered = logs.filter((log) => {
    const level = (log.level || "INFO").toUpperCase();
    if (filter !== "ALL" && level !== filter) return false;
    if (search) {
      const s = search.toLowerCase();
      return (
        (log.message || "").toLowerCase().includes(s) ||
        (log.source_file || "").toLowerCase().includes(s)
      );
    }
    return true;
  });

  // ── Level badge colors ─────────────────────────────────────────
  const levelColor = (level) => {
    switch ((level || "").toUpperCase()) {
      case "ERROR":
      case "FATAL":
      case "CRITICAL":
        return "bg-red-600 text-white";
      case "WARNING":
        return "bg-yellow-600 text-white";
      case "DEBUG":
        return "bg-slate-600 text-slate-300";
      default:
        return "bg-blue-600/60 text-blue-200";
    }
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Toolbar */}
      <div className="bg-slate-800 border-b border-slate-700 px-4 py-3 flex items-center gap-3 shrink-0 flex-wrap">
        <span className="text-sm font-semibold text-slate-300">🪵 Logs</span>

        {/* User picker */}
        <input
          type="text"
          className="bg-slate-900 border border-slate-600 rounded px-3 py-1.5 text-sm w-40"
          placeholder="User ID"
          value={inputUser}
          onChange={(e) => setInputUser(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleConnect()}
        />
        <button
          onClick={handleConnect}
          className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded text-sm font-medium"
        >
          Load Logs
        </button>

        <div className="flex-1" />

        {/* Level filter */}
        {["ALL", "ERROR", "WARNING", "INFO", "DEBUG"].map((lvl) => (
          <button
            key={lvl}
            onClick={() => setFilter(lvl)}
            className={`px-2 py-1 rounded text-xs font-medium ${
              filter === lvl ? "bg-blue-600" : "bg-slate-700 hover:bg-slate-600"
            }`}
          >
            {lvl}
          </button>
        ))}

        {/* Search */}
        <input
          type="text"
          className="bg-slate-900 border border-slate-600 rounded px-3 py-1.5 text-sm w-48"
          placeholder="Search..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />

        {/* Auto-scroll */}
        <button
          onClick={() => setAutoScroll(!autoScroll)}
          className={`px-2 py-1 rounded text-xs ${autoScroll ? "bg-green-700" : "bg-slate-700"}`}
          title="Auto-scroll"
        >
          {autoScroll ? "⬇️ Auto" : "⏸ Paused"}
        </button>
      </div>

      {/* Log list */}
      <div className="flex-1 overflow-auto font-mono text-xs">
        {loading ? (
          <div className="flex items-center justify-center h-full text-slate-500">
            Loading...
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-slate-500 gap-2">
            <span className="text-4xl">📭</span>
            <p>{userId ? "No logs matching filter" : "Enter a User ID and click Load Logs"}</p>
          </div>
        ) : (
          <table className="w-full">
            <thead className="sticky top-0 bg-slate-800 text-slate-400 text-[11px] uppercase">
              <tr>
                <th className="px-3 py-2 text-left w-[180px]">Time</th>
                <th className="px-2 py-2 text-left w-[70px]">Level</th>
                <th className="px-2 py-2 text-left w-[180px]">Source</th>
                <th className="px-3 py-2 text-left">Message</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((log, i) => {
                const level = (log.level || "INFO").toUpperCase();
                const isError = ["ERROR", "FATAL", "CRITICAL"].includes(level);
                return (
                  <tr
                    key={i}
                    onClick={() => setSelected(log)}
                    className={`border-b border-slate-800 cursor-pointer transition-colors ${
                      isError
                        ? "bg-red-950/30 hover:bg-red-900/40"
                        : "hover:bg-slate-800/60"
                    } ${selected === log ? "ring-1 ring-blue-500" : ""}`}
                  >
                    <td className="px-3 py-1.5 text-slate-500 whitespace-nowrap">
                      {log.timestamp
                        ? new Date(log.timestamp).toLocaleTimeString()
                        : "—"}
                    </td>
                    <td className="px-2 py-1.5">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${levelColor(level)}`}>
                        {level}
                      </span>
                    </td>
                    <td className="px-2 py-1.5 text-slate-400 truncate max-w-[180px]">
                      {log.source_file || log.source || "—"}
                      {log.line_number ? `:${log.line_number}` : ""}
                    </td>
                    <td className="px-3 py-1.5 text-slate-200 truncate max-w-[600px]">
                      {log.message || "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        <div ref={logEndRef} />
      </div>

      {/* Detail panel */}
      {selected && (
        <div className="shrink-0 bg-slate-800 border-t border-slate-700 p-4 max-h-64 overflow-auto">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-slate-300">Log Detail</h3>
            <button
              onClick={() => setSelected(null)}
              className="text-slate-500 hover:text-white text-sm"
            >
              ✕
            </button>
          </div>
          <pre className="text-xs text-slate-300 whitespace-pre-wrap">
            {JSON.stringify(selected, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
