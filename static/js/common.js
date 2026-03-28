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

/* ── Lock status indicator ── */
(function() {
  var banner = null;

  async function checkLock() {
    try {
      var data = await api.get('/api/status');
      if (data.locked) {
        if (!banner) {
          banner = document.createElement('div');
          banner.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:300;background:var(--error);color:#fff;padding:8px 24px;font-family:var(--font-display);font-size:.8rem;text-transform:uppercase;letter-spacing:.04em;display:flex;align-items:center;justify-content:space-between';
          var span = document.createElement('span');
          banner.appendChild(span);
          var btn = document.createElement('button');
          btn.textContent = 'FORCE UNLOCK';
          btn.style.cssText = 'background:#fff;color:var(--error);border:none;padding:4px 12px;font-family:var(--font-display);font-size:.75rem;font-weight:600;cursor:pointer;text-transform:uppercase';
          btn.onclick = async function() {
            if (!confirm('ロックを強制解除しますか？')) return;
            await api.post('/api/status/unlock', {});
            checkLock();
          };
          banner.appendChild(btn);
          document.body.appendChild(banner);
          document.body.style.paddingTop = '36px';
        }
        var mins = Math.floor(data.lock_age_seconds / 60);
        banner.querySelector('span').textContent = 'RUNNER LOCKED (' + mins + 'min ago)';
      } else {
        if (banner) {
          banner.remove();
          banner = null;
          document.body.style.paddingTop = '';
        }
      }
    } catch(e) {}
  }

  checkLock();
  setInterval(checkLock, 15000);
})();
