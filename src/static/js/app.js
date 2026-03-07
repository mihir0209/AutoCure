/* ═══════════════════════════════════════════════════════
   AutoCure Dashboard – app.js
   Global WebSocket manager, toast notifications, helpers
   ═══════════════════════════════════════════════════════ */

// ─── WebSocket Manager ───────────────────────────────

class DashboardWS {
  constructor() {
    this.ws = null;
    this.handlers = [];
    this.baseDelay = 2000;
    this.delay = this.baseDelay;
    this.maxDelay = 30000;
  }

  connect() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${proto}//${location.host}/ws/dashboard`;
    try { this.ws = new WebSocket(url); } catch(e) { this._reconnect(); return; }

    this.ws.onopen = () => {
      this.delay = this.baseDelay;
      this._setStatus(true);
    };
    this.ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        this.handlers.forEach(fn => { try { fn(data); } catch(e) { console.warn('[WS] handler error', e); } });
      } catch(e) { /* ignore parse errors */ }
    };
    this.ws.onclose = () => { this._setStatus(false); this._reconnect(); };
    this.ws.onerror = () => { this._setStatus(false); };
  }

  onMessage(fn) { this.handlers.push(fn); }

  _reconnect() {
    setTimeout(() => { this.delay = Math.min(this.delay * 1.5, this.maxDelay); this.connect(); }, this.delay);
  }

  _setStatus(ok) {
    const el = document.getElementById('wsStatus');
    if (!el) return;
    el.className = 'ws-status ' + (ok ? 'connected' : 'disconnected');
    const span = el.querySelector('span');
    if (span) span.textContent = ok ? 'Live' : 'Reconnecting...';
  }
}

// ─── Toast Notifications ─────────────────────────────

const TOAST_ICONS = {
  info:    'ph-info',
  success: 'ph-check-circle',
  warning: 'ph-warning',
  error:   'ph-x-circle',
};

function showToast(message, type, duration) {
  type = type || 'info';
  duration = duration || 4000;
  const c = document.getElementById('toastContainer');
  if (!c) return;
  const t = document.createElement('div');
  t.className = 'toast toast-' + type;
  t.innerHTML = '<i class="ph ' + (TOAST_ICONS[type]||TOAST_ICONS.info) + '"></i><span>' + escapeHtml(message) + '</span>';
  c.appendChild(t);
  requestAnimationFrame(function() { t.classList.add('show'); });
  setTimeout(function() { t.classList.remove('show'); setTimeout(function(){ t.remove(); }, 300); }, duration);
}

// ─── Utility Functions ───────────────────────────────

function escapeHtml(s) {
  var d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}

function timeAgo(iso) {
  if (!iso) return '';
  var d = new Date(iso.endsWith('Z') ? iso : iso + 'Z');
  var s = (Date.now() - d.getTime()) / 1000;
  if (s < 60) return 'just now';
  if (s < 3600) return Math.floor(s/60) + 'm ago';
  if (s < 86400) return Math.floor(s/3600) + 'h ago';
  return Math.floor(s/86400) + 'd ago';
}

function formatTime(iso) {
  if (!iso) return '';
  try {
    var d = new Date(iso.endsWith('Z') ? iso : iso + 'Z');
    return d.toLocaleTimeString();
  } catch(e) { return iso; }
}

function formatDate(iso) {
  if (!iso) return '';
  try {
    var d = new Date(iso.endsWith('Z') ? iso : iso + 'Z');
    return d.toLocaleDateString() + ' ' + d.toLocaleTimeString();
  } catch(e) { return iso; }
}

function copyToClipboard(text, btn) {
  navigator.clipboard.writeText(text).then(function() {
    if (btn) {
      var orig = btn.innerHTML;
      btn.innerHTML = '<i class="ph ph-check"></i> Copied';
      setTimeout(function(){ btn.innerHTML = orig; }, 2000);
    }
    showToast('Copied to clipboard', 'success');
  }).catch(function() {
    showToast('Copy failed', 'error');
  });
}

function api(url, opts) {
  opts = opts || {};
  var headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
  return fetch(url, Object.assign({}, opts, { headers: headers }))
    .then(function(r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
}

// ─── Global Instance ─────────────────────────────────

var dashboardWS = new DashboardWS();

document.addEventListener('DOMContentLoaded', function() {
  // Auto-connect on authenticated pages (not login)
  if (!document.querySelector('.login-body')) {
    dashboardWS.connect();
  }
});
