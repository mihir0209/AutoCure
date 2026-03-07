import React, { useState, useEffect, useCallback, useRef } from "react";

const BACKEND = ""; // proxied via vite

/**
 * Dashboard – real-time overview of the Self-Healing System.
 *
 * Shows:
 *  - System status (health, AI provider, connections)
 *  - Live log stream via WebSocket
 *  - Recent errors + analysis results
 *  - Registered users & repos
 */
export default function Dashboard() {
  const [status, setStatus] = useState(null);
  const [summary, setSummary] = useState(null);
  const [connections, setConnections] = useState([]);
  const [logs, setLogs] = useState([]);
  const [errors, setErrors] = useState([]);
  const [loading, setLoading] = useState(true);

  // WebSocket for live log streaming
  const ws = useRef(null);
  const logEndRef = useRef(null);

  // ── Fetch system data ──────────────────────────────────────────
  const fetchData = useCallback(async () => {
    try {
      const [statusRes, summaryRes, connRes] = await Promise.allSettled([
        fetch(`${BACKEND}/api/v1/status`),
        fetch(`${BACKEND}/api/v1/dashboard/summary`),
        fetch(`${BACKEND}/api/v1/connections`),
      ]);
      if (statusRes.status === "fulfilled" && statusRes.value.ok)
        setStatus(await statusRes.value.json());
      if (summaryRes.status === "fulfilled" && summaryRes.value.ok)
        setSummary(await summaryRes.value.json());
      if (connRes.status === "fulfilled" && connRes.value.ok) {
        const data = await connRes.value.json();
        setConnections(data.connections || []);
      }
    } catch {
      /* backend might not be running */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 8000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Auto-scroll logs
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  // ── Cards ──────────────────────────────────────────────────────
  const StatCard = ({ label, value, icon, color = "blue" }) => (
    <div className={`bg-slate-800 rounded-xl p-5 border border-slate-700 hover:border-${color}-500/40 transition-colors`}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs uppercase tracking-wider text-slate-400">{label}</p>
          <p className={`text-3xl font-bold mt-1 text-${color}-400`}>
            {value ?? "—"}
          </p>
        </div>
        <span className="text-2xl opacity-60">{icon}</span>
      </div>
    </div>
  );

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="animate-spin w-8 h-8 border-2 border-blue-400 border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-auto p-6 space-y-6">
      {/* Status Banner */}
      <div className="flex items-center gap-3">
        <div
          className={`w-3 h-3 rounded-full ${
            status?.status === "running" ? "bg-green-400 animate-pulse" : "bg-red-400"
          }`}
        />
        <h2 className="text-lg font-semibold">
          System {status?.status === "running" ? "Online" : "Offline"}
        </h2>
        <span className="text-xs text-slate-500 ml-auto">
          AI: {status?.ai_provider || "—"} &middot; v2.0.0
        </span>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Active Connections" value={summary?.active_connections} icon="🔌" color="green" />
        <StatCard label="Registered Users" value={summary?.registered_users} icon="👤" color="purple" />
        <StatCard label="Total Logs" value={summary?.total_logs} icon="📜" color="blue" />
        <StatCard label="Errors Detected" value={summary?.total_errors} icon="🚨" color="red" />
      </div>

      {/* Two-column layout */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* Active connections */}
        <div className="bg-slate-800 rounded-xl border border-slate-700 p-5">
          <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-green-400" /> Live Connections
          </h3>
          {connections.length === 0 ? (
            <p className="text-slate-500 text-sm">No active connections</p>
          ) : (
            <ul className="space-y-2 max-h-60 overflow-auto">
              {connections.map((c, i) => (
                <li
                  key={i}
                  className="flex items-center justify-between bg-slate-900/50 px-3 py-2 rounded-lg text-sm"
                >
                  <span className="font-mono text-blue-300">{c.user_id}</span>
                  <span className="text-xs text-slate-400">
                    logs: {c.logs_received} &middot; errors: {c.errors_detected}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Repos */}
        <div className="bg-slate-800 rounded-xl border border-slate-700 p-5">
          <h3 className="text-sm font-semibold text-slate-300 mb-3">
            📦 Repositories Synced
          </h3>
          <p className="text-4xl font-bold text-emerald-400">
            {summary?.repositories_synced ?? 0}
          </p>
          <p className="text-xs text-slate-500 mt-2">
            Total users registered: {summary?.registered_users ?? 0}
          </p>
        </div>
      </div>

      {/* Pipeline overview */}
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-5">
        <h3 className="text-sm font-semibold text-slate-300 mb-4">
          🔄 Analysis Pipeline
        </h3>
        <div className="flex items-center gap-3 overflow-x-auto pb-2">
          {[
            { step: "Log Ingestion", icon: "📥", desc: "WebSocket stream" },
            { step: "Error Detection", icon: "🔍", desc: "Pattern matching" },
            { step: "AST Tracing", icon: "🌳", desc: "tree-sitter" },
            { step: "AI Analysis", icon: "🤖", desc: "Groq / Cerebras" },
            { step: "Confidence", icon: "📊", desc: "Multi-iteration" },
            { step: "Fix Proposal", icon: "💡", desc: "Code suggestions" },
            { step: "Email Report", icon: "📧", desc: "Rich HTML" },
          ].map((s, i, arr) => (
            <React.Fragment key={s.step}>
              <div className="flex flex-col items-center min-w-[90px] text-center">
                <span className="text-2xl">{s.icon}</span>
                <span className="text-xs font-medium text-slate-300 mt-1">{s.step}</span>
                <span className="text-[10px] text-slate-500">{s.desc}</span>
              </div>
              {i < arr.length - 1 && (
                <span className="text-slate-600 text-lg">→</span>
              )}
            </React.Fragment>
          ))}
        </div>
      </div>

      {/* Quick actions */}
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-5">
        <h3 className="text-sm font-semibold text-slate-300 mb-3">⚡ Quick Actions</h3>
        <div className="flex flex-wrap gap-3">
          <ActionButton
            label="View AST Visualizer"
            icon="🌳"
            onClick={() => {
              // Navigate to AST tab (controlled by parent)
              document.dispatchEvent(new CustomEvent("navigate", { detail: "ast" }));
            }}
          />
          <ActionButton
            label="Refresh Status"
            icon="🔄"
            onClick={fetchData}
          />
        </div>
      </div>
    </div>
  );
}

function ActionButton({ label, icon, onClick }) {
  return (
    <button
      onClick={onClick}
      className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
    >
      <span>{icon}</span>
      {label}
    </button>
  );
}
