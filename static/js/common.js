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

/* ── Keyboard shortcuts ── */
var _shortcutHelp = null;
var _pageShortcuts = {};

function registerPageShortcuts(map) {
  _pageShortcuts = map || {};
}

document.addEventListener('keydown', function (e) {
  // input/textarea/select にフォーカス中は無効
  var tag = document.activeElement && document.activeElement.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
    if (e.key === 'Escape') { document.activeElement.blur(); }
    return;
  }

  // Esc: モーダルを閉じる / ヘルプを閉じる
  if (e.key === 'Escape') {
    if (_shortcutHelp) { _shortcutHelp.remove(); _shortcutHelp = null; return; }
    document.querySelectorAll('.modal-overlay.active').forEach(function (m) { m.classList.remove('active'); });
    // Alpine.js のモーダル状態もリセット
    var alpineEl = document.querySelector('[x-data]');
    if (alpineEl && alpineEl.__x) {
      var data = Alpine.$data(alpineEl);
      Object.keys(data).forEach(function (k) { if (k.indexOf('show') === 0 && k.indexOf('Modal') > 0 && data[k] === true) data[k] = false; });
    }
    return;
  }

  // ?: ショートカットヘルプ表示
  if (e.key === '?') {
    e.preventDefault();
    if (_shortcutHelp) { _shortcutHelp.remove(); _shortcutHelp = null; return; }
    var html = '<div style="position:fixed;inset:0;background:rgba(0,0,0,.7);display:flex;align-items:center;justify-content:center;z-index:200;font-family:var(--font-body)">' +
      '<div style="background:var(--surface);padding:28px;max-width:420px;width:90%">' +
      '<h2 style="font-family:var(--font-display);color:var(--primary-lit);text-transform:uppercase;letter-spacing:.04em;margin-bottom:16px;font-size:1rem">KEYBOARD SHORTCUTS</h2>' +
      '<table style="width:100%;font-size:.85rem;border-collapse:separate;border-spacing:0 4px">' +
      '<tr><td style="color:var(--secondary);font-family:var(--font-display);width:60px">1-6</td><td>Page navigation</td></tr>' +
      '<tr><td style="color:var(--secondary);font-family:var(--font-display)">N</td><td>New item</td></tr>' +
      '<tr><td style="color:var(--secondary);font-family:var(--font-display)">ESC</td><td>Close modal</td></tr>' +
      '<tr><td style="color:var(--secondary);font-family:var(--font-display)">[ ]</td><td>Pagination (Logs/Tasks)</td></tr>' +
      '<tr><td style="color:var(--secondary);font-family:var(--font-display)">D</td><td>Delete (in modal)</td></tr>' +
      '<tr><td style="color:var(--secondary);font-family:var(--font-display)">A</td><td>Archive (in modal)</td></tr>' +
      '<tr><td style="color:var(--secondary);font-family:var(--font-display)">?</td><td>This help</td></tr>' +
      '</table>' +
      '<div style="margin-top:16px;text-align:right"><span style="font-size:.75rem;color:var(--text-secondary)">Press ESC or ? to close</span></div>' +
      '</div></div>';
    var div = document.createElement('div');
    div.innerHTML = html;
    _shortcutHelp = div.firstChild;
    _shortcutHelp.addEventListener('click', function (ev) { if (ev.target === _shortcutHelp) { _shortcutHelp.remove(); _shortcutHelp = null; } });
    document.body.appendChild(_shortcutHelp);
    return;
  }

  // モーダルが開いている場合のショートカット (d=delete, a=archive)
  var modalOpen = document.querySelector('.modal-overlay.active') ||
    (function() { var el = document.querySelector('[x-data]'); if (!el) return false; var d = Alpine.$data(el); return Object.keys(d).some(function(k) { return k.indexOf('show') === 0 && k.indexOf('Modal') > 0 && d[k] === true; }); })();
  if (modalOpen) {
    if (e.key === 'd' || e.key === 'D') {
      if (_pageShortcuts.modalDelete) { _pageShortcuts.modalDelete(); return; }
    }
    if (e.key === 'a' || e.key === 'A') {
      if (_pageShortcuts.modalArchive) { _pageShortcuts.modalArchive(); return; }
    }
    return; // モーダル中は他のショートカットを無効化
  }

  // ページナビゲーション: 1-5
  var pages = ['/', '/tasks', '/logs', '/schedules', '/prompts', '/debug-logs'];
  var num = parseInt(e.key);
  if (num >= 1 && num <= 6) {
    var target = pages[num - 1];
    if (window.location.pathname !== target) window.location.href = target;
    return;
  }

  // N: 新規作成
  if (e.key === 'n' || e.key === 'N') {
    if (_pageShortcuts.new) { _pageShortcuts.new(); return; }
  }

  // [ ]: ページネーション
  if (e.key === '[') {
    if (_pageShortcuts.prev) { _pageShortcuts.prev(); return; }
  }
  if (e.key === ']') {
    if (_pageShortcuts.next) { _pageShortcuts.next(); return; }
  }
});

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

