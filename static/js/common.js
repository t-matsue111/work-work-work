/**
 * common.js - 共有ユーティリティ（Kinetic Console）
 */

/* ── API Wrapper ── */
const api = {
  async get(url) {
    const res = await fetch(url);
    return res.json();
  },
  async post(url, body) {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return res;
  },
  async patch(url, body) {
    const res = await fetch(url, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return res;
  },
  async put(url, body) {
    const res = await fetch(url, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return res;
  },
  async del(url) {
    const res = await fetch(url, { method: 'DELETE' });
    return res;
  },
};

/* ── Utilities ── */
function esc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function relativeTime(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr.replace(' ', 'T'));
  const now = new Date();
  const diff = Math.floor((now - d) / 1000);
  if (diff < 60) return diff + '\u79d2\u524d';
  if (diff < 3600) return Math.floor(diff / 60) + '\u5206\u524d';
  if (diff < 86400) return Math.floor(diff / 3600) + '\u6642\u9593\u524d';
  return Math.floor(diff / 86400) + '\u65e5\u524d';
}

function fmtLocalTime(dateStr) {
  if (!dateStr) return '-';
  var d = new Date(dateStr.replace(' ', 'T'));
  if (isNaN(d)) return dateStr;
  var pad = function(n) { return n < 10 ? '0' + n : n; };
  return d.getFullYear() + '-' + pad(d.getMonth()+1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
}

function fmtCost(v) {
  return v != null ? '$' + v.toFixed(4) : '-';
}

function fmtDuration(v) {
  return v != null ? v + 's' : '-';
}

function badgeClass(type) {
  return 'badge badge-' + type;
}

function statusClass(s) {
  return 'status-badge status-' + (s || 'unknown');
}

/* ── Modal helpers ── */
function openModal(id) {
  document.getElementById(id).classList.add('active');
}

function closeModal(id) {
  document.getElementById(id).classList.remove('active');
}

/* Close modal on overlay click */
function initModalOverlays() {
  document.querySelectorAll('.modal-overlay').forEach(function (m) {
    m.addEventListener('click', function (e) {
      if (e.target === m) m.classList.remove('active');
    });
  });
}

/* ── Form helper for schedules ── */
function setField(id, val) {
  var el = document.getElementById(id);
  if (!el) return;
  if (el.tagName === 'SELECT') {
    for (var i = 0; i < el.options.length; i++) {
      if (el.options[i].value === String(val || '')) {
        el.selectedIndex = i;
        return;
      }
    }
    el.selectedIndex = 0;
  } else {
    el.value = val || '';
  }
}
