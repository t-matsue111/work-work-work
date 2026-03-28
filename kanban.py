#!/usr/bin/env python3
"""Claude Task Runner - Kanban Board Server

Python標準ライブラリのみで動作する軽量Kanbanボードサーバー。
SQLite（tasks.db）を直接読み書きし、ブラウザでタスク管理が可能。

Usage:
    python3 kanban.py [--port PORT] [--db PATH]
"""

import argparse
import json
import os
import re
import signal
import sqlite3
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# デフォルト設定
DEFAULT_PORT = 8766
DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db", "tasks.db")
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sources", "sqlite", "schema.sql")
PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")

# ── HTML テンプレート ──────────────────────────────────────────────
KANBAN_HTML = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Claude Task Runner - Kanban</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#1a1a2e;color:#e0e0e0;min-height:100vh}
header{background:#0f3460;padding:16px 24px;display:flex;align-items:center;justify-content:space-between;box-shadow:0 2px 8px rgba(0,0,0,.3)}
header h1{font-size:1.4rem;font-weight:700;color:#e94560}
header .stats{font-size:.85rem;color:#a0a0b8;margin-left:auto;margin-right:24px}
header .stats span{margin:0 8px}
.btn-log{background:transparent;color:#3a86ff;border:1px solid #3a86ff;padding:8px 16px;border-radius:6px;font-size:.85rem;cursor:pointer;font-weight:600;text-decoration:none;transition:background .2s,color .2s;margin-right:8px}
.btn-log:hover{background:#3a86ff;color:#fff}
.btn-add{background:#e94560;color:#fff;border:none;padding:8px 20px;border-radius:6px;font-size:.9rem;cursor:pointer;font-weight:600;transition:background .2s}
.btn-add:hover{background:#c73650}
.board{display:flex;gap:16px;padding:20px 16px;overflow-x:auto;min-height:calc(100vh - 68px);align-items:flex-start}
.column{min-width:280px;max-width:320px;flex:1 0 280px;background:#16213e;border-radius:10px;display:flex;flex-direction:column;max-height:calc(100vh - 100px)}
.column-header{padding:12px 16px;border-radius:10px 10px 0 0;font-weight:700;font-size:.95rem;display:flex;justify-content:space-between;align-items:center}
.column-header .count{background:rgba(0,0,0,.25);padding:2px 10px;border-radius:12px;font-size:.8rem}
.col-pending .column-header{background:#f0c929;color:#1a1a2e}
.col-in_progress .column-header{background:#3a86ff;color:#fff}
.col-completed .column-header{background:#2ecc71;color:#1a1a2e}
.col-error .column-header{background:#e74c3c;color:#fff}
.col-review .column-header{background:#e67e22;color:#fff}
.column-body{padding:8px;overflow-y:auto;flex:1;min-height:80px}
.column-body.drag-over{background:rgba(233,69,96,.08);border-radius:0 0 10px 10px}
.card{background:#1a1a3e;border:1px solid #2a2a4e;border-radius:8px;padding:12px;margin-bottom:8px;cursor:grab;transition:transform .15s,box-shadow .15s}
.card:hover{transform:translateY(-2px);box-shadow:0 4px 12px rgba(0,0,0,.3)}
.card.dragging{opacity:.5;transform:rotate(2deg)}
.card-title{font-weight:600;font-size:.9rem;margin-bottom:6px;line-height:1.3}
.card-meta{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.badge{padding:2px 8px;border-radius:4px;font-size:.7rem;font-weight:600}
.badge-research{background:#3a86ff33;color:#3a86ff}
.badge-planning{background:#ff69b433;color:#ff69b4}
.badge-code_review{background:#f0c92933;color:#f0c929}
.badge-sentry_analysis{background:#a855f733;color:#a855f7}
.priority-dot{width:10px;height:10px;border-radius:50%;display:inline-block}
.priority-high{background:#e74c3c}
.priority-medium{background:#f0c929}
.priority-low{background:#888}
.card-time{font-size:.7rem;color:#888;margin-top:4px}
/* モーダル共通 */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;align-items:center;justify-content:center;z-index:100}
.modal-overlay.active{display:flex}
.modal{background:#16213e;border-radius:12px;padding:24px;width:90%;max-width:560px;max-height:85vh;overflow-y:auto;box-shadow:0 8px 32px rgba(0,0,0,.5)}
.modal h2{margin-bottom:16px;font-size:1.2rem;color:#e94560}
.modal label{display:block;font-size:.85rem;color:#a0a0b8;margin-bottom:4px;margin-top:12px}
.modal input,.modal select,.modal textarea{width:100%;padding:8px 12px;border-radius:6px;border:1px solid #2a2a4e;background:#1a1a2e;color:#e0e0e0;font-size:.9rem}
.modal textarea{min-height:100px;resize:vertical}
.modal-actions{display:flex;gap:12px;margin-top:20px;justify-content:flex-end}
.modal-actions button{padding:8px 20px;border-radius:6px;border:none;font-size:.9rem;cursor:pointer;font-weight:600}
.btn-primary{background:#e94560;color:#fff}
.btn-primary:hover{background:#c73650}
.btn-cancel{background:#2a2a4e;color:#e0e0e0}
.btn-cancel:hover{background:#3a3a5e}
.btn-delete{background:#e74c3c;color:#fff}
.btn-delete:hover{background:#c0392b}
.detail-field{margin-bottom:12px}
.detail-field .label{font-size:.8rem;color:#888;margin-bottom:2px}
.detail-field .value{background:#1a1a2e;padding:10px;border-radius:6px;font-size:.85rem;white-space:pre-wrap;word-break:break-word;max-height:200px;overflow-y:auto}
@media(max-width:768px){.board{flex-direction:column;align-items:stretch}.column{min-width:auto;max-width:none;max-height:none}}
</style>
</head>
<body>
<header>
  <h1>Claude Task Runner</h1>
  <div class="stats" id="stats"></div>
  <a href="/logs" class="btn-log">Logs</a>
  <a href="/schedules" class="btn-log">Schedules</a>
  <a href="/prompts" class="btn-log">Prompts</a>
  <button class="btn-add" onclick="openAddModal()">+ タスク追加</button>
</header>
<div class="board" id="board">
  <div class="column col-pending" data-status="pending">
    <div class="column-header">Todo <span class="count" id="cnt-pending">0</span></div>
    <div class="column-body" id="col-pending"></div>
  </div>
  <div class="column col-in_progress" data-status="in_progress">
    <div class="column-header">In Progress <span class="count" id="cnt-in_progress">0</span></div>
    <div class="column-body" id="col-in_progress"></div>
  </div>
  <div class="column col-completed" data-status="completed">
    <div class="column-header">Done <span class="count" id="cnt-completed">0</span></div>
    <div class="column-body" id="col-completed"></div>
  </div>
  <div class="column col-error" data-status="error">
    <div class="column-header">Error <span class="count" id="cnt-error">0</span></div>
    <div class="column-body" id="col-error"></div>
  </div>
  <div class="column col-review" data-status="needs_review">
    <div class="column-header">要確認 <span class="count" id="cnt-review">0</span></div>
    <div class="column-body" id="col-review"></div>
  </div>
</div>

<!-- 追加モーダル -->
<div class="modal-overlay" id="addModal">
  <div class="modal">
    <h2>タスク追加</h2>
    <label>タスク名</label>
    <input type="text" id="addName" placeholder="タスク名を入力">
    <label>ラベル</label>
    <input type="text" id="addType" list="kanbanTypeList" placeholder="例: research, email_check">
    <datalist id="kanbanTypeList">
      <option value="research">技術調査・コードベース分析</option>
      <option value="planning">要件→実装計画作成</option>
      <option value="code_review">PRレビューコメント投稿</option>
      <option value="sentry_analysis">Sentryイシュー原因調査</option>
      <option value="email_check">メール確認・要約</option>
    </datalist>
    <label>優先度</label>
    <select id="addPriority">
      <option value="medium">medium</option>
      <option value="high">high</option>
      <option value="low">low</option>
    </select>
    <label>入力情報</label>
    <textarea id="addInput" placeholder="タスクの詳細情報"></textarea>
    <details style="margin-top:16px;border:1px solid #2a2a4e;border-radius:6px;padding:0 12px">
      <summary style="cursor:pointer;padding:10px 0;color:#a0a0b8;font-size:.85rem;font-weight:600">詳細設定</summary>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <div><label style="font-size:.8rem;color:#888">モデル</label>
        <select id="addTaskModel" style="width:100%;padding:6px 10px;border-radius:6px;border:1px solid #2a2a4e;background:#1a1a2e;color:#e0e0e0;font-size:.85rem">
          <option value="">デフォルト (sonnet)</option>
          <option value="opus">opus</option>
          <option value="haiku">haiku</option>
        </select></div>
        <div><label style="font-size:.8rem;color:#888">MCP接続</label>
        <input type="text" id="addTaskMcp" list="kanbanMcpList" placeholder="なし" style="font-size:.85rem">
        <datalist id="kanbanMcpList">
          <option value="mcp-config-email.json">Google Workspace</option>
          <option value="mcp-config-sentry.json">Sentry</option>
          <option value="sources/notion/mcp-config.json">Notion</option>
        </datalist></div>
        <div><label style="font-size:.8rem;color:#888">タイムアウト(秒)</label>
        <input type="number" id="addTaskTimeout" placeholder="300" style="font-size:.85rem"></div>
        <div><label style="font-size:.8rem;color:#888">最大ターン</label>
        <input type="number" id="addTaskMaxTurns" placeholder="30" style="font-size:.85rem"></div>
      </div>
      <label style="font-size:.8rem;color:#888">作業ディレクトリ</label>
      <input type="text" id="addTaskWorkDir" placeholder="省略時はこのプロジェクト" style="font-size:.85rem;margin-bottom:12px">
      <label style="font-size:.8rem;color:#888">許可ツール</label>
      <input type="text" id="addTaskTools" placeholder="省略時はソースのデフォルト" style="font-size:.85rem;margin-bottom:12px">
    </details>
    <div class="modal-actions">
      <button class="btn-cancel" onclick="closeModal('addModal')">キャンセル</button>
      <button class="btn-primary" onclick="submitAdd()">追加</button>
    </div>
  </div>
</div>

<!-- 詳細モーダル -->
<div class="modal-overlay" id="detailModal">
  <div class="modal">
    <h2 id="detailTitle"></h2>
    <div class="card-meta" id="detailMeta" style="margin-bottom:16px"></div>
    <div class="detail-field"><div class="label">Input</div><div class="value" id="detailInput"></div></div>
    <div class="detail-field"><div class="label">Result</div><div class="value" id="detailResult"></div></div>
    <div class="detail-field"><div class="label">作成日時</div><div class="value" id="detailCreated"></div></div>
    <div class="detail-field"><div class="label">更新日時</div><div class="value" id="detailUpdated"></div></div>
    <div class="modal-actions">
      <button class="btn-delete" id="detailDeleteBtn">削除</button>
      <button class="btn-cancel" onclick="closeModal('detailModal')">閉じる</button>
    </div>
  </div>
</div>

<script>
let allTasks = [];
const STATUS_MAP = {
  pending: 'col-pending',
  in_progress: 'col-in_progress',
  completed: 'col-completed',
  error: 'col-error',
  needs_clarification: 'col-review',
  needs_review: 'col-review'
};

function relativeTime(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr.replace(' ', 'T'));
  const now = new Date();
  const diff = Math.floor((now - d) / 1000);
  if (diff < 60) return `${diff}秒前`;
  if (diff < 3600) return `${Math.floor(diff/60)}分前`;
  if (diff < 86400) return `${Math.floor(diff/3600)}時間前`;
  return `${Math.floor(diff/86400)}日前`;
}

function badgeClass(type) { return 'badge badge-' + type; }

function createCard(task) {
  const div = document.createElement('div');
  div.className = 'card';
  div.draggable = true;
  div.dataset.id = task.id;
  div.innerHTML = `
    <div class="card-title">${esc(task.task_name)}</div>
    <div class="card-meta">
      <span class="${badgeClass(task.task_type)}">${task.task_type}</span>
      <span class="priority-dot priority-${task.priority}" title="${task.priority}"></span>
    </div>
    <div class="card-time">${relativeTime(task.created_at)}</div>`;
  div.addEventListener('dragstart', e => { e.dataTransfer.setData('text/plain', task.id); div.classList.add('dragging'); });
  div.addEventListener('dragend', () => div.classList.remove('dragging'));
  div.addEventListener('click', () => openDetail(task));
  return div;
}

function esc(s) { if (!s) return ''; const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

async function loadTasks() {
  const res = await fetch('/api/tasks');
  allTasks = await res.json();
  render();
  loadStats();
}

function render() {
  Object.values(STATUS_MAP).forEach(id => { document.getElementById(id).innerHTML = ''; });
  const counts = { pending:0, in_progress:0, completed:0, error:0, review:0 };
  allTasks.forEach(t => {
    const colId = STATUS_MAP[t.status];
    if (!colId) return;
    document.getElementById(colId).appendChild(createCard(t));
    if (t.status === 'needs_clarification' || t.status === 'needs_review') counts.review++;
    else if (counts[t.status] !== undefined) counts[t.status]++;
  });
  document.getElementById('cnt-pending').textContent = counts.pending;
  document.getElementById('cnt-in_progress').textContent = counts.in_progress;
  document.getElementById('cnt-completed').textContent = counts.completed;
  document.getElementById('cnt-error').textContent = counts.error;
  document.getElementById('cnt-review').textContent = counts.review;
}

async function loadStats() {
  const res = await fetch('/api/stats');
  const s = await res.json();
  document.getElementById('stats').innerHTML = `合計: <span>${s.total}</span> | 完了率: <span>${s.completion_rate}%</span>`;
}

// ドラッグ&ドロップ
document.querySelectorAll('.column-body').forEach(col => {
  col.addEventListener('dragover', e => { e.preventDefault(); col.classList.add('drag-over'); });
  col.addEventListener('dragleave', () => col.classList.remove('drag-over'));
  col.addEventListener('drop', async e => {
    e.preventDefault();
    col.classList.remove('drag-over');
    const id = e.dataTransfer.getData('text/plain');
    const newStatus = col.closest('.column').dataset.status;
    await fetch('/api/tasks/' + id, { method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify({status: newStatus}) });
    loadTasks();
  });
});

// モーダル
function openAddModal() { document.getElementById('addModal').classList.add('active'); document.getElementById('addName').focus(); }
function closeModal(id) { document.getElementById(id).classList.remove('active'); }
document.querySelectorAll('.modal-overlay').forEach(m => m.addEventListener('click', e => { if (e.target === m) m.classList.remove('active'); }));

async function submitAdd() {
  const name = document.getElementById('addName').value.trim();
  if (!name) return alert('タスク名を入力してください');
  const body = {
    task_name: name,
    task_type: document.getElementById('addType').value || 'research',
    priority: document.getElementById('addPriority').value,
    input: document.getElementById('addInput').value,
  };
  const model = document.getElementById('addTaskModel').value;
  const mcp = document.getElementById('addTaskMcp').value;
  const timeout = document.getElementById('addTaskTimeout').value;
  const maxTurns = document.getElementById('addTaskMaxTurns').value;
  const workDir = document.getElementById('addTaskWorkDir').value;
  const tools = document.getElementById('addTaskTools').value;
  if (model) body.model = model;
  if (mcp) body.mcp_config = mcp;
  if (timeout) body.timeout_seconds = parseInt(timeout);
  if (maxTurns) body.max_turns = parseInt(maxTurns);
  if (workDir) body.work_dir = workDir;
  if (tools) body.allowed_tools = tools;
  await fetch('/api/tasks', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
  closeModal('addModal');
  document.getElementById('addName').value = '';
  document.getElementById('addInput').value = '';
  loadTasks();
}

function openDetail(task) {
  document.getElementById('detailTitle').textContent = task.task_name;
  document.getElementById('detailMeta').innerHTML = `
    <span class="${badgeClass(task.task_type)}">${task.task_type}</span>
    <span class="priority-dot priority-${task.priority}"></span>
    <span style="font-size:.8rem;color:#888">Status: ${task.status}</span>`;
  document.getElementById('detailInput').textContent = task.input || '(なし)';
  document.getElementById('detailResult').textContent = task.result || '(なし)';
  document.getElementById('detailCreated').textContent = task.created_at || '';
  document.getElementById('detailUpdated').textContent = task.updated_at || '';
  document.getElementById('detailDeleteBtn').onclick = async () => {
    if (!confirm('このタスクを削除しますか？')) return;
    await fetch('/api/tasks/' + task.id, { method:'DELETE' });
    closeModal('detailModal');
    loadTasks();
  };
  document.getElementById('detailModal').classList.add('active');
}

// 初期読み込み + 自動リフレッシュ
loadTasks();
setInterval(loadTasks, 30000);
</script>
</body>
</html>"""


LOGS_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db", "logs.db")
CRON_NEXT_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "cron-next.py")

# ── ログビューア HTML テンプレート ─────────────────────────────────
LOGS_HTML = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Claude Task Runner - Logs</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#1a1a2e;color:#e0e0e0;min-height:100vh}
header{background:#0f3460;padding:16px 24px;display:flex;align-items:center;justify-content:space-between;box-shadow:0 2px 8px rgba(0,0,0,.3)}
header h1{font-size:1.4rem;font-weight:700;color:#e94560}
header nav{display:flex;gap:8px;margin-left:auto}
header nav a{color:#3a86ff;border:1px solid #3a86ff;padding:8px 16px;border-radius:6px;font-size:.85rem;font-weight:600;text-decoration:none;transition:background .2s,color .2s}
header nav a:hover{background:#3a86ff;color:#fff}
header nav a.active{background:#3a86ff;color:#fff}
.container{padding:20px 24px;max-width:1400px;margin:0 auto}
.filters{display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;align-items:center}
.filters select{padding:6px 12px;border-radius:6px;border:1px solid #2a2a4e;background:#16213e;color:#e0e0e0;font-size:.85rem}
.filters label{font-size:.85rem;color:#a0a0b8}
.stats-bar{display:flex;gap:20px;margin-bottom:20px;flex-wrap:wrap}
.stat-card{background:#16213e;border-radius:8px;padding:12px 20px;min-width:140px}
.stat-card .stat-label{font-size:.75rem;color:#888;text-transform:uppercase}
.stat-card .stat-value{font-size:1.4rem;font-weight:700;color:#e94560}
.cost-chart{background:#16213e;border-radius:8px;padding:16px;margin-bottom:20px}
.cost-chart h3{font-size:.9rem;color:#a0a0b8;margin-bottom:12px}
.chart-bars{display:flex;align-items:flex-end;gap:4px;height:80px}
.chart-bar{flex:1;min-width:20px;max-width:40px;background:#3a86ff;border-radius:3px 3px 0 0;position:relative;cursor:default;transition:background .2s}
.chart-bar:hover{background:#5a9fff}
.chart-bar .chart-tip{display:none;position:absolute;bottom:calc(100% + 4px);left:50%;transform:translateX(-50%);background:#0f3460;color:#e0e0e0;padding:4px 8px;border-radius:4px;font-size:.7rem;white-space:nowrap;z-index:10}
.chart-bar:hover .chart-tip{display:block}
.chart-labels{display:flex;gap:4px;margin-top:4px}
.chart-labels span{flex:1;min-width:20px;max-width:40px;text-align:center;font-size:.6rem;color:#666}
table{width:100%;border-collapse:collapse;font-size:.85rem}
thead th{background:#0f3460;padding:10px 12px;text-align:left;font-weight:600;font-size:.8rem;color:#a0a0b8;position:sticky;top:0}
tbody tr{cursor:pointer;transition:background .15s}
tbody tr:nth-child(even){background:#16213e}
tbody tr:nth-child(odd){background:#1a1a3e}
tbody tr:hover{background:#1e2a50}
tbody td{padding:8px 12px;border-bottom:1px solid #2a2a4e}
.status-badge{padding:2px 8px;border-radius:4px;font-size:.75rem;font-weight:600;display:inline-block}
.status-success{background:#2ecc7133;color:#2ecc71}
.status-error{background:#e74c3c33;color:#e74c3c}
.status-timeout{background:#e67e2233;color:#e67e22}
.status-skipped{background:#88888833;color:#888}
.status-unknown{background:#88888833;color:#888}
.table-wrap{overflow-x:auto;border-radius:8px;border:1px solid #2a2a4e}
.pagination{display:flex;gap:8px;margin-top:16px;justify-content:center;align-items:center}
.pagination button{padding:6px 14px;border-radius:6px;border:1px solid #2a2a4e;background:#16213e;color:#e0e0e0;cursor:pointer;font-size:.85rem}
.pagination button:hover{background:#2a2a4e}
.pagination button:disabled{opacity:.4;cursor:default}
.pagination span{font-size:.85rem;color:#888}
/* モーダル */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;align-items:center;justify-content:center;z-index:100}
.modal-overlay.active{display:flex}
.modal{background:#16213e;border-radius:12px;padding:24px;width:90%;max-width:700px;max-height:85vh;overflow-y:auto;box-shadow:0 8px 32px rgba(0,0,0,.5)}
.modal h2{margin-bottom:16px;font-size:1.1rem;color:#e94560}
.detail-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.detail-field{margin-bottom:8px}
.detail-field .label{font-size:.75rem;color:#888;margin-bottom:2px}
.detail-field .value{background:#1a1a2e;padding:8px 10px;border-radius:6px;font-size:.82rem;white-space:pre-wrap;word-break:break-word;max-height:200px;overflow-y:auto}
.detail-field.full{grid-column:1/-1}
.modal-actions{display:flex;justify-content:flex-end;margin-top:16px}
.modal-actions button{padding:8px 20px;border-radius:6px;border:none;font-size:.9rem;cursor:pointer;font-weight:600;background:#2a2a4e;color:#e0e0e0}
.modal-actions button:hover{background:#3a3a5e}
</style>
</head>
<body>
<header>
  <h1>Claude Task Runner</h1>
  <nav>
    <a href="/">Kanban</a>
    <a href="/logs" class="active">Logs</a>
    <a href="/schedules">Schedules</a>
    <a href="/prompts">Prompts</a>
  </nav>
</header>
<div class="container">
  <div class="stats-bar" id="statsBar"></div>
  <div class="cost-chart" id="costChart"><h3>日別コスト (USD)</h3><div class="chart-bars" id="chartBars"></div><div class="chart-labels" id="chartLabels"></div></div>
  <div class="filters">
    <label>Runner:
      <select id="filterRunner" onchange="loadLogs()">
        <option value="">全て</option>
        <option value="task_runner">task_runner</option>
        <option value="email_checker">email_checker</option>
      </select>
    </label>
    <label>Status:
      <select id="filterStatus" onchange="loadLogs()">
        <option value="">全て</option>
        <option value="success">success</option>
        <option value="error">error</option>
        <option value="timeout">timeout</option>
        <option value="skipped">skipped</option>
      </select>
    </label>
  </div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Timestamp</th><th>Runner</th><th>Source</th><th>Type</th><th>Task Name</th><th>Status</th><th>Cost</th><th>Duration</th>
        </tr>
      </thead>
      <tbody id="logBody"></tbody>
    </table>
  </div>
  <div class="pagination">
    <button id="prevBtn" onclick="changePage(-1)">← 前</button>
    <span id="pageInfo"></span>
    <button id="nextBtn" onclick="changePage(1)">次 →</button>
  </div>
</div>

<!-- 詳細モーダル -->
<div class="modal-overlay" id="logDetailModal">
  <div class="modal">
    <h2 id="logDetailTitle"></h2>
    <div class="detail-grid" id="logDetailGrid"></div>
    <div class="modal-actions">
      <button onclick="document.getElementById('logDetailModal').classList.remove('active')">閉じる</button>
    </div>
  </div>
</div>

<script>
let currentOffset = 0;
const PAGE_SIZE = 50;

function statusClass(s) { return 'status-badge status-' + (s || 'unknown'); }

function esc(s) { if (!s) return ''; const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

function fmtCost(v) { return v != null ? '$' + v.toFixed(4) : '-'; }
function fmtDuration(v) { return v != null ? v + 's' : '-'; }

async function loadStats() {
  const res = await fetch('/api/logs/stats');
  const s = await res.json();
  document.getElementById('statsBar').innerHTML = `
    <div class="stat-card"><div class="stat-label">総実行回数</div><div class="stat-value">${s.total_runs}</div></div>
    <div class="stat-card"><div class="stat-label">成功率</div><div class="stat-value">${s.success_rate}%</div></div>
    <div class="stat-card"><div class="stat-label">合計コスト</div><div class="stat-value">${fmtCost(s.total_cost)}</div></div>
  `;
  // 日別コストチャート
  const days = s.daily_costs || [];
  if (days.length === 0) {
    document.getElementById('costChart').style.display = 'none';
    return;
  }
  const maxCost = Math.max(...days.map(d => d.cost), 0.001);
  document.getElementById('chartBars').innerHTML = days.map(d => {
    const h = Math.max(2, (d.cost / maxCost) * 70);
    return `<div class="chart-bar" style="height:${h}px"><div class="chart-tip">${d.date}<br>${fmtCost(d.cost)}</div></div>`;
  }).join('');
  document.getElementById('chartLabels').innerHTML = days.map(d =>
    `<span>${d.date.slice(5)}</span>`
  ).join('');
}

async function loadLogs() {
  const runner = document.getElementById('filterRunner').value;
  const status = document.getElementById('filterStatus').value;
  let url = `/api/logs?limit=${PAGE_SIZE}&offset=${currentOffset}`;
  if (runner) url += `&runner_type=${runner}`;
  if (status) url += `&status=${status}`;
  const res = await fetch(url);
  const logs = await res.json();
  const tbody = document.getElementById('logBody');
  tbody.innerHTML = '';
  logs.forEach(log => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${esc(log.timestamp)}</td>
      <td>${esc(log.runner_type)}</td>
      <td>${esc(log.task_source || '-')}</td>
      <td>${esc(log.task_type || '-')}</td>
      <td>${esc(log.task_name || '-')}</td>
      <td><span class="${statusClass(log.status)}">${log.status}</span></td>
      <td>${fmtCost(log.cost_usd)}</td>
      <td>${fmtDuration(log.duration_seconds)}</td>`;
    tr.addEventListener('click', () => openLogDetail(log.id));
    tbody.appendChild(tr);
  });
  document.getElementById('pageInfo').textContent = `${currentOffset + 1} - ${currentOffset + logs.length}`;
  document.getElementById('prevBtn').disabled = currentOffset === 0;
  document.getElementById('nextBtn').disabled = logs.length < PAGE_SIZE;
}

function changePage(dir) {
  currentOffset = Math.max(0, currentOffset + dir * PAGE_SIZE);
  loadLogs();
}

async function openLogDetail(id) {
  const res = await fetch(`/api/logs/${id}`);
  if (!res.ok) return;
  const log = await res.json();
  document.getElementById('logDetailTitle').textContent = log.task_name || `Log #${log.id}`;
  const fields = [
    ['Timestamp', log.timestamp], ['Runner', log.runner_type],
    ['Source', log.task_source], ['Type', log.task_type],
    ['Status', log.status], ['Model', log.model],
    ['Cost', fmtCost(log.cost_usd)], ['Duration', fmtDuration(log.duration_seconds)],
    ['Input Tokens', log.input_tokens], ['Output Tokens', log.output_tokens],
  ];
  const fullFields = [
    ['Result Summary', log.result_summary],
    ['Result Detail', log.result_detail],
    ['Error Message', log.error_message],
    ['Raw Response', log.raw_response],
  ];
  let html = fields.map(([l,v]) => `<div class="detail-field"><div class="label">${l}</div><div class="value">${esc(String(v != null ? v : '-'))}</div></div>`).join('');
  html += fullFields.map(([l,v]) => `<div class="detail-field full"><div class="label">${l}</div><div class="value">${esc(String(v || '-'))}</div></div>`).join('');
  document.getElementById('logDetailGrid').innerHTML = html;
  document.getElementById('logDetailModal').classList.add('active');
}

document.getElementById('logDetailModal').addEventListener('click', e => {
  if (e.target === document.getElementById('logDetailModal')) document.getElementById('logDetailModal').classList.remove('active');
});

loadStats();
loadLogs();
</script>
</body>
</html>"""


# ── Schedules HTML テンプレート ────────────────────────────────────
SCHEDULES_HTML = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Claude Task Runner - Schedules</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#1a1a2e;color:#e0e0e0;min-height:100vh}
header{background:#0f3460;padding:16px 24px;display:flex;align-items:center;justify-content:space-between;box-shadow:0 2px 8px rgba(0,0,0,.3)}
header h1{font-size:1.4rem;font-weight:700;color:#e94560}
header nav{display:flex;gap:8px;margin-left:auto}
header nav a{color:#3a86ff;border:1px solid #3a86ff;padding:8px 16px;border-radius:6px;font-size:.85rem;font-weight:600;text-decoration:none;transition:background .2s,color .2s}
header nav a:hover,header nav a.active{background:#3a86ff;color:#fff}
.container{padding:20px 24px;max-width:1400px;margin:0 auto}
.toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}
.toolbar h2{font-size:1.1rem;color:#a0a0b8}
.btn-add{background:#e94560;color:#fff;border:none;padding:8px 20px;border-radius:6px;font-size:.9rem;cursor:pointer;font-weight:600;transition:background .2s}
.btn-add:hover{background:#c73650}
table{width:100%;border-collapse:collapse;font-size:.85rem}
thead th{background:#0f3460;padding:10px 12px;text-align:left;font-weight:600;font-size:.8rem;color:#a0a0b8;position:sticky;top:0}
tbody tr{transition:background .15s}
tbody tr:nth-child(even){background:#16213e}
tbody tr:nth-child(odd){background:#1a1a3e}
tbody tr:hover{background:#1e2a50}
tbody td{padding:8px 12px;border-bottom:1px solid #2a2a4e}
.table-wrap{overflow-x:auto;border-radius:8px;border:1px solid #2a2a4e}
.toggle{cursor:pointer;font-size:1.2rem;user-select:none}
.toggle:hover{opacity:.7}
.btn-sm{padding:4px 10px;border-radius:4px;border:none;font-size:.75rem;cursor:pointer;font-weight:600;transition:background .2s}
.btn-run{background:#3a86ff;color:#fff}.btn-run:hover{background:#2a76ef}
.btn-del{background:#e74c3c;color:#fff}.btn-del:hover{background:#c0392b}
.status-badge{padding:2px 8px;border-radius:4px;font-size:.75rem;font-weight:600;display:inline-block}
.status-success{background:#2ecc7133;color:#2ecc71}
.status-error{background:#e74c3c33;color:#e74c3c}
.status-timeout{background:#e67e2233;color:#e67e22}
/* モーダル */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;align-items:center;justify-content:center;z-index:100}
.modal-overlay.active{display:flex}
.modal{background:#16213e;border-radius:12px;padding:24px;width:90%;max-width:640px;max-height:85vh;overflow-y:auto;box-shadow:0 8px 32px rgba(0,0,0,.5)}
.modal h2{margin-bottom:16px;font-size:1.1rem;color:#e94560}
.modal label{display:block;font-size:.85rem;color:#a0a0b8;margin-bottom:4px;margin-top:12px}
.modal input,.modal select,.modal textarea{width:100%;padding:8px 12px;border-radius:6px;border:1px solid #2a2a4e;background:#1a1a2e;color:#e0e0e0;font-size:.9rem}
.modal textarea{min-height:80px;resize:vertical}
.form-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.modal-actions{display:flex;gap:12px;margin-top:20px;justify-content:flex-end}
.modal-actions button{padding:8px 20px;border-radius:6px;border:none;font-size:.9rem;cursor:pointer;font-weight:600}
.btn-primary{background:#e94560;color:#fff}.btn-primary:hover{background:#c73650}
.btn-cancel{background:#2a2a4e;color:#e0e0e0}.btn-cancel:hover{background:#3a3a5e}
.detail-field{margin-bottom:8px}
.detail-field .label{font-size:.75rem;color:#888;margin-bottom:2px}
.detail-field .value{background:#1a1a2e;padding:8px 10px;border-radius:6px;font-size:.82rem;white-space:pre-wrap;word-break:break-word;max-height:200px;overflow-y:auto}
</style>
</head>
<body>
<header>
  <h1>Claude Task Runner</h1>
  <nav>
    <a href="/">Kanban</a>
    <a href="/logs">Logs</a>
    <a href="/schedules" class="active">Schedules</a>
    <a href="/prompts">Prompts</a>
  </nav>
</header>
<div class="container">
  <div class="toolbar">
    <h2>Schedules</h2>
    <button class="btn-add" onclick="openAddModal()">+ スケジュール追加</button>
  </div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>ID</th><th>有効</th><th>名前</th><th>cron式</th><th>バックエンド</th><th>種別</th><th>次回実行</th><th>状態</th><th>失敗</th><th>操作</th>
        </tr>
      </thead>
      <tbody id="scheduleBody"></tbody>
    </table>
  </div>
</div>

<!-- 追加モーダル -->
<div class="modal-overlay" id="addModal">
  <div class="modal">
    <h2>スケジュール追加</h2>
    <label>名前 *</label>
    <input type="text" id="addName" placeholder="例: 朝のメールチェック、週次Sentryレビュー">
    <label>cron式 *</label>
    <select id="addCronPreset" onchange="if(this.value)document.getElementById('addCron').value=this.value" style="margin-bottom:6px">
      <option value="">-- プリセットから選択 --</option>
      <option value="*/10 * * * *">10分毎</option>
      <option value="*/30 * * * *">30分毎</option>
      <option value="0 * * * *">毎時0分</option>
      <option value="0 9 * * *">毎日 9:00</option>
      <option value="0 9 * * 1-5">平日 9:00</option>
      <option value="7 8-20 * * 1-5">平日 8:07〜20:07（毎時7分）</option>
      <option value="0 9,15 * * 1-5">平日 9:00 と 15:00</option>
      <option value="0 9 * * 1">毎週月曜 9:00</option>
      <option value="0 0 1 * *">毎月1日 0:00</option>
    </select>
    <input type="text" id="addCron" placeholder="分 時 日 月 曜日（例: 7 8-20 * * 1-5）">
    <div class="form-row">
      <div><label>ラベル <span style="font-size:.7rem;color:#666">分類用（自由入力）</span></label>
      <input type="text" id="addType" list="typeList" placeholder="例: research, email_check">
      <datalist id="typeList">
        <option value="research">技術調査・コードベース分析</option>
        <option value="planning">要件→実装計画作成</option>
        <option value="code_review">PRレビューコメント投稿</option>
        <option value="sentry_analysis">Sentryイシュー原因調査</option>
        <option value="email_check">メール確認・要約</option>
      </datalist></div>
      <div><label>優先度 <span style="font-size:.7rem;color:#666">spotタスクより後に処理される</span></label>
      <select id="addPriority">
        <option value="medium">medium</option>
        <option value="high">high</option>
        <option value="low">low</option>
      </select></div>
    </div>
    <div class="form-row">
      <div><label>バックエンド</label>
      <select id="addBackend">
        <option value="claude">claude</option>
        <option value="ollama">ollama</option>
        <option value="codex">codex</option>
      </select></div>
      <div><label>モデル</label>
      <select id="addModel">
        <option value="sonnet" selected>sonnet</option>
        <option value="opus">opus</option>
        <option value="haiku">haiku</option>
      </select></div>
    </div>
    <label>プロンプト</label>
    <textarea id="addPrompt" placeholder="Claudeへの指示内容を記述&#10;&#10;例: 未読メールを確認し、重要なものを要約してください"></textarea>
    <label>プロンプトファイル <span style="font-size:.75rem;color:#666">（プロンプト欄が空の場合にこのファイルを使用。<a href="/prompts" style="color:#3a86ff">Prompts</a>で管理）</span></label>
    <select id="addPromptFile" style="margin-bottom:2px">
      <option value="">-- なし（上のプロンプト欄を使用）--</option>
    </select>
    <div class="form-row">
      <div><label>MCP接続 <span style="font-size:.75rem;color:#666">外部サービスとの連携</span></label>
      <input type="text" id="addMcpConfig" list="mcpList" placeholder="なし（標準ツールのみ）">
      <datalist id="mcpList">
        <option value="mcp-config-email.json">Google Workspace（Gmail等）</option>
        <option value="mcp-config-sentry.json">Sentry</option>
        <option value="sources/notion/mcp-config.json">Notion</option>
        <option value="/Users/t.matsue/project/manager/truckers_manager/.mcp.json">truckers_manager（Sentry+Notion+Serena）</option>
      </datalist></div>
      <div><label>許可ツール <span style="font-size:.75rem;color:#666">Claudeが使えるツール</span></label>
      <select id="addToolsPreset" onchange="document.getElementById('addTools').value=this.value">
        <option value="">標準（Read,Grep,検索等）</option>
        <option value="Read Grep Glob WebSearch WebFetch Bash(sqlite3:*) Bash(curl:*)">標準 + DB操作 + curl</option>
        <option value="Read Grep Glob WebSearch WebFetch Bash(git:*) Bash(gh:*)">標準 + Git + GitHub CLI</option>
        <option value="mcp__google_workspace_mcp__search_gmail_messages,mcp__google_workspace_mcp__get_gmail_message_content,mcp__google_workspace_mcp__get_gmail_messages_content_batch,mcp__google_workspace_mcp__get_events,mcp__google_workspace_mcp__list_tasks">Gmail + Calendar + Tasks（読み取り専用）</option>
        <option value="Read Grep Glob WebSearch WebFetch mcp__sentry__search_issues mcp__sentry__get_sentry_resource">Sentry（issue検索・閲覧）</option>
      </select>
      <input type="text" id="addTools" placeholder="カスタム指定時のみ入力" style="margin-top:4px;font-size:.8rem"></div>
    </div>

    <!-- 詳細設定（折りたたみ） -->
    <details style="margin-top:16px;border:1px solid #2a2a4e;border-radius:6px;padding:0 12px">
      <summary style="cursor:pointer;padding:10px 0;color:#a0a0b8;font-size:.85rem;font-weight:600">詳細設定</summary>
      <div class="form-row">
        <div><label>タイムアウト(秒) <span style="font-size:.75rem;color:#666">処理の制限時間</span></label>
        <input type="number" id="addTimeout" value="300">
        <div style="font-size:.7rem;color:#666;margin-top:2px">300秒=5分。長い調査は600秒程度に</div></div>
        <div><label>最大ターン <span style="font-size:.75rem;color:#666">Claudeの思考回数上限</span></label>
        <input type="number" id="addMaxTurns" value="30">
        <div style="font-size:.7rem;color:#666;margin-top:2px">1ターン=1回のツール使用。通常30で十分</div></div>
      </div>
      <div class="form-row">
        <div><label>連続失敗上限</label>
        <input type="number" id="addMaxFailures" value="3">
        <div style="font-size:.7rem;color:#666;margin-top:2px">この回数連続で失敗すると自動で無効化</div></div>
        <div><label>セッション永続 <span style="font-size:.75rem;color:#666">前回の会話を引き継ぐ</span></label>
        <select id="addPersistent"><option value="0">いいえ（毎回新規）</option><option value="1">はい（前回から継続）</option></select>
        <div style="font-size:.7rem;color:#666;margin-top:2px">メールチェック等、文脈を保持したい場合にオン</div></div>
      </div>
      <label>作業ディレクトリ <span style="font-size:.75rem;color:#666">別プロジェクトのコードを対象にする場合</span></label>
      <input type="text" id="addWorkDir" placeholder="例: /Users/t.matsue/project/my-app（省略時はこのプロジェクト）">
      <div style="font-size:.7rem;color:#666;margin-top:2px;margin-bottom:12px">Claudeがファイルを読み書きするルートディレクトリ</div>
    </details>
    <div class="modal-actions">
      <button class="btn-cancel" onclick="closeModal('addModal')">キャンセル</button>
      <button class="btn-primary" onclick="submitAdd()">追加</button>
    </div>
  </div>
</div>

<!-- 詳細モーダル -->
<div class="modal-overlay" id="detailModal">
  <div class="modal">
    <h2 id="detailTitle"></h2>
    <div id="detailContent"></div>
    <div class="modal-actions">
      <button class="btn-cancel" onclick="closeModal('detailModal')">閉じる</button>
    </div>
  </div>
</div>

<script>
function esc(s) { if (!s) return ''; const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

async function loadSchedules() {
  const res = await fetch('/api/schedules');
  const schedules = await res.json();
  const tbody = document.getElementById('scheduleBody');
  tbody.innerHTML = '';
  schedules.forEach(s => {
    const tr = document.createElement('tr');
    const statusCls = s.last_status ? 'status-badge status-' + s.last_status : '';
    tr.innerHTML = `
      <td>${s.id}</td>
      <td><span class="toggle" onclick="toggleEnabled(${s.id}, ${s.enabled ? 0 : 1})">${s.enabled ? '\u25cf' : '\u25cb'}</span></td>
      <td style="cursor:pointer;text-decoration:underline" onclick="openDetail(${s.id})">${esc(s.name)}</td>
      <td><code>${esc(s.cron_expr)}</code></td>
      <td>${esc(s.backend)}+${esc(s.model)}</td>
      <td>${esc(s.task_type)}</td>
      <td>${esc(s.next_run_at || '-')}</td>
      <td>${s.last_status ? '<span class="' + statusCls + '">' + s.last_status + '</span>' : '-'}</td>
      <td>${s.consecutive_failures}/${s.max_consecutive_failures}</td>
      <td>
        <button class="btn-sm btn-run" onclick="triggerRun(${s.id})">実行</button>
        <button class="btn-sm btn-del" onclick="deleteSchedule(${s.id}, '${esc(s.name)}')">削除</button>
      </td>`;
    tbody.appendChild(tr);
  });
}

async function toggleEnabled(id, newVal) {
  await fetch('/api/schedules/' + id, { method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify({enabled: newVal}) });
  loadSchedules();
}

async function triggerRun(id) {
  await fetch('/api/schedules/' + id + '/trigger', { method:'POST' });
  loadSchedules();
  alert('手動トリガーしました。次のrun-tasks.sh実行時に処理されます。');
}

async function deleteSchedule(id, name) {
  if (!confirm('スケジュール "' + name + '" を削除しますか？')) return;
  await fetch('/api/schedules/' + id, { method:'DELETE' });
  loadSchedules();
}

async function openDetail(id) {
  const res = await fetch('/api/schedules/' + id);
  if (!res.ok) return;
  const s = await res.json();
  document.getElementById('detailTitle').textContent = s.name;
  const fields = [
    ['ID', s.id], ['有効', s.enabled ? 'はい' : 'いいえ'], ['cron式', s.cron_expr],
    ['種別', s.task_type], ['優先度', s.priority], ['バックエンド', s.backend + '+' + s.model],
    ['タイムアウト', s.timeout_seconds + '秒'], ['最大ターン', s.max_turns],
    ['セッション永続', s.session_persistent ? 'はい' : 'いいえ'],
    ['作業ディレクトリ', s.work_dir || '-'], ['MCP設定', s.mcp_config || '-'],
    ['許可ツール', s.allowed_tools || '-'],
    ['最終実行', s.last_run_at || '-'], ['次回実行', s.next_run_at || '-'],
    ['最終状態', s.last_status || '-'], ['連続失敗', s.consecutive_failures + '/' + s.max_consecutive_failures],
    ['作成日時', s.created_at], ['更新日時', s.updated_at],
  ];
  const fullFields = [
    ['プロンプト', s.prompt], ['プロンプトファイル', s.prompt_file],
  ];
  let html = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">';
  html += fields.map(([l,v]) => `<div class="detail-field"><div class="label">${l}</div><div class="value">${esc(String(v != null ? v : '-'))}</div></div>`).join('');
  html += '</div>';
  html += fullFields.map(([l,v]) => `<div class="detail-field"><div class="label">${l}</div><div class="value">${esc(String(v || '-'))}</div></div>`).join('');
  document.getElementById('detailContent').innerHTML = html;
  document.getElementById('detailModal').classList.add('active');
}

function openAddModal() { document.getElementById('addModal').classList.add('active'); document.getElementById('addName').focus(); }
function closeModal(id) { document.getElementById(id).classList.remove('active'); }
document.querySelectorAll('.modal-overlay').forEach(m => m.addEventListener('click', e => { if (e.target === m) m.classList.remove('active'); }));

async function submitAdd() {
  const name = document.getElementById('addName').value.trim();
  const cron = document.getElementById('addCron').value.trim();
  if (!name) return alert('名前を入力してください');
  if (!cron) return alert('cron式を入力してください');
  const body = {
    name, cron_expr: cron,
    task_type: document.getElementById('addType').value,
    priority: document.getElementById('addPriority').value,
    backend: document.getElementById('addBackend').value,
    model: document.getElementById('addModel').value || 'sonnet',
    description: '',
    prompt: document.getElementById('addPrompt').value,
    prompt_file: document.getElementById('addPromptFile').value,
    timeout_seconds: parseInt(document.getElementById('addTimeout').value) || 300,
    max_turns: parseInt(document.getElementById('addMaxTurns').value) || 30,
    work_dir: document.getElementById('addWorkDir').value,
    mcp_config: document.getElementById('addMcpConfig').value,
    allowed_tools: document.getElementById('addTools').value,
    max_consecutive_failures: parseInt(document.getElementById('addMaxFailures').value) || 3,
    session_persistent: parseInt(document.getElementById('addPersistent').value) || 0,
  };
  const res = await fetch('/api/schedules', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
  if (!res.ok) { const e = await res.json(); return alert('エラー: ' + (e.error || 'Unknown')); }
  closeModal('addModal');
  document.getElementById('addName').value = '';
  document.getElementById('addCron').value = '';
  document.getElementById('addPrompt').value = '';
  document.getElementById('addPromptFile').selectedIndex = 0;
  document.getElementById('addWorkDir').value = '';
  document.getElementById('addMcpConfig').selectedIndex = 0;
  document.getElementById('addToolsPreset').selectedIndex = 0;
  document.getElementById('addTools').value = '';
  loadSchedules();
}

async function loadPromptFiles() {
  const sel = document.getElementById('addPromptFile');
  sel.innerHTML = '<option value="">-- なし（上のプロンプト欄を使用）--</option>';
  try {
    const res = await fetch('/api/prompts');
    const prompts = await res.json();
    prompts.forEach(p => {
      const opt = document.createElement('option');
      opt.value = 'prompts/' + p.name;
      opt.textContent = p.name + ' (' + p.size + 'B)';
      sel.appendChild(opt);
    });
  } catch(e) {}
}

loadSchedules();
loadPromptFiles();
setInterval(loadSchedules, 30000);
</script>
</body>
</html>"""


# ── Prompts（スキル）管理 HTML テンプレート ─────────────────────────
PROMPTS_HTML = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Claude Task Runner - Prompts</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#1a1a2e;color:#e0e0e0;min-height:100vh}
header{background:#0f3460;padding:16px 24px;display:flex;align-items:center;justify-content:space-between;box-shadow:0 2px 8px rgba(0,0,0,.3)}
header h1{font-size:1.4rem;font-weight:700;color:#e94560}
header nav{display:flex;gap:8px;margin-left:auto}
header nav a{color:#3a86ff;border:1px solid #3a86ff;padding:8px 16px;border-radius:6px;font-size:.85rem;font-weight:600;text-decoration:none;transition:background .2s,color .2s}
header nav a:hover,header nav a.active{background:#3a86ff;color:#fff}
.container{padding:20px 24px;max-width:1200px;margin:0 auto}
.toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}
.toolbar h2{font-size:1.1rem;color:#a0a0b8}
.btn-add{background:#e94560;color:#fff;border:none;padding:8px 20px;border-radius:6px;font-size:.9rem;cursor:pointer;font-weight:600;transition:background .2s}
.btn-add:hover{background:#c73650}
.prompt-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}
.prompt-card{background:#16213e;border:1px solid #2a2a4e;border-radius:10px;padding:16px;cursor:pointer;transition:transform .15s,box-shadow .15s}
.prompt-card:hover{transform:translateY(-2px);box-shadow:0 4px 12px rgba(0,0,0,.3)}
.prompt-card h3{font-size:.95rem;margin-bottom:8px;color:#e94560}
.prompt-card .meta{font-size:.75rem;color:#888;margin-bottom:8px}
.prompt-card .preview{font-size:.8rem;color:#a0a0b8;max-height:60px;overflow:hidden;white-space:pre-wrap;word-break:break-word}
/* モーダル */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;align-items:center;justify-content:center;z-index:100}
.modal-overlay.active{display:flex}
.modal{background:#16213e;border-radius:12px;padding:24px;width:90%;max-width:720px;max-height:85vh;overflow-y:auto;box-shadow:0 8px 32px rgba(0,0,0,.5)}
.modal h2{margin-bottom:16px;font-size:1.1rem;color:#e94560}
.modal label{display:block;font-size:.85rem;color:#a0a0b8;margin-bottom:4px;margin-top:12px}
.modal input,.modal textarea{width:100%;padding:8px 12px;border-radius:6px;border:1px solid #2a2a4e;background:#1a1a2e;color:#e0e0e0;font-size:.9rem}
.modal textarea{min-height:320px;resize:vertical;font-family:'SF Mono',Menlo,Consolas,monospace;font-size:.82rem;line-height:1.5}
.modal-actions{display:flex;gap:12px;margin-top:20px;justify-content:flex-end}
.modal-actions button{padding:8px 20px;border-radius:6px;border:none;font-size:.9rem;cursor:pointer;font-weight:600}
.btn-primary{background:#e94560;color:#fff}.btn-primary:hover{background:#c73650}
.btn-cancel{background:#2a2a4e;color:#e0e0e0}.btn-cancel:hover{background:#3a3a5e}
.btn-delete{background:#e74c3c;color:#fff}.btn-delete:hover{background:#c0392b}
.hint{font-size:.75rem;color:#666;margin-top:4px}
</style>
</head>
<body>
<header>
  <h1>Claude Task Runner</h1>
  <nav>
    <a href="/">Kanban</a>
    <a href="/logs">Logs</a>
    <a href="/schedules">Schedules</a>
    <a href="/prompts" class="active">Prompts</a>
  </nav>
</header>
<div class="container">
  <div class="toolbar">
    <h2>Prompts</h2>
    <button class="btn-add" onclick="openNewModal()">+ 新規作成</button>
  </div>
  <div class="prompt-grid" id="promptGrid"></div>
</div>

<!-- 編集モーダル -->
<div class="modal-overlay" id="editModal">
  <div class="modal">
    <h2 id="editTitle">プロンプト編集</h2>
    <label>ファイル名</label>
    <input type="text" id="editName" placeholder="例: weekly-sentry-review">
    <div class="hint">.txt は自動付与。英数字・ハイフン・アンダースコアのみ</div>
    <label>内容</label>
    <textarea id="editContent" placeholder="Claudeへの指示内容を記述..."></textarea>
    <div class="modal-actions">
      <button class="btn-delete" id="editDeleteBtn" style="margin-right:auto;display:none" onclick="deletePrompt()">削除</button>
      <button class="btn-cancel" onclick="closeModal()">キャンセル</button>
      <button class="btn-primary" onclick="savePrompt()">保存</button>
    </div>
  </div>
</div>

<script>
let editingFile = null; // null=新規, 'xxx.txt'=編集

function esc(s) { if (!s) return ''; const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

async function loadPrompts() {
  const res = await fetch('/api/prompts');
  const prompts = await res.json();
  const grid = document.getElementById('promptGrid');
  grid.innerHTML = '';
  if (prompts.length === 0) {
    grid.innerHTML = '<div style="color:#888;padding:20px">プロンプトファイルがありません。「+ 新規作成」から追加できます。</div>';
    return;
  }
  prompts.forEach(p => {
    const card = document.createElement('div');
    card.className = 'prompt-card';
    card.onclick = () => openEditModal(p.name);
    const lines = (p.content || '').split('\n').length;
    card.innerHTML = `
      <h3>${esc(p.name)}</h3>
      <div class="meta">${lines}行 / ${p.size}B / ${p.modified || ''}</div>
      <div class="preview">${esc((p.content || '').slice(0, 150))}</div>`;
    grid.appendChild(card);
  });
}

function openNewModal() {
  editingFile = null;
  document.getElementById('editTitle').textContent = '新規プロンプト作成';
  document.getElementById('editName').value = '';
  document.getElementById('editName').disabled = false;
  document.getElementById('editContent').value = '';
  document.getElementById('editDeleteBtn').style.display = 'none';
  document.getElementById('editModal').classList.add('active');
  document.getElementById('editName').focus();
}

async function openEditModal(name) {
  const res = await fetch('/api/prompts/' + encodeURIComponent(name));
  if (!res.ok) return;
  const p = await res.json();
  editingFile = name;
  document.getElementById('editTitle').textContent = name;
  document.getElementById('editName').value = name.replace(/\.txt$/, '');
  document.getElementById('editName').disabled = true;
  document.getElementById('editContent').value = p.content || '';
  document.getElementById('editDeleteBtn').style.display = 'inline-block';
  document.getElementById('editModal').classList.add('active');
  document.getElementById('editContent').focus();
}

function closeModal() { document.getElementById('editModal').classList.remove('active'); }
document.getElementById('editModal').addEventListener('click', e => { if (e.target === document.getElementById('editModal')) closeModal(); });

async function savePrompt() {
  let name = document.getElementById('editName').value.trim();
  const content = document.getElementById('editContent').value;
  if (!name) return alert('ファイル名を入力してください');
  if (!name.endsWith('.txt')) name += '.txt';
  if (!/^[a-zA-Z0-9_\-]+\.txt$/.test(name)) return alert('ファイル名は英数字・ハイフン・アンダースコアのみです');

  const method = editingFile ? 'PUT' : 'POST';
  const url = editingFile ? '/api/prompts/' + encodeURIComponent(editingFile) : '/api/prompts';
  const res = await fetch(url, { method, headers:{'Content-Type':'application/json'}, body: JSON.stringify({name, content}) });
  if (!res.ok) { const e = await res.json(); return alert('エラー: ' + (e.error || 'Unknown')); }
  closeModal();
  loadPrompts();
}

async function deletePrompt() {
  if (!editingFile) return;
  if (!confirm(editingFile + ' を削除しますか？')) return;
  await fetch('/api/prompts/' + encodeURIComponent(editingFile), { method:'DELETE' });
  closeModal();
  loadPrompts();
}

loadPrompts();
</script>
</body>
</html>"""


# ── DB ヘルパー ────────────────────────────────────────────────────
def get_db(db_path: str) -> sqlite3.Connection:
    """DBに接続し、必要に応じてスキーマを初期化する"""
    need_init = not os.path.exists(db_path)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if need_init and os.path.exists(SCHEMA_PATH):
        with open(SCHEMA_PATH, "r") as f:
            conn.executescript(f.read())
        print(f"[kanban] スキーマを初期化しました: {db_path}")
    return conn


def get_logs_db() -> sqlite3.Connection:
    """logs.db に接続する"""
    conn = sqlite3.connect(LOGS_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def rows_to_dicts(rows):
    return [dict(r) for r in rows]


# ── リクエストハンドラ ─────────────────────────────────────────────
class KanbanHandler(BaseHTTPRequestHandler):
    db_path = DEFAULT_DB_PATH

    def log_message(self, format, *args):
        # アクセスログを簡潔に
        sys.stderr.write(f"[kanban] {args[0]}\n")

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html, status=200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    # ── ルーティング ───────────────────────────────────────────
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        if path == "/" or path == "":
            self._send_html(KANBAN_HTML)
        elif path == "/logs":
            self._send_html(LOGS_HTML)
        elif path == "/schedules":
            self._send_html(SCHEDULES_HTML)
        elif path == "/prompts":
            self._send_html(PROMPTS_HTML)
        elif path == "/api/prompts":
            self._handle_get_prompts()
        elif path == "/api/tasks":
            self._handle_get_tasks()
        elif path == "/api/stats":
            self._handle_get_stats()
        elif path == "/api/schedules":
            self._handle_get_schedules()
        elif path == "/api/logs":
            self._handle_get_logs(qs)
        elif path == "/api/logs/stats":
            self._handle_get_logs_stats()
        else:
            m = re.match(r"^/api/logs/(\d+)$", path)
            if m:
                self._handle_get_log_detail(int(m.group(1)))
            else:
                m = re.match(r"^/api/schedules/(\d+)$", path)
                if m:
                    self._handle_get_schedule_detail(int(m.group(1)))
                else:
                    m = re.match(r"^/api/prompts/(.+)$", path)
                    if m:
                        self._handle_get_prompt(m.group(1))
                    else:
                        self._send_json({"error": "Not Found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/tasks":
            self._handle_create_task()
        elif path == "/api/schedules":
            self._handle_create_schedule()
        elif path == "/api/prompts":
            self._handle_save_prompt()
        else:
            m = re.match(r"^/api/schedules/(\d+)/trigger$", path)
            if m:
                self._handle_trigger_schedule(int(m.group(1)))
            else:
                self._send_json({"error": "Not Found"}, 404)

    def do_PATCH(self):
        path = urlparse(self.path).path
        m = re.match(r"^/api/tasks/(\d+)$", path)
        if m:
            self._handle_update_task(int(m.group(1)))
        else:
            m = re.match(r"^/api/schedules/(\d+)$", path)
            if m:
                self._handle_update_schedule(int(m.group(1)))
            else:
                self._send_json({"error": "Not Found"}, 404)

    def do_PUT(self):
        path = urlparse(self.path).path
        m = re.match(r"^/api/prompts/(.+)$", path)
        if m:
            self._handle_save_prompt(m.group(1))
        else:
            self._send_json({"error": "Not Found"}, 404)

    def do_DELETE(self):
        path = urlparse(self.path).path
        m = re.match(r"^/api/tasks/(\d+)$", path)
        if m:
            self._handle_delete_task(int(m.group(1)))
        else:
            m = re.match(r"^/api/schedules/(\d+)$", path)
            if m:
                self._handle_delete_schedule(int(m.group(1)))
            else:
                m = re.match(r"^/api/prompts/(.+)$", path)
                if m:
                    self._handle_delete_prompt(m.group(1))
                else:
                    self._send_json({"error": "Not Found"}, 404)

    # ── API 実装 ───────────────────────────────────────────────
    def _handle_get_tasks(self):
        conn = get_db(self.db_path)
        try:
            rows = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
            self._send_json(rows_to_dicts(rows))
        finally:
            conn.close()

    def _handle_get_stats(self):
        conn = get_db(self.db_path)
        try:
            rows = conn.execute("SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status").fetchall()
            stats = {r["status"]: r["cnt"] for r in rows}
            total = sum(stats.values())
            completed = stats.get("completed", 0)
            rate = round(completed / total * 100, 1) if total > 0 else 0
            self._send_json({
                "total": total,
                "completed": completed,
                "completion_rate": rate,
                "by_status": stats,
            })
        finally:
            conn.close()

    def _handle_create_task(self):
        data = self._read_body()
        required = ["task_name", "task_type"]
        for key in required:
            if key not in data or not data[key]:
                self._send_json({"error": f"{key} is required"}, 400)
                return
        conn = get_db(self.db_path)
        try:
            cur = conn.execute(
                "INSERT INTO tasks (task_name, task_type, priority, status, input, model, timeout_seconds, max_turns, allowed_tools, mcp_config, work_dir) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    data["task_name"],
                    data.get("task_type", "research"),
                    data.get("priority", "medium"),
                    data.get("status", "pending"),
                    data.get("input", ""),
                    data.get("model") or None,
                    data.get("timeout_seconds") or None,
                    data.get("max_turns") or None,
                    data.get("allowed_tools") or None,
                    data.get("mcp_config") or None,
                    data.get("work_dir") or None,
                ),
            )
            conn.commit()
            task = conn.execute("SELECT * FROM tasks WHERE id = ?", (cur.lastrowid,)).fetchone()
            self._send_json(dict(task), 201)
        except sqlite3.IntegrityError as e:
            self._send_json({"error": str(e)}, 400)
        finally:
            conn.close()

    def _handle_update_task(self, task_id: int):
        data = self._read_body()
        if not data:
            self._send_json({"error": "No data"}, 400)
            return
        allowed = {"task_name", "task_type", "priority", "status", "input", "result", "assigned_session_id", "started_at", "completed_at", "model", "timeout_seconds", "max_turns", "allowed_tools", "mcp_config", "work_dir"}
        updates = {k: v for k, v in data.items() if k in allowed}
        if not updates:
            self._send_json({"error": "No valid fields"}, 400)
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [task_id]
        conn = get_db(self.db_path)
        try:
            conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", values)
            conn.commit()
            task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if task:
                self._send_json(dict(task))
            else:
                self._send_json({"error": "Not Found"}, 404)
        finally:
            conn.close()

    def _handle_delete_task(self, task_id: int):
        conn = get_db(self.db_path)
        try:
            cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()
            if cur.rowcount:
                self._send_json({"deleted": task_id})
            else:
                self._send_json({"error": "Not Found"}, 404)
        finally:
            conn.close()

    # ── Schedule API ───────────────────────────────────────────────
    def _handle_get_schedules(self):
        conn = get_db(self.db_path)
        try:
            rows = conn.execute("SELECT * FROM schedules ORDER BY id").fetchall()
            self._send_json(rows_to_dicts(rows))
        except Exception:
            self._send_json([])
        finally:
            conn.close()

    def _handle_get_schedule_detail(self, schedule_id: int):
        conn = get_db(self.db_path)
        try:
            row = conn.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
            if row:
                self._send_json(dict(row))
            else:
                self._send_json({"error": "Not Found"}, 404)
        finally:
            conn.close()

    def _handle_create_schedule(self):
        data = self._read_body()
        for key in ["name", "cron_expr"]:
            if key not in data or not data[key]:
                self._send_json({"error": f"{key} is required"}, 400)
                return
        # cron式バリデーション: next_run_atを計算
        import subprocess
        try:
            result = subprocess.run(
                ["python3", CRON_NEXT_SCRIPT, data["cron_expr"]],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                self._send_json({"error": f"Invalid cron expression: {result.stderr.strip()}"}, 400)
                return
            next_run = result.stdout.strip()
        except Exception as e:
            self._send_json({"error": f"cron parse error: {str(e)}"}, 400)
            return

        conn = get_db(self.db_path)
        try:
            cur = conn.execute(
                """INSERT INTO schedules (name, description, task_type, priority, cron_expr,
                   backend, model, prompt, prompt_file, work_dir, mcp_config, allowed_tools,
                   timeout_seconds, max_turns, max_consecutive_failures, session_persistent, next_run_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    data["name"],
                    data.get("description", ""),
                    data.get("task_type", "research"),
                    data.get("priority", "medium"),
                    data["cron_expr"],
                    data.get("backend", "claude"),
                    data.get("model", "sonnet"),
                    data.get("prompt", ""),
                    data.get("prompt_file", ""),
                    data.get("work_dir", ""),
                    data.get("mcp_config", ""),
                    data.get("allowed_tools", ""),
                    data.get("timeout_seconds", 300),
                    data.get("max_turns", 30),
                    data.get("max_consecutive_failures", 3),
                    data.get("session_persistent", 0),
                    next_run,
                ),
            )
            conn.commit()
            schedule = conn.execute("SELECT * FROM schedules WHERE id = ?", (cur.lastrowid,)).fetchone()
            self._send_json(dict(schedule), 201)
        except sqlite3.IntegrityError as e:
            self._send_json({"error": str(e)}, 400)
        finally:
            conn.close()

    def _handle_update_schedule(self, schedule_id: int):
        data = self._read_body()
        if not data:
            self._send_json({"error": "No data"}, 400)
            return
        allowed = {
            "name", "description", "task_type", "priority", "cron_expr", "enabled",
            "backend", "model", "prompt", "prompt_file", "work_dir", "mcp_config",
            "allowed_tools", "timeout_seconds", "max_turns", "max_consecutive_failures",
            "session_persistent", "consecutive_failures",
        }
        updates = {k: v for k, v in data.items() if k in allowed}
        if not updates:
            self._send_json({"error": "No valid fields"}, 400)
            return

        # enabled=1に変更する場合、next_run_atを再計算
        if updates.get("enabled") == 1:
            conn = get_db(self.db_path)
            try:
                row = conn.execute("SELECT cron_expr FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
                if row:
                    import subprocess
                    try:
                        result = subprocess.run(
                            ["python3", CRON_NEXT_SCRIPT, row["cron_expr"]],
                            capture_output=True, text=True, timeout=5
                        )
                        if result.returncode == 0:
                            updates["next_run_at"] = result.stdout.strip()
                            updates["consecutive_failures"] = 0
                    except Exception:
                        pass
            finally:
                conn.close()

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [schedule_id]
        conn = get_db(self.db_path)
        try:
            conn.execute(f"UPDATE schedules SET {set_clause} WHERE id = ?", values)
            conn.commit()
            schedule = conn.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
            if schedule:
                self._send_json(dict(schedule))
            else:
                self._send_json({"error": "Not Found"}, 404)
        finally:
            conn.close()

    def _handle_delete_schedule(self, schedule_id: int):
        conn = get_db(self.db_path)
        try:
            cur = conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
            conn.commit()
            if cur.rowcount:
                self._send_json({"deleted": schedule_id})
            else:
                self._send_json({"error": "Not Found"}, 404)
        finally:
            conn.close()

    def _handle_trigger_schedule(self, schedule_id: int):
        conn = get_db(self.db_path)
        try:
            row = conn.execute("SELECT id FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
            if not row:
                self._send_json({"error": "Not Found"}, 404)
                return
            from datetime import datetime
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("UPDATE schedules SET next_run_at = ?, enabled = 1 WHERE id = ?", (now, schedule_id))
            conn.commit()
            self._send_json({"triggered": schedule_id, "next_run_at": now})
        finally:
            conn.close()

    # ── Prompts API ────────────────────────────────────────────────
    def _safe_prompt_name(self, name: str) -> str | None:
        """ファイル名バリデーション。不正ならNone"""
        name = os.path.basename(name)
        if not name.endswith(".txt"):
            name += ".txt"
        if not re.match(r"^[a-zA-Z0-9_\-]+\.txt$", name):
            return None
        return name

    def _handle_get_prompts(self):
        os.makedirs(PROMPTS_DIR, exist_ok=True)
        result = []
        for f in sorted(os.listdir(PROMPTS_DIR)):
            if not f.endswith(".txt"):
                continue
            fpath = os.path.join(PROMPTS_DIR, f)
            try:
                stat = os.stat(fpath)
                with open(fpath, "r", encoding="utf-8") as fh:
                    content = fh.read()
                from datetime import datetime
                mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                result.append({"name": f, "size": stat.st_size, "modified": mtime, "content": content})
            except Exception:
                result.append({"name": f, "size": 0, "modified": "", "content": ""})
        self._send_json(result)

    def _handle_get_prompt(self, name: str):
        safe = self._safe_prompt_name(name)
        if not safe:
            self._send_json({"error": "Invalid name"}, 400)
            return
        fpath = os.path.join(PROMPTS_DIR, safe)
        if not os.path.isfile(fpath):
            self._send_json({"error": "Not Found"}, 404)
            return
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        self._send_json({"name": safe, "content": content})

    def _handle_save_prompt(self, existing_name: str | None = None):
        data = self._read_body()
        name = data.get("name", "")
        content = data.get("content", "")
        safe = self._safe_prompt_name(existing_name or name)
        if not safe:
            self._send_json({"error": "Invalid name. Use alphanumeric, hyphens, underscores only."}, 400)
            return
        os.makedirs(PROMPTS_DIR, exist_ok=True)
        fpath = os.path.join(PROMPTS_DIR, safe)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        self._send_json({"name": safe, "saved": True}, 201)

    def _handle_delete_prompt(self, name: str):
        safe = self._safe_prompt_name(name)
        if not safe:
            self._send_json({"error": "Invalid name"}, 400)
            return
        fpath = os.path.join(PROMPTS_DIR, safe)
        if not os.path.isfile(fpath):
            self._send_json({"error": "Not Found"}, 404)
            return
        os.remove(fpath)
        self._send_json({"deleted": safe})

    # ── ログ API ──────────────────────────────────────────────────
    def _handle_get_logs(self, qs):
        conn = get_logs_db()
        try:
            where = []
            params = []
            runner_type = qs.get("runner_type", [None])[0]
            if runner_type:
                where.append("runner_type = ?")
                params.append(runner_type)
            status = qs.get("status", [None])[0]
            if status:
                where.append("status = ?")
                params.append(status)
            limit = int(qs.get("limit", [50])[0])
            offset = int(qs.get("offset", [0])[0])
            sql = "SELECT id, timestamp, runner_type, task_source, task_type, task_name, status, cost_usd, duration_seconds FROM execution_logs"
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            rows = conn.execute(sql, params).fetchall()
            self._send_json(rows_to_dicts(rows))
        finally:
            conn.close()

    def _handle_get_logs_stats(self):
        conn = get_logs_db()
        try:
            # 総実行回数
            total = conn.execute("SELECT COUNT(*) as cnt FROM execution_logs").fetchone()["cnt"]
            # 成功数
            success = conn.execute("SELECT COUNT(*) as cnt FROM execution_logs WHERE status = 'success'").fetchone()["cnt"]
            success_rate = round(success / total * 100, 1) if total > 0 else 0
            # 合計コスト
            total_cost = conn.execute("SELECT COALESCE(SUM(cost_usd), 0) as s FROM execution_logs").fetchone()["s"]
            # 日別コスト（直近14日）
            # timestamp形式がISO8601（例: 2026-03-12T00:37:46+0900）のため、先頭10文字で日付抽出
            daily = conn.execute(
                "SELECT substr(timestamp, 1, 10) as date, SUM(cost_usd) as cost FROM execution_logs "
                "WHERE date IS NOT NULL "
                "GROUP BY substr(timestamp, 1, 10) ORDER BY date DESC LIMIT 14"
            ).fetchall()
            daily = list(reversed(rows_to_dicts(daily)))
            self._send_json({
                "total_runs": total,
                "success_rate": success_rate,
                "total_cost": total_cost,
                "daily_costs": [{"date": d["date"], "cost": d["cost"] or 0} for d in daily],
            })
        finally:
            conn.close()

    def _handle_get_log_detail(self, log_id: int):
        conn = get_logs_db()
        try:
            row = conn.execute("SELECT * FROM execution_logs WHERE id = ?", (log_id,)).fetchone()
            if row:
                self._send_json(dict(row))
            else:
                self._send_json({"error": "Not Found"}, 404)
        finally:
            conn.close()


# ── メイン ─────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Claude Task Runner Kanban Board")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"ポート番号 (default: {DEFAULT_PORT})")
    parser.add_argument("--db", type=str, default=DEFAULT_DB_PATH, help=f"DBファイルパス (default: {DEFAULT_DB_PATH})")
    args = parser.parse_args()

    KanbanHandler.db_path = args.db

    HTTPServer.allow_reuse_address = True
    server = HTTPServer(("0.0.0.0", args.port), KanbanHandler)
    print(f"[kanban] Kanban Board: http://localhost:{args.port}")
    print(f"[kanban] DB: {args.db}")
    print(f"[kanban] Ctrl+C で終了")

    def shutdown(sig, frame):
        print("\n[kanban] シャットダウン中...")
        # shutdown()はserve_forever()と同じスレッドから呼ぶとデッドロックするため別スレッドで実行
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("[kanban] 停止しました")


if __name__ == "__main__":
    main()