/* ── Pause toggle ── */
async function togglePause() {
  var data = await api.get('/api/status');
  if (data.paused) {
    await api.post('/api/status/resume', {});
  } else {
    await api.post('/api/status/pause', {});
  }
  updatePauseBtn();
  location.reload();
}

async function updatePauseBtn() {
  try {
    var data = await api.get('/api/status');
    var btn = document.getElementById('pauseBtn');
    if (!btn) return;
    if (data.paused) {
      btn.textContent = 'RESUME';
      btn.style.background = 'var(--primary)';
      btn.style.color = '#fff';
      btn.style.borderColor = 'var(--primary)';
    } else {
      btn.textContent = 'PAUSE';
      btn.style.background = 'transparent';
      btn.style.color = 'var(--text-secondary)';
      btn.style.borderColor = '';
    }
  } catch(e) {}
}
document.addEventListener('DOMContentLoaded', updatePauseBtn);

/* ── Status indicator (lock + pause) ── */
(function() {
  var statusBar = null;

  function createBar() {
    statusBar = document.createElement('div');
    statusBar.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:300;padding:8px 24px;font-family:var(--font-display);font-size:.8rem;text-transform:uppercase;letter-spacing:.04em;display:flex;align-items:center;gap:16px';
    document.body.appendChild(statusBar);
    document.body.style.paddingTop = '36px';
  }

  function removeBar() {
    if (statusBar) { statusBar.remove(); statusBar = null; document.body.style.paddingTop = ''; }
  }

  async function checkStatus() {
    try {
      var data = await api.get('/api/status');
      if (!data.locked && !data.paused) { removeBar(); return; }

      if (!statusBar) createBar();
      var html = '';

      if (data.paused) {
        statusBar.style.background = 'var(--primary)';
        html += '<span>RUNNER PAUSED</span>';
        html += '<button onclick="api.post(\'/api/status/resume\',{}).then(function(){location.reload()})" style="background:#fff;color:var(--primary);border:none;padding:4px 12px;font-family:var(--font-display);font-size:.75rem;font-weight:600;cursor:pointer;text-transform:uppercase">RESUME</button>';
      }

      if (data.locked) {
        if (data.paused) html += '<span style="margin-left:16px;opacity:.8">|</span>';
        else statusBar.style.background = 'var(--error)';
        var mins = Math.floor(data.lock_age_seconds / 60);
        html += '<span>LOCKED (' + mins + 'min)</span>';
        html += '<button onclick="if(confirm(\'ロックを強制解除しますか？\'))api.post(\'/api/status/unlock\',{}).then(function(){location.reload()})" style="background:#fff;color:var(--error);border:none;padding:4px 12px;font-family:var(--font-display);font-size:.75rem;font-weight:600;cursor:pointer;text-transform:uppercase">UNLOCK</button>';
      }

      if (!data.paused && !data.locked) { removeBar(); return; }
      statusBar.innerHTML = html;
    } catch(e) {}
  }

  checkStatus();
  setInterval(checkStatus, 15000);
})();
