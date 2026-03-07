import React, { useState, useEffect, useCallback } from "react";

const SEVERITY_COLORS = {
  critical: "bg-red-600",
  high: "bg-orange-500",
  medium: "bg-yellow-500",
  low: "bg-blue-500",
};

const SEVERITY_DOT = {
  critical: "🔴",
  high: "🟠",
  medium: "🟡",
  low: "🔵",
};

function timeAgo(iso) {
  if (!iso) return "";
  const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export default function Reports() {
  const [reports, setReports] = useState([]);
  const [stats, setStats] = useState(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const [filter, setFilter] = useState({ user_id: "", error_type: "" });
  const LIMIT = 20;

  const fetchReports = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: LIMIT, offset: page * LIMIT });
      if (filter.user_id) params.set("user_id", filter.user_id);
      if (filter.error_type) params.set("error_type", filter.error_type);

      const [rRes, sRes] = await Promise.all([
        fetch(`/api/v1/reports?${params}`),
        fetch("/api/v1/reports/stats"),
      ]);
      const rData = await rRes.json();
      const sData = await sRes.json();
      setReports(rData.reports || []);
      setTotal(rData.total || 0);
      setStats(sData);
    } catch (err) {
      console.error("Failed to fetch reports", err);
    } finally {
      setLoading(false);
    }
  }, [page, filter]);

  useEffect(() => { fetchReports(); }, [fetchReports]);

  const handleDelete = async (id) => {
    if (!confirm("Delete this report?")) return;
    try {
      await fetch(`/api/v1/reports/${id}`, { method: "DELETE" });
      fetchReports();
    } catch (err) {
      console.error("Delete failed", err);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / LIMIT));

  return (
    <div className="flex-1 overflow-auto p-6 space-y-6">
      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">📄 Analysis Reports</h2>
        <button
          onClick={fetchReports}
          className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm"
        >
          ↻ Refresh
        </button>
      </div>

      {/* ── Stats cards ── */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            { label: "Total Reports", value: stats.total ?? 0, icon: "📊" },
            { label: "Avg Confidence", value: `${(stats.avg_confidence ?? 0).toFixed(0)}%`, icon: "🎯" },
            { label: "Unique Errors", value: stats.unique_error_types ?? 0, icon: "🐛" },
            { label: "Total Fixes", value: stats.total_proposals ?? 0, icon: "🔧" },
          ].map((s) => (
            <div key={s.label} className="bg-slate-800 border border-slate-700 rounded-xl px-4 py-3">
              <div className="text-2xl">{s.icon}</div>
              <div className="text-lg font-bold mt-1">{s.value}</div>
              <div className="text-xs text-slate-400">{s.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* ── Filters ── */}
      <div className="flex gap-3 items-center flex-wrap">
        <input
          type="text"
          placeholder="Filter by user_id..."
          value={filter.user_id}
          onChange={(e) => { setFilter((f) => ({ ...f, user_id: e.target.value })); setPage(0); }}
          className="bg-slate-800 border border-slate-600 rounded-lg px-3 py-1.5 text-sm w-44"
        />
        <input
          type="text"
          placeholder="Filter by error type..."
          value={filter.error_type}
          onChange={(e) => { setFilter((f) => ({ ...f, error_type: e.target.value })); setPage(0); }}
          className="bg-slate-800 border border-slate-600 rounded-lg px-3 py-1.5 text-sm w-44"
        />
        {(filter.user_id || filter.error_type) && (
          <button
            onClick={() => { setFilter({ user_id: "", error_type: "" }); setPage(0); }}
            className="text-xs text-slate-400 hover:text-white"
          >
            ✕ Clear
          </button>
        )}
      </div>

      {/* ── Table ── */}
      {loading ? (
        <div className="text-center py-16 text-slate-400">Loading reports…</div>
      ) : reports.length === 0 ? (
        <div className="text-center py-16 text-slate-500">
          No reports yet. Errors processed through the pipeline will appear here.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-700">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-800 text-slate-400 text-left">
                <th className="px-4 py-3 font-medium">Severity</th>
                <th className="px-4 py-3 font-medium">Error Type</th>
                <th className="px-4 py-3 font-medium hidden md:table-cell">Source</th>
                <th className="px-4 py-3 font-medium hidden lg:table-cell">Root Cause</th>
                <th className="px-4 py-3 font-medium text-center">Confidence</th>
                <th className="px-4 py-3 font-medium text-center">Fixes</th>
                <th className="px-4 py-3 font-medium">Time</th>
                <th className="px-4 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/60">
              {reports.map((r) => (
                <tr key={r.report_id} className="hover:bg-slate-800/50 transition-colors">
                  <td className="px-4 py-3">
                    <span title={r.severity}>
                      {SEVERITY_DOT[r.severity] ?? "⚪"}{" "}
                      <span className="capitalize text-xs">{r.severity}</span>
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono text-orange-300 text-xs">{r.error_type}</td>
                  <td className="px-4 py-3 text-xs text-slate-400 hidden md:table-cell truncate max-w-[200px]">
                    {r.source_file ? `${r.source_file}:${r.line_number}` : "—"}
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-300 hidden lg:table-cell truncate max-w-[260px]">
                    {r.root_cause || "—"}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span
                      className={`inline-block px-2 py-0.5 rounded-full text-xs font-bold ${
                        r.confidence >= 0.75
                          ? "bg-green-900/60 text-green-300"
                          : r.confidence >= 0.5
                          ? "bg-yellow-900/60 text-yellow-300"
                          : "bg-red-900/60 text-red-300"
                      }`}
                    >
                      {(r.confidence * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center tabular-nums">{r.proposals_count}</td>
                  <td className="px-4 py-3 text-xs text-slate-400 whitespace-nowrap">
                    {timeAgo(r.created_at)}
                  </td>
                  <td className="px-4 py-3 text-right space-x-2 whitespace-nowrap">
                    <a
                      href={r.view_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-block px-2.5 py-1 bg-blue-600 hover:bg-blue-500 rounded text-xs font-medium"
                    >
                      View
                    </a>
                    <button
                      onClick={() => handleDelete(r.report_id)}
                      className="px-2.5 py-1 bg-red-800/60 hover:bg-red-700 rounded text-xs"
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Pagination ── */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3">
          <button
            disabled={page === 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            className="px-3 py-1 bg-slate-700 rounded disabled:opacity-40 text-sm"
          >
            ← Prev
          </button>
          <span className="text-sm text-slate-400">
            Page {page + 1} / {totalPages}
          </span>
          <button
            disabled={page >= totalPages - 1}
            onClick={() => setPage((p) => p + 1)}
            className="px-3 py-1 bg-slate-700 rounded disabled:opacity-40 text-sm"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
