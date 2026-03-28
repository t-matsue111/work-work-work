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
<title>WORK WORK WORK - Kanban</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#131313;--surface-lowest:#0e0e0e;--surface-low:#1c1b1b;--surface:#201f1f;--surface-highest:#353534;
  --primary:#ff5717;--primary-lit:#ffb59e;--secondary:#c3f400;--error:#e74c3c;--info:#3a86ff;
  --text:#e6e1e5;--text-secondary:#958f94;--ghost:rgba(92,64,55,.2);
  --font-display:'Space Grotesk',sans-serif;--font-body:'Inter',sans-serif;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--font-body);background:var(--bg);color:var(--text);min-height:100vh}
/* ── Header ── */
header{background:var(--surface-highest);padding:14px 24px;display:flex;align-items:center;gap:16px}
header h1{font-family:var(--font-display);font-size:1.3rem;font-weight:700;color:var(--primary);letter-spacing:0.04em;text-transform:uppercase}
header nav{display:flex;gap:6px;margin-left:16px}
header nav a{font-family:var(--font-display);color:var(--text-secondary);background:transparent;border:1px solid var(--ghost);padding:7px 16px;border-radius:0;font-size:.8rem;font-weight:600;text-decoration:none;text-transform:uppercase;letter-spacing:0.05em;transition:background .2s,color .2s}
header nav a:hover{background:var(--surface);color:var(--text)}
header nav a.active{background:var(--primary);color:#fff;border-color:var(--primary)}
header .stats{font-family:var(--font-display);font-size:.85rem;color:var(--text-secondary);margin-left:auto;margin-right:8px}
header .stats span{color:var(--primary-lit);font-weight:700;margin:0 4px}
.btn-add{font-family:var(--font-display);background:linear-gradient(135deg,var(--primary-lit),var(--primary));color:#fff;border:none;padding:8px 20px;border-radius:0;font-size:.85rem;cursor:pointer;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;transition:opacity .2s}
.btn-add:hover{opacity:.85}
/* ── Board ── */
.board{display:flex;gap:12px;padding:20px 16px;overflow-x:auto;min-height:calc(100vh - 60px);align-items:flex-start}
.column{min-width:270px;max-width:320px;flex:1 0 270px;background:var(--surface-lowest);border-radius:0;display:flex;flex-direction:column;max-height:calc(100vh - 90px)}
.column-header{padding:12px 16px;font-family:var(--font-display);font-weight:700;font-size:.8rem;text-transform:uppercase;letter-spacing:0.05em;display:flex;justify-content:space-between;align-items:center;background:var(--surface-low)}
.column-header .count{font-family:var(--font-display);background:rgba(255,255,255,.06);padding:2px 10px;border-radius:0;font-size:.75rem;font-weight:600}
.col-pending .column-header{color:var(--primary-lit);border-left:4px solid var(--primary)}
.col-in_progress .column-header{color:var(--info);border-left:4px solid var(--info)}
.col-completed .column-header{color:var(--secondary);border-left:4px solid var(--secondary)}
.col-error .column-header{color:var(--error);border-left:4px solid var(--error)}
.col-review .column-header{color:var(--primary-lit);border-left:4px solid var(--primary-lit)}
.column-body{padding:8px;overflow-y:auto;flex:1;min-height:80px}
.column-body.drag-over{background:rgba(255,87,23,.06)}
/* ── Cards ── */
.card{background:var(--surface-low);border-left:4px solid var(--text-secondary);border-radius:0;padding:12px 12px 12px 12px;margin-bottom:6px;cursor:grab;transition:transform .15s,box-shadow .15s}
.card:hover{transform:translateY(-1px);box-shadow:0 8px 24px rgba(0,0,0,.04)}
.card.dragging{opacity:.5;transform:rotate(1deg)}
.card[data-status="pending"]{border-left-color:var(--primary)}
.card[data-status="in_progress"]{border-left-color:var(--info)}
.card[data-status="completed"]{border-left-color:var(--secondary)}
.card[data-status="error"]{border-left-color:var(--error)}
.card[data-status="needs_review"],.card[data-status="needs_clarification"]{border-left-color:var(--primary-lit)}
.card-title{font-family:var(--font-body);font-weight:600;font-size:.85rem;margin-bottom:6px;line-height:1.35;color:var(--text)}
.card-meta{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.badge{padding:2px 8px;border-radius:0;font-family:var(--font-display);font-size:.65rem;font-weight:600;text-transform:uppercase;letter-spacing:0.04em}
.badge-research{background:rgba(58,134,255,.15);color:var(--info)}
.badge-planning{background:rgba(255,181,158,.12);color:var(--primary-lit)}
.badge-code_review{background:rgba(195,244,0,.1);color:var(--secondary)}
.badge-sentry_analysis{background:rgba(168,85,247,.12);color:#a855f7}
.badge-email_check{background:rgba(255,87,23,.1);color:var(--primary)}
.priority-dot{width:8px;height:8px;border-radius:0;display:inline-block}
.priority-high{background:var(--error)}
.priority-medium{background:var(--primary)}
.priority-low{background:var(--text-secondary)}
.card-time{font-family:var(--font-display);font-size:.65rem;color:var(--text-secondary);margin-top:6px;letter-spacing:0.02em}
/* ── Modal shared ── */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.65);display:none;align-items:center;justify-content:center;z-index:100}
.modal-overlay.active{display:flex}
.modal{background:var(--surface);border-radius:0;padding:28px;width:90%;max-width:580px;max-height:85vh;overflow-y:auto;box-shadow:0 12px 40px rgba(0,0,0,.3)}
.modal h2{font-family:var(--font-display);margin-bottom:20px;font-size:1.1rem;color:var(--primary-lit);text-transform:uppercase;letter-spacing:0.04em}
.modal label{display:block;font-family:var(--font-display);font-size:.75rem;color:var(--text-secondary);margin-bottom:4px;margin-top:14px;text-transform:uppercase;letter-spacing:0.05em}
.modal input,.modal select,.modal textarea{width:100%;padding:10px 12px;border-radius:0;border:none;border-bottom:2px solid var(--text-secondary);background:var(--surface-low);color:var(--text);font-family:var(--font-body);font-size:.88rem;transition:border-color .2s}
.modal input:focus,.modal select:focus,.modal textarea:focus{outline:none;border-bottom-color:var(--secondary)}
.modal textarea{min-height:100px;resize:vertical}
.modal-actions{display:flex;gap:12px;margin-top:24px;justify-content:flex-end}
.modal-actions button{font-family:var(--font-display);padding:9px 22px;border-radius:0;border:none;font-size:.85rem;cursor:pointer;font-weight:600;text-transform:uppercase;letter-spacing:0.04em}
.btn-primary{background:linear-gradient(135deg,var(--primary-lit),var(--primary));color:#fff}
.btn-primary:hover{opacity:.85}
.btn-cancel{background:transparent;color:var(--text-secondary);border:1px solid var(--ghost) !important}
.btn-cancel:hover{background:var(--surface-low);color:var(--text)}
.btn-delete{background:var(--error);color:#fff}
.btn-delete:hover{opacity:.85}
.detail-field{margin-bottom:14px}
.detail-field .label{font-family:var(--font-display);font-size:.7rem;color:var(--text-secondary);margin-bottom:4px;text-transform:uppercase;letter-spacing:0.05em}
.detail-field .value{background:var(--surface-lowest);padding:10px 12px;border-radius:0;font-size:.84rem;white-space:pre-wrap;word-break:break-word;max-height:200px;overflow-y:auto;border-left:2px solid var(--ghost)}
/* ── Advanced settings ── */
details{margin-top:16px;background:var(--surface-low);padding:0 14px;border:none}
details summary{cursor:pointer;padding:12px 0;color:var(--text-secondary);font-family:var(--font-display);font-size:.8rem;font-weight:600;text-transform:uppercase;letter-spacing:0.04em}
details .adv-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
details .adv-grid label{font-family:var(--font-display);font-size:.7rem;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.05em}
details .adv-grid input,details .adv-grid select{font-size:.84rem}
@media(max-width:768px){.board{flex-direction:column;align-items:stretch}.column{min-width:auto;max-width:none;max-height:none}}
</style>
</head>
<body>
<header>
  <h1>WORK WORK WORK</h1>
  <nav>
    <a href="/" class="active">Kanban</a>
    <a href="/tasks">Tasks</a>
    <a href="/logs">Logs</a>
    <a href="/schedules">Schedules</a>
    <a href="/prompts">Prompts</a>
  </nav>
  <div class="stats" id="stats"></div>
  <button class="btn-add" onclick="openAddModal()">+ Add Task</button>
</header>
<div class="board" id="board">
  <div class="column col-pending" data-status="pending">
    <div class="column-header">PENDING <span class="count" id="cnt-pending">0</span></div>
    <div class="column-body" id="col-pending"></div>
  </div>
  <div class="column col-in_progress" data-status="in_progress">
    <div class="column-header">IN PROGRESS <span class="count" id="cnt-in_progress">0</span></div>
    <div class="column-body" id="col-in_progress"></div>
  </div>
  <div class="column col-completed" data-status="completed">
    <div class="column-header">DONE <span class="count" id="cnt-completed">0</span></div>
    <div class="column-body" id="col-completed"></div>
  </div>
  <div class="column col-error" data-status="error">
    <div class="column-header">ERROR <span class="count" id="cnt-error">0</span></div>
    <div class="column-body" id="col-error"></div>
  </div>
  <div class="column col-review" data-status="needs_review">
    <div class="column-header">REVIEW <span class="count" id="cnt-review">0</span></div>
    <div class="column-body" id="col-review"></div>
  </div>
</div>

<!-- 追加モーダル -->
<div class="modal-overlay" id="addModal">
  <div class="modal">
    <h2>Add Task</h2>
    <label>Task Name</label>
    <input type="text" id="addName" placeholder="タスク名を入力">
    <label>Label</label>
    <input type="text" id="addType" list="kanbanTypeList" placeholder="例: research, email_check">
    <datalist id="kanbanTypeList">
      <option value="research">技術調査・コードベース分析</option>
      <option value="planning">要件→実装計画作成</option>
      <option value="code_review">PRレビューコメント投稿</option>
      <option value="sentry_analysis">Sentryイシュー原因調査</option>
      <option value="email_check">メール確認・要約</option>
    </datalist>
    <label>Priority</label>
    <select id="addPriority">
      <option value="medium">medium</option>
      <option value="high">high</option>
      <option value="low">low</option>
    </select>
    <label>Input</label>
    <textarea id="addInput" placeholder="タスクの詳細情報"></textarea>
    <details>
      <summary>Advanced Settings</summary>
      <div class="adv-grid">
        <div><label>Model</label>
        <select id="addTaskModel">
          <option value="">Default (sonnet)</option>
          <option value="opus">opus</option>
          <option value="haiku">haiku</option>
        </select></div>
        <div><label>MCP Config</label>
        <input type="text" id="addTaskMcp" list="kanbanMcpList" placeholder="None">
        <datalist id="kanbanMcpList">
          <option value="mcp-config-email.json">Google Workspace</option>
          <option value="mcp-config-sentry.json">Sentry</option>
          <option value="sources/notion/mcp-config.json">Notion</option>
        </datalist></div>
        <div><label>Timeout (sec)</label>
        <input type="number" id="addTaskTimeout" placeholder="300"></div>
        <div><label>Max Turns</label>
        <input type="number" id="addTaskMaxTurns" placeholder="30"></div>
      </div>
      <label>Work Directory</label>
      <input type="text" id="addTaskWorkDir" placeholder="省略時はこのプロジェクト" style="margin-bottom:12px">
      <label>Allowed Tools</label>
      <input type="text" id="addTaskTools" placeholder="省略時はソースのデフォルト" style="margin-bottom:14px">
    </details>
    <div class="modal-actions">
      <button class="btn-cancel" onclick="closeModal('addModal')">Cancel</button>
      <button class="btn-primary" onclick="submitAdd()">Add</button>
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
    <div class="detail-field"><div class="label">Created</div><div class="value" id="detailCreated"></div></div>
    <div class="detail-field"><div class="label">Updated</div><div class="value" id="detailUpdated"></div></div>
    <div class="modal-actions">
      <button class="btn-delete" id="detailDeleteBtn">Delete</button>
      <button class="btn-sm" id="detailArchiveBtn" style="background:var(--text-secondary);color:#fff;margin-right:auto;display:none">Archive</button>
      <button class="btn-cancel" onclick="closeModal('detailModal')">Close</button>
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
  div.dataset.status = task.status;
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
  document.getElementById('stats').innerHTML = `TOTAL <span>${s.total}</span> DONE <span>${s.completion_rate}%</span>`;
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
    <span style="font-family:var(--font-display);font-size:.75rem;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.04em">Status: ${task.status}</span>`;
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
  const archBtn = document.getElementById('detailArchiveBtn');
  if (task.status === 'completed' || task.status === 'error') {
    archBtn.style.display = 'inline-block';
    archBtn.onclick = async () => {
      await fetch('/api/tasks/' + task.id, { method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify({archived: 1}) });
      closeModal('detailModal');
      loadTasks();
    };
  } else {
    archBtn.style.display = 'none';
  }
  document.getElementById('detailModal').classList.add('active');
}

// 初期読み込み + 自動リフレッシュ
loadTasks();
setInterval(loadTasks, 30000);
</script>
</body>
</html>"""


# ── Tasks一覧 HTML テンプレート ────────────────────────────────────
TASKS_HTML = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>WORK WORK WORK - Tasks</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#131313;--surface-lowest:#0e0e0e;--surface-low:#1c1b1b;--surface:#201f1f;--surface-highest:#353534;
  --primary:#ff5717;--primary-lit:#ffb59e;--secondary:#c3f400;--error:#e74c3c;--info:#3a86ff;
  --text:#e6e1e5;--text-secondary:#958f94;--ghost:rgba(92,64,55,.2);
  --font-display:'Space Grotesk',sans-serif;--font-body:'Inter',sans-serif;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--font-body);background:var(--bg);color:var(--text);min-height:100vh}
header{background:var(--surface-highest);padding:14px 24px;display:flex;align-items:center;gap:16px}
header h1{font-family:var(--font-display);font-size:1.3rem;font-weight:700;color:var(--primary);letter-spacing:0.04em;text-transform:uppercase}
header nav{display:flex;gap:6px;margin-left:16px}
header nav a{font-family:var(--font-display);color:var(--text-secondary);background:transparent;border:1px solid var(--ghost);padding:7px 16px;border-radius:0;font-size:.8rem;font-weight:600;text-decoration:none;text-transform:uppercase;letter-spacing:0.05em;transition:background .2s,color .2s}
header nav a:hover{background:var(--surface);color:var(--text)}
header nav a.active{background:var(--primary);color:#fff;border-color:var(--primary)}
.container{padding:20px 24px;max-width:1400px;margin:0 auto}
.toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}
.toolbar h2{font-family:var(--font-display);font-size:.9rem;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.06em}
.filters{display:flex;gap:12px;align-items:center}
.filters select{font-family:var(--font-body);padding:6px 10px;border:none;border-bottom:2px solid var(--text-secondary);background:var(--surface-low);color:var(--text);font-size:.82rem;border-radius:0}
.filters select:focus{outline:none;border-bottom-color:var(--secondary)}
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:separate;border-spacing:0 2px;font-size:.84rem}
thead th{background:var(--surface-highest);padding:11px 14px;text-align:left;font-family:var(--font-display);font-weight:600;font-size:.7rem;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.06em;position:sticky;top:0}
tbody tr{transition:background .15s}
tbody tr:nth-child(even){background:var(--surface-low)}
tbody tr:nth-child(odd){background:var(--bg)}
tbody tr:hover{background:var(--surface)}
tbody td{padding:10px 14px}
.status-badge{padding:3px 10px;border-radius:0;font-family:var(--font-display);font-size:.7rem;font-weight:600;display:inline-block;text-transform:uppercase;letter-spacing:0.04em}
.status-pending{background:rgba(255,87,23,.1);color:var(--primary)}
.status-in_progress{background:rgba(58,134,255,.12);color:var(--info)}
.status-completed{background:rgba(195,244,0,.1);color:var(--secondary)}
.status-error{background:rgba(231,76,60,.12);color:var(--error)}
.status-needs_review,.status-needs_clarification{background:rgba(255,181,158,.1);color:var(--primary-lit)}
.archived-badge{font-family:var(--font-display);font-size:.6rem;background:var(--surface-highest);color:var(--text-secondary);padding:2px 6px;text-transform:uppercase;letter-spacing:0.04em;margin-left:6px}
.btn-sm{font-family:var(--font-display);padding:5px 12px;border-radius:0;border:none;font-size:.7rem;cursor:pointer;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;transition:opacity .2s;background:var(--text-secondary);color:#fff}
.btn-sm:hover{opacity:.8}
.pagination{display:flex;gap:8px;margin-top:16px;align-items:center}
.pagination button{font-family:var(--font-display);padding:6px 14px;border:1px solid var(--ghost);background:transparent;color:var(--text-secondary);cursor:pointer;font-size:.8rem;text-transform:uppercase;border-radius:0}
.pagination button:hover{background:var(--surface-low);color:var(--text)}
.pagination button:disabled{opacity:.4;cursor:default}
.pagination span{font-family:var(--font-display);font-size:.8rem;color:var(--text-secondary)}
</style>
</head>
<body>
<header>
  <h1>WORK WORK WORK</h1>
  <nav>
    <a href="/">Kanban</a>
    <a href="/tasks" class="active">Tasks</a>
    <a href="/tasks">Tasks</a>
    <a href="/logs">Logs</a>
    <a href="/schedules">Schedules</a>
    <a href="/prompts">Prompts</a>
  </nav>
</header>
<div class="container">
  <div class="toolbar">
    <h2>All Tasks</h2>
    <div class="filters">
      <select id="filterStatus" onchange="loadTasks()">
        <option value="">All Status</option>
        <option value="pending">pending</option>
        <option value="in_progress">in_progress</option>
        <option value="completed">completed</option>
        <option value="error">error</option>
        <option value="needs_review">needs_review</option>
        <option value="needs_clarification">needs_clarification</option>
      </select>
      <select id="filterArchived" onchange="loadTasks()">
        <option value="active">Active Only</option>
        <option value="archived">Archived Only</option>
        <option value="all">All</option>
      </select>
    </div>
  </div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>ID</th><th>Name</th><th>Label</th><th>Priority</th><th>Status</th><th>Created</th><th>Actions</th>
        </tr>
      </thead>
      <tbody id="taskBody"></tbody>
    </table>
  </div>
  <div class="pagination">
    <button id="prevBtn" onclick="changePage(-1)">&larr; Prev</button>
    <span id="pageInfo"></span>
    <button id="nextBtn" onclick="changePage(1)">Next &rarr;</button>
  </div>
</div>
<script>
const PAGE_SIZE = 50;
let currentOffset = 0;
function esc(s){if(!s)return'';const d=document.createElement('div');d.textContent=s;return d.innerHTML}
async function loadTasks(){
  const status=document.getElementById('filterStatus').value;
  const arch=document.getElementById('filterArchived').value;
  let url='/api/tasks?archived=' + (arch==='all'?'1':arch==='archived'?'1':'0');
  const res=await fetch(url);
  let tasks=await res.json();
  if(status) tasks=tasks.filter(t=>t.status===status);
  if(arch==='archived') tasks=tasks.filter(t=>t.archived===1);
  else if(arch==='active') tasks=tasks.filter(t=>!t.archived);
  const page=tasks.slice(currentOffset,currentOffset+PAGE_SIZE);
  const tbody=document.getElementById('taskBody');
  tbody.innerHTML='';
  page.forEach(t=>{
    const tr=document.createElement('tr');
    const archBadge=t.archived?'<span class="archived-badge">archived</span>':'';
    tr.innerHTML=`
      <td style="font-family:var(--font-display)">${t.id}</td>
      <td>${esc(t.task_name)}${archBadge}</td>
      <td>${esc(t.task_type)}</td>
      <td>${esc(t.priority)}</td>
      <td><span class="status-badge status-${t.status}">${t.status}</span></td>
      <td style="font-family:var(--font-display);font-size:.8rem">${esc(t.created_at||'')}</td>
      <td>${t.archived?'<button class="btn-sm" onclick="unarchive('+t.id+')">Restore</button>':t.status==='completed'||t.status==='error'?'<button class="btn-sm" onclick="archive('+t.id+')">Archive</button>':''}</td>`;
    tbody.appendChild(tr);
  });
  document.getElementById('pageInfo').textContent=(currentOffset+1)+' - '+(currentOffset+page.length)+' / '+tasks.length;
  document.getElementById('prevBtn').disabled=currentOffset===0;
  document.getElementById('nextBtn').disabled=currentOffset+PAGE_SIZE>=tasks.length;
}
function changePage(dir){currentOffset=Math.max(0,currentOffset+dir*PAGE_SIZE);loadTasks()}
async function archive(id){
  await fetch('/api/tasks/'+id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({archived:1})});
  loadTasks();
}
async function unarchive(id){
  await fetch('/api/tasks/'+id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({archived:0})});
  loadTasks();
}
loadTasks();
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
<title>WORK WORK WORK - Logs</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#131313;--surface-lowest:#0e0e0e;--surface-low:#1c1b1b;--surface:#201f1f;--surface-highest:#353534;
  --primary:#ff5717;--primary-lit:#ffb59e;--secondary:#c3f400;--error:#e74c3c;--info:#3a86ff;
  --text:#e6e1e5;--text-secondary:#958f94;--ghost:rgba(92,64,55,.2);
  --font-display:'Space Grotesk',sans-serif;--font-body:'Inter',sans-serif;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--font-body);background:var(--bg);color:var(--text);min-height:100vh}
header{background:var(--surface-highest);padding:14px 24px;display:flex;align-items:center;gap:16px}
header h1{font-family:var(--font-display);font-size:1.3rem;font-weight:700;color:var(--primary);letter-spacing:0.04em;text-transform:uppercase}
header nav{display:flex;gap:6px;margin-left:16px}
header nav a{font-family:var(--font-display);color:var(--text-secondary);background:transparent;border:1px solid var(--ghost);padding:7px 16px;border-radius:0;font-size:.8rem;font-weight:600;text-decoration:none;text-transform:uppercase;letter-spacing:0.05em;transition:background .2s,color .2s}
header nav a:hover{background:var(--surface);color:var(--text)}
header nav a.active{background:var(--primary);color:#fff;border-color:var(--primary)}
.container{padding:20px 24px;max-width:1400px;margin:0 auto}
/* ── Stats Bar ── */
.stats-bar{display:flex;gap:16px;margin-bottom:20px;flex-wrap:wrap}
.stat-card{background:var(--surface-low);border-radius:0;padding:16px 24px;min-width:160px;border-left:4px solid var(--primary)}
.stat-card .stat-label{font-family:var(--font-display);font-size:.65rem;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px}
.stat-card .stat-value{font-family:var(--font-display);font-size:1.6rem;font-weight:700;color:var(--primary-lit)}
/* ── Cost Chart ── */
.cost-chart{background:var(--surface-low);border-radius:0;padding:18px;margin-bottom:20px}
.cost-chart h3{font-family:var(--font-display);font-size:.75rem;color:var(--text-secondary);margin-bottom:14px;text-transform:uppercase;letter-spacing:0.06em}
.chart-bars{display:flex;align-items:flex-end;gap:4px;height:80px}
.chart-bar{flex:1;min-width:20px;max-width:40px;background:var(--primary);border-radius:0;position:relative;cursor:default;transition:background .2s}
.chart-bar:hover{background:var(--primary-lit)}
.chart-bar .chart-tip{display:none;position:absolute;bottom:calc(100% + 6px);left:50%;transform:translateX(-50%);background:var(--surface-highest);color:var(--text);padding:6px 10px;border-radius:0;font-family:var(--font-display);font-size:.7rem;white-space:nowrap;z-index:10;box-shadow:0 8px 24px rgba(0,0,0,.15)}
.chart-bar:hover .chart-tip{display:block}
.chart-labels{display:flex;gap:4px;margin-top:6px}
.chart-labels span{flex:1;min-width:20px;max-width:40px;text-align:center;font-family:var(--font-display);font-size:.55rem;color:var(--text-secondary);letter-spacing:0.02em}
/* ── Filters ── */
.filters{display:flex;gap:14px;margin-bottom:18px;flex-wrap:wrap;align-items:center}
.filters select{padding:7px 14px;border-radius:0;border:none;border-bottom:2px solid var(--text-secondary);background:var(--surface-low);color:var(--text);font-family:var(--font-body);font-size:.84rem;transition:border-color .2s}
.filters select:focus{outline:none;border-bottom-color:var(--secondary)}
.filters label{font-family:var(--font-display);font-size:.75rem;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.05em}
/* ── Table ── */
.table-wrap{overflow-x:auto;border-radius:0}
table{width:100%;border-collapse:separate;border-spacing:0 2px;font-size:.84rem}
thead th{background:var(--surface-highest);padding:11px 14px;text-align:left;font-family:var(--font-display);font-weight:600;font-size:.7rem;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.06em;position:sticky;top:0}
tbody tr{cursor:pointer;transition:background .15s}
tbody tr:nth-child(even){background:var(--surface-low)}
tbody tr:nth-child(odd){background:var(--bg)}
tbody tr:hover{background:var(--surface)}
tbody td{padding:10px 14px}
.status-badge{padding:3px 10px;border-radius:0;font-family:var(--font-display);font-size:.7rem;font-weight:600;display:inline-block;text-transform:uppercase;letter-spacing:0.04em}
.status-success{background:rgba(195,244,0,.1);color:var(--secondary)}
.status-error{background:rgba(231,76,60,.12);color:var(--error)}
.status-timeout{background:rgba(255,87,23,.1);color:var(--primary)}
.status-skipped{background:rgba(149,143,148,.1);color:var(--text-secondary)}
.status-unknown{background:rgba(149,143,148,.1);color:var(--text-secondary)}
/* ── Pagination ── */
.pagination{display:flex;gap:8px;margin-top:18px;justify-content:center;align-items:center}
.pagination button{font-family:var(--font-display);padding:7px 16px;border-radius:0;border:1px solid var(--ghost);background:transparent;color:var(--text-secondary);cursor:pointer;font-size:.8rem;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;transition:background .2s,color .2s}
.pagination button:hover{background:var(--surface-low);color:var(--text)}
.pagination button:disabled{opacity:.3;cursor:default}
.pagination span{font-family:var(--font-display);font-size:.8rem;color:var(--text-secondary)}
/* ── Modal ── */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.65);display:none;align-items:center;justify-content:center;z-index:100}
.modal-overlay.active{display:flex}
.modal{background:var(--surface);border-radius:0;padding:28px;width:90%;max-width:720px;max-height:85vh;overflow-y:auto;box-shadow:0 12px 40px rgba(0,0,0,.3)}
.modal h2{font-family:var(--font-display);margin-bottom:20px;font-size:1.1rem;color:var(--primary-lit);text-transform:uppercase;letter-spacing:0.04em}
.detail-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.detail-field{margin-bottom:6px}
.detail-field .label{font-family:var(--font-display);font-size:.65rem;color:var(--text-secondary);margin-bottom:3px;text-transform:uppercase;letter-spacing:0.06em}
.detail-field .value{background:var(--surface-lowest);padding:9px 12px;border-radius:0;font-size:.82rem;white-space:pre-wrap;word-break:break-word;max-height:200px;overflow-y:auto;border-left:2px solid var(--ghost)}
.detail-field.full{grid-column:1/-1}
.modal-actions{display:flex;justify-content:flex-end;margin-top:18px}
.modal-actions button{font-family:var(--font-display);padding:9px 22px;border-radius:0;border:none;font-size:.85rem;cursor:pointer;font-weight:600;background:transparent;color:var(--text-secondary);border:1px solid var(--ghost);text-transform:uppercase;letter-spacing:0.04em;transition:background .2s,color .2s}
.modal-actions button:hover{background:var(--surface-low);color:var(--text)}
</style>
</head>
<body>
<header>
  <h1>WORK WORK WORK</h1>
  <nav>
    <a href="/">Kanban</a>
    <a href="/tasks">Tasks</a>
    <a href="/logs" class="active">Logs</a>
    <a href="/schedules">Schedules</a>
    <a href="/prompts">Prompts</a>
  </nav>
</header>
<div class="container">
  <div class="stats-bar" id="statsBar"></div>
  <div class="cost-chart" id="costChart"><h3>Daily Cost (USD)</h3><div class="chart-bars" id="chartBars"></div><div class="chart-labels" id="chartLabels"></div></div>
  <div class="filters">
    <label>Status
      <select id="filterStatus" onchange="loadLogs()">
        <option value="">All</option>
        <option value="success">success</option>
        <option value="error">error</option>
        <option value="timeout">timeout</option>
        <option value="skipped">skipped</option>
      </select>
    </label>
    <label>Model
      <select id="filterModel" onchange="loadLogs()">
        <option value="">All</option>
        <option value="sonnet">sonnet</option>
        <option value="opus">opus</option>
        <option value="haiku">haiku</option>
      </select>
    </label>
    <label>Schedule
      <select id="filterSchedule" onchange="loadLogs()">
        <option value="">All</option>
        <option value="spot">spot taskのみ</option>
        <option value="schedule">scheduleのみ</option>
      </select>
    </label>
  </div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Timestamp</th><th>Task Name</th><th>Status</th><th>Model</th><th>Cost</th><th>Duration</th><th>Source</th>
        </tr>
      </thead>
      <tbody id="logBody"></tbody>
    </table>
  </div>
  <div class="pagination">
    <button id="prevBtn" onclick="changePage(-1)">PREV</button>
    <span id="pageInfo"></span>
    <button id="nextBtn" onclick="changePage(1)">NEXT</button>
  </div>
</div>

<!-- 詳細モーダル -->
<div class="modal-overlay" id="logDetailModal">
  <div class="modal">
    <h2 id="logDetailTitle"></h2>
    <div class="detail-grid" id="logDetailGrid"></div>
    <div class="modal-actions">
      <button onclick="document.getElementById('logDetailModal').classList.remove('active')">Close</button>
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
    <div class="stat-card"><div class="stat-label">Total Runs</div><div class="stat-value">${s.total_runs}</div></div>
    <div class="stat-card"><div class="stat-label">Success Rate</div><div class="stat-value">${s.success_rate}%</div></div>
    <div class="stat-card"><div class="stat-label">Total Cost</div><div class="stat-value">${fmtCost(s.total_cost)}</div></div>
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
  const status = document.getElementById('filterStatus').value;
  const model = document.getElementById('filterModel').value;
  const schedule = document.getElementById('filterSchedule').value;
  let url = `/api/logs?limit=${PAGE_SIZE}&offset=${currentOffset}`;
  if (status) url += `&status=${status}`;
  if (model) url += `&model=${model}`;
  if (schedule) url += `&schedule=${schedule}`;
  const res = await fetch(url);
  const logs = await res.json();
  const tbody = document.getElementById('logBody');
  tbody.innerHTML = '';
  logs.forEach(log => {
    const tr = document.createElement('tr');
    const schedBadge = log.schedule_id ? '<span style="font-family:var(--font-display);font-size:.6rem;background:rgba(58,134,255,.1);color:var(--info);padding:2px 6px;border-radius:0;margin-left:6px;text-transform:uppercase;letter-spacing:0.04em">schedule</span>' : '';
    tr.innerHTML = `
      <td>${esc(log.timestamp)}</td>
      <td>${esc(log.task_name || '-')}${schedBadge}</td>
      <td><span class="${statusClass(log.status)}">${log.status}</span></td>
      <td>${esc(log.model || '-')}</td>
      <td style="font-family:var(--font-display)">${fmtCost(log.cost_usd)}</td>
      <td style="font-family:var(--font-display)">${fmtDuration(log.duration_seconds)}</td>
      <td>${esc(log.task_source || '-')}</td>`;
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
    ['Timestamp', log.timestamp], ['Status', log.status],
    ['Model', log.model], ['Source', log.task_source],
    ['Type', log.task_type], ['Schedule ID', log.schedule_id || '-'],
    ['Cost', fmtCost(log.cost_usd)], ['Duration', fmtDuration(log.duration_seconds)],
    ['Input Tokens', log.input_tokens], ['Output Tokens', log.output_tokens],
    ['Session ID', log.session_id], ['Runner', log.runner_type],
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
<title>WORK WORK WORK - Schedules</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#131313;--surface-lowest:#0e0e0e;--surface-low:#1c1b1b;--surface:#201f1f;--surface-highest:#353534;
  --primary:#ff5717;--primary-lit:#ffb59e;--secondary:#c3f400;--error:#e74c3c;--info:#3a86ff;
  --text:#e6e1e5;--text-secondary:#958f94;--ghost:rgba(92,64,55,.2);
  --font-display:'Space Grotesk',sans-serif;--font-body:'Inter',sans-serif;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--font-body);background:var(--bg);color:var(--text);min-height:100vh}
header{background:var(--surface-highest);padding:14px 24px;display:flex;align-items:center;gap:16px}
header h1{font-family:var(--font-display);font-size:1.3rem;font-weight:700;color:var(--primary);letter-spacing:0.04em;text-transform:uppercase}
header nav{display:flex;gap:6px;margin-left:16px}
header nav a{font-family:var(--font-display);color:var(--text-secondary);background:transparent;border:1px solid var(--ghost);padding:7px 16px;border-radius:0;font-size:.8rem;font-weight:600;text-decoration:none;text-transform:uppercase;letter-spacing:0.05em;transition:background .2s,color .2s}
header nav a:hover{background:var(--surface);color:var(--text)}
header nav a.active{background:var(--primary);color:#fff;border-color:var(--primary)}
.container{padding:20px 24px;max-width:1400px;margin:0 auto}
.toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}
.toolbar h2{font-family:var(--font-display);font-size:.9rem;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.06em}
.btn-add{font-family:var(--font-display);background:linear-gradient(135deg,var(--primary-lit),var(--primary));color:#fff;border:none;padding:8px 20px;border-radius:0;font-size:.85rem;cursor:pointer;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;transition:opacity .2s}
.btn-add:hover{opacity:.85}
/* ── Table ── */
.table-wrap{overflow-x:auto;border-radius:0}
table{width:100%;border-collapse:separate;border-spacing:0 2px;font-size:.84rem}
thead th{background:var(--surface-highest);padding:11px 14px;text-align:left;font-family:var(--font-display);font-weight:600;font-size:.7rem;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.06em;position:sticky;top:0}
tbody tr{transition:background .15s}
tbody tr:nth-child(even){background:var(--surface-low)}
tbody tr:nth-child(odd){background:var(--bg)}
tbody tr:hover{background:var(--surface)}
tbody td{padding:10px 14px}
.toggle{cursor:pointer;font-size:1.2rem;user-select:none;transition:opacity .2s}
.toggle:hover{opacity:.7}
.btn-sm{font-family:var(--font-display);padding:5px 12px;border-radius:0;border:none;font-size:.7rem;cursor:pointer;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;transition:opacity .2s}
.btn-run{background:var(--info);color:#fff}.btn-run:hover{opacity:.8}
.btn-del{background:var(--error);color:#fff}.btn-del:hover{opacity:.8}
.status-badge{padding:3px 10px;border-radius:0;font-family:var(--font-display);font-size:.7rem;font-weight:600;display:inline-block;text-transform:uppercase;letter-spacing:0.04em}
.status-success{background:rgba(195,244,0,.1);color:var(--secondary)}
.status-error{background:rgba(231,76,60,.12);color:var(--error)}
.status-timeout{background:rgba(255,87,23,.1);color:var(--primary)}
/* ── Modal shared ── */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.65);display:none;align-items:center;justify-content:center;z-index:100}
.modal-overlay.active{display:flex}
.modal{background:var(--surface);border-radius:0;padding:28px;width:90%;max-width:660px;max-height:85vh;overflow-y:auto;box-shadow:0 12px 40px rgba(0,0,0,.3)}
.modal h2{font-family:var(--font-display);margin-bottom:20px;font-size:1.1rem;color:var(--primary-lit);text-transform:uppercase;letter-spacing:0.04em}
.modal label{display:block;font-family:var(--font-display);font-size:.75rem;color:var(--text-secondary);margin-bottom:4px;margin-top:14px;text-transform:uppercase;letter-spacing:0.05em}
.modal input,.modal select,.modal textarea{width:100%;padding:10px 12px;border-radius:0;border:none;border-bottom:2px solid var(--text-secondary);background:var(--surface-low);color:var(--text);font-family:var(--font-body);font-size:.88rem;transition:border-color .2s}
.modal input:focus,.modal select:focus,.modal textarea:focus{outline:none;border-bottom-color:var(--secondary)}
.modal textarea{min-height:80px;resize:vertical}
.form-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.modal-actions{display:flex;gap:12px;margin-top:24px;justify-content:flex-end}
.modal-actions button{font-family:var(--font-display);padding:9px 22px;border-radius:0;border:none;font-size:.85rem;cursor:pointer;font-weight:600;text-transform:uppercase;letter-spacing:0.04em}
.btn-primary{background:linear-gradient(135deg,var(--primary-lit),var(--primary));color:#fff}
.btn-primary:hover{opacity:.85}
.btn-cancel{background:transparent;color:var(--text-secondary);border:1px solid var(--ghost) !important}
.btn-cancel:hover{background:var(--surface-low);color:var(--text)}
.detail-field{margin-bottom:8px}
.detail-field .label{font-family:var(--font-display);font-size:.65rem;color:var(--text-secondary);margin-bottom:3px;text-transform:uppercase;letter-spacing:0.06em}
.detail-field .value{background:var(--surface-lowest);padding:9px 12px;border-radius:0;font-size:.82rem;white-space:pre-wrap;word-break:break-word;max-height:200px;overflow-y:auto;border-left:2px solid var(--ghost)}
/* ── Advanced settings ── */
details{margin-top:16px;background:var(--surface-low);padding:0 14px;border:none}
details summary{cursor:pointer;padding:12px 0;color:var(--text-secondary);font-family:var(--font-display);font-size:.8rem;font-weight:600;text-transform:uppercase;letter-spacing:0.04em}
.hint{font-family:var(--font-body);font-size:.65rem;color:var(--text-secondary);margin-top:2px}
.sub-label{font-family:var(--font-body);font-size:.65rem;color:var(--text-secondary)}
</style>
</head>
<body>
<header>
  <h1>WORK WORK WORK</h1>
  <nav>
    <a href="/">Kanban</a>
    <a href="/tasks">Tasks</a>
    <a href="/logs">Logs</a>
    <a href="/schedules" class="active">Schedules</a>
    <a href="/prompts">Prompts</a>
  </nav>
</header>
<div class="container">
  <div class="toolbar">
    <h2>Schedules</h2>
    <button class="btn-add" onclick="openAddModal()">+ Add Schedule</button>
  </div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>ID</th><th>Enabled</th><th>Name</th><th>Cron</th><th>Backend</th><th>Type</th><th>Next Run</th><th>Status</th><th>Failures</th><th>Actions</th>
        </tr>
      </thead>
      <tbody id="scheduleBody"></tbody>
    </table>
  </div>
</div>

<!-- 追加/編集モーダル -->
<div class="modal-overlay" id="addModal">
  <div class="modal">
    <h2 id="modalTitle">Add Schedule</h2>
    <label>Name *</label>
    <input type="text" id="addName" placeholder="例: 朝のメールチェック、週次Sentryレビュー">
    <label>Cron Expression *</label>
    <select id="addCronPreset" onchange="if(this.value)document.getElementById('addCron').value=this.value" style="margin-bottom:6px">
      <option value="">-- Preset --</option>
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
      <div><label>Label <span class="sub-label">分類用</span></label>
      <input type="text" id="addType" list="typeList" placeholder="例: research, email_check">
      <datalist id="typeList">
        <option value="research">技術調査・コードベース分析</option>
        <option value="planning">要件→実装計画作成</option>
        <option value="code_review">PRレビューコメント投稿</option>
        <option value="sentry_analysis">Sentryイシュー原因調査</option>
        <option value="email_check">メール確認・要約</option>
      </datalist></div>
      <div><label>Priority <span class="sub-label">spotタスクより後に処理</span></label>
      <select id="addPriority">
        <option value="medium">medium</option>
        <option value="high">high</option>
        <option value="low">low</option>
      </select></div>
    </div>
    <div class="form-row">
      <div><label>Backend</label>
      <select id="addBackend">
        <option value="claude">claude</option>
        <option value="ollama">ollama</option>
        <option value="codex">codex</option>
      </select></div>
      <div><label>Model</label>
      <select id="addModel">
        <option value="sonnet" selected>sonnet</option>
        <option value="opus">opus</option>
        <option value="haiku">haiku</option>
      </select></div>
    </div>
    <label>Prompt</label>
    <textarea id="addPrompt" placeholder="Claudeへの指示内容を記述&#10;&#10;例: 未読メールを確認し、重要なものを要約してください"></textarea>
    <label>Prompt File <span class="sub-label">（プロンプト欄が空の場合にこのファイルを使用。<a href="/prompts" style="color:var(--primary-lit)">Prompts</a>で管理）</span></label>
    <select id="addPromptFile" style="margin-bottom:2px">
      <option value="">-- なし（上のプロンプト欄を使用）--</option>
    </select>
    <div class="form-row">
      <div><label>MCP Config <span class="sub-label">外部サービス連携</span></label>
      <input type="text" id="addMcpConfig" list="mcpList" placeholder="なし（標準ツールのみ）">
      <datalist id="mcpList">
        <option value="mcp-config-email.json">Google Workspace（Gmail等）</option>
        <option value="mcp-config-sentry.json">Sentry</option>
        <option value="sources/notion/mcp-config.json">Notion</option>
        <option value="/Users/t.matsue/project/manager/truckers_manager/.mcp.json">truckers_manager（Sentry+Notion+Serena）</option>
      </datalist></div>
      <div><label>Allowed Tools <span class="sub-label">Claudeが使えるツール</span></label>
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
    <details>
      <summary>Advanced Settings</summary>
      <div class="form-row">
        <div><label>Timeout (sec) <span class="sub-label">処理の制限時間</span></label>
        <input type="number" id="addTimeout" value="300">
        <div class="hint">300秒=5分。長い調査は600秒程度に</div></div>
        <div><label>Max Turns <span class="sub-label">Claudeの思考回数上限</span></label>
        <input type="number" id="addMaxTurns" value="30">
        <div class="hint">1ターン=1回のツール使用。通常30で十分</div></div>
      </div>
      <div class="form-row">
        <div><label>Max Failures</label>
        <input type="number" id="addMaxFailures" value="3">
        <div class="hint">この回数連続で失敗すると自動で無効化</div></div>
        <div><label>Persistent Session <span class="sub-label">前回の会話を引き継ぐ</span></label>
        <select id="addPersistent"><option value="0">いいえ（毎回新規）</option><option value="1">はい（前回から継続）</option></select>
        <div class="hint">メールチェック等、文脈を保持したい場合にオン</div></div>
      </div>
      <label>Work Directory <span class="sub-label">別プロジェクトのコードを対象にする場合</span></label>
      <input type="text" id="addWorkDir" placeholder="例: /Users/t.matsue/project/my-app（省略時はこのプロジェクト）">
      <div class="hint" style="margin-bottom:14px">Claudeがファイルを読み書きするルートディレクトリ</div>
    </details>
    <div class="modal-actions">
      <button class="btn-sm btn-del" id="modalDeleteBtn" style="margin-right:auto;display:none" onclick="deleteEditing()">DELETE</button>
      <button class="btn-cancel" onclick="closeModal('addModal')">Cancel</button>
      <button class="btn-primary" id="modalSubmitBtn" onclick="submitForm()">Add</button>
    </div>
  </div>
</div>

<script>
let editingId = null; // null=新規, number=編集

function esc(s) { if (!s) return ''; const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

function setField(id, val) {
  const el = document.getElementById(id);
  if (!el) return;
  if (el.tagName === 'SELECT') {
    for (let i = 0; i < el.options.length; i++) {
      if (el.options[i].value === String(val || '')) { el.selectedIndex = i; return; }
    }
    el.selectedIndex = 0;
  } else {
    el.value = val || '';
  }
}

async function loadSchedules() {
  const res = await fetch('/api/schedules');
  const schedules = await res.json();
  const tbody = document.getElementById('scheduleBody');
  tbody.innerHTML = '';
  schedules.forEach(s => {
    const tr = document.createElement('tr');
    const statusCls = s.last_status ? 'status-badge status-' + s.last_status : '';
    tr.innerHTML = `
      <td style="font-family:var(--font-display)">${s.id}</td>
      <td><span class="toggle" onclick="event.stopPropagation();toggleEnabled(${s.id}, ${s.enabled ? 0 : 1})" style="color:${s.enabled ? 'var(--secondary)' : 'var(--text-secondary)'}">${s.enabled ? '\u25cf' : '\u25cb'}</span></td>
      <td style="cursor:pointer;color:var(--primary-lit)">${esc(s.name)}</td>
      <td><code style="font-family:var(--font-display);font-size:.8rem;color:var(--text-secondary)">${esc(s.cron_expr)}</code></td>
      <td style="font-family:var(--font-display);font-size:.8rem">${esc(s.backend)}+${esc(s.model)}</td>
      <td>${esc(s.task_type)}</td>
      <td style="font-family:var(--font-display);font-size:.8rem">${esc(s.next_run_at || '-')}</td>
      <td>${s.last_status ? '<span class="' + statusCls + '">' + s.last_status + '</span>' : '-'}</td>
      <td style="font-family:var(--font-display)">${s.consecutive_failures}/${s.max_consecutive_failures}</td>
      <td>
        <button class="btn-sm btn-run" onclick="event.stopPropagation();triggerRun(${s.id})">Run</button>
      </td>`;
    tr.style.cursor = 'pointer';
    tr.addEventListener('click', () => openEdit(s.id));
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
}

function resetForm() {
  ['addName','addCron','addType','addPrompt','addWorkDir','addMcpConfig','addTools'].forEach(id => setField(id, ''));
  setField('addPriority', 'medium');
  setField('addBackend', 'claude');
  setField('addModel', 'sonnet');
  setField('addTimeout', '300');
  setField('addMaxTurns', '30');
  setField('addMaxFailures', '3');
  setField('addPersistent', '0');
  setField('addPromptFile', '');
  setField('addToolsPreset', '');
  setField('addCronPreset', '');
}

function openAddModal() {
  editingId = null;
  resetForm();
  document.getElementById('modalTitle').textContent = 'ADD SCHEDULE';
  document.getElementById('modalSubmitBtn').textContent = 'ADD';
  document.getElementById('modalDeleteBtn').style.display = 'none';
  document.getElementById('addModal').classList.add('active');
  document.getElementById('addName').focus();
}

async function openEdit(id) {
  const res = await fetch('/api/schedules/' + id);
  if (!res.ok) return;
  const s = await res.json();
  editingId = id;

  setField('addName', s.name);
  setField('addCron', s.cron_expr);
  setField('addType', s.task_type);
  setField('addPriority', s.priority);
  setField('addBackend', s.backend);
  setField('addModel', s.model);
  setField('addPrompt', s.prompt);
  setField('addPromptFile', s.prompt_file);
  setField('addMcpConfig', s.mcp_config);
  setField('addTools', s.allowed_tools);
  setField('addTimeout', s.timeout_seconds);
  setField('addMaxTurns', s.max_turns);
  setField('addMaxFailures', s.max_consecutive_failures);
  setField('addPersistent', s.session_persistent);
  setField('addWorkDir', s.work_dir);

  document.getElementById('modalTitle').textContent = 'EDIT SCHEDULE';
  document.getElementById('modalSubmitBtn').textContent = 'SAVE';
  document.getElementById('modalDeleteBtn').style.display = 'inline-block';
  document.getElementById('addModal').classList.add('active');
}

function closeModal(id) { document.getElementById(id).classList.remove('active'); }
document.querySelectorAll('.modal-overlay').forEach(m => m.addEventListener('click', e => { if (e.target === m) m.classList.remove('active'); }));

async function submitForm() {
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

  let res;
  if (editingId) {
    res = await fetch('/api/schedules/' + editingId, { method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
  } else {
    res = await fetch('/api/schedules', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
  }
  if (!res.ok) { const e = await res.json(); return alert('エラー: ' + (e.error || 'Unknown')); }
  closeModal('addModal');
  loadSchedules();
}

async function deleteEditing() {
  if (!editingId) return;
  if (!confirm('このスケジュールを削除しますか？')) return;
  await fetch('/api/schedules/' + editingId, { method:'DELETE' });
  closeModal('addModal');
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
<title>WORK WORK WORK - Prompts</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#131313;--surface-lowest:#0e0e0e;--surface-low:#1c1b1b;--surface:#201f1f;--surface-highest:#353534;
  --primary:#ff5717;--primary-lit:#ffb59e;--secondary:#c3f400;--error:#e74c3c;--info:#3a86ff;
  --text:#e6e1e5;--text-secondary:#958f94;--ghost:rgba(92,64,55,.2);
  --font-display:'Space Grotesk',sans-serif;--font-body:'Inter',sans-serif;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--font-body);background:var(--bg);color:var(--text);min-height:100vh}
header{background:var(--surface-highest);padding:14px 24px;display:flex;align-items:center;gap:16px}
header h1{font-family:var(--font-display);font-size:1.3rem;font-weight:700;color:var(--primary);letter-spacing:0.04em;text-transform:uppercase}
header nav{display:flex;gap:6px;margin-left:16px}
header nav a{font-family:var(--font-display);color:var(--text-secondary);background:transparent;border:1px solid var(--ghost);padding:7px 16px;border-radius:0;font-size:.8rem;font-weight:600;text-decoration:none;text-transform:uppercase;letter-spacing:0.05em;transition:background .2s,color .2s}
header nav a:hover{background:var(--surface);color:var(--text)}
header nav a.active{background:var(--primary);color:#fff;border-color:var(--primary)}
.container{padding:20px 24px;max-width:1200px;margin:0 auto}
.toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}
.toolbar h2{font-family:var(--font-display);font-size:.9rem;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.06em}
.btn-add{font-family:var(--font-display);background:linear-gradient(135deg,var(--primary-lit),var(--primary));color:#fff;border:none;padding:8px 20px;border-radius:0;font-size:.85rem;cursor:pointer;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;transition:opacity .2s}
.btn-add:hover{opacity:.85}
/* ── Prompt Cards ── */
.prompt-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.prompt-card{background:var(--surface-low);border-left:4px solid var(--primary);border-radius:0;padding:18px;cursor:pointer;transition:transform .15s,box-shadow .15s}
.prompt-card:hover{transform:translateY(-1px);box-shadow:0 8px 24px rgba(0,0,0,.04)}
.prompt-card h3{font-family:var(--font-display);font-size:.9rem;margin-bottom:8px;color:var(--primary-lit);letter-spacing:0.02em}
.prompt-card .meta{font-family:var(--font-display);font-size:.65rem;color:var(--text-secondary);margin-bottom:10px;text-transform:uppercase;letter-spacing:0.04em}
.prompt-card .preview{font-family:var(--font-body);font-size:.78rem;color:var(--text-secondary);max-height:60px;overflow:hidden;white-space:pre-wrap;word-break:break-word;line-height:1.45}
/* ── Modal ── */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.65);display:none;align-items:center;justify-content:center;z-index:100}
.modal-overlay.active{display:flex}
.modal{background:var(--surface);border-radius:0;padding:28px;width:90%;max-width:740px;max-height:85vh;overflow-y:auto;box-shadow:0 12px 40px rgba(0,0,0,.3)}
.modal h2{font-family:var(--font-display);margin-bottom:20px;font-size:1.1rem;color:var(--primary-lit);text-transform:uppercase;letter-spacing:0.04em}
.modal label{display:block;font-family:var(--font-display);font-size:.75rem;color:var(--text-secondary);margin-bottom:4px;margin-top:14px;text-transform:uppercase;letter-spacing:0.05em}
.modal input,.modal textarea{width:100%;padding:10px 12px;border-radius:0;border:none;border-bottom:2px solid var(--text-secondary);background:var(--surface-low);color:var(--text);font-family:var(--font-body);font-size:.88rem;transition:border-color .2s}
.modal input:focus,.modal textarea:focus{outline:none;border-bottom-color:var(--secondary)}
.modal textarea{min-height:320px;resize:vertical;font-family:'SF Mono',Menlo,Consolas,monospace;font-size:.82rem;line-height:1.5;border-bottom:none;border-left:2px solid var(--ghost)}
.modal-actions{display:flex;gap:12px;margin-top:24px;justify-content:flex-end}
.modal-actions button{font-family:var(--font-display);padding:9px 22px;border-radius:0;border:none;font-size:.85rem;cursor:pointer;font-weight:600;text-transform:uppercase;letter-spacing:0.04em}
.btn-primary{background:linear-gradient(135deg,var(--primary-lit),var(--primary));color:#fff}
.btn-primary:hover{opacity:.85}
.btn-cancel{background:transparent;color:var(--text-secondary);border:1px solid var(--ghost) !important}
.btn-cancel:hover{background:var(--surface-low);color:var(--text)}
.btn-delete{background:var(--error);color:#fff}
.btn-delete:hover{opacity:.85}
.hint{font-family:var(--font-body);font-size:.7rem;color:var(--text-secondary);margin-top:4px}
</style>
</head>
<body>
<header>
  <h1>WORK WORK WORK</h1>
  <nav>
    <a href="/">Kanban</a>
    <a href="/tasks">Tasks</a>
    <a href="/logs">Logs</a>
    <a href="/schedules">Schedules</a>
    <a href="/prompts" class="active">Prompts</a>
  </nav>
</header>
<div class="container">
  <div class="toolbar">
    <h2>Prompts</h2>
    <button class="btn-add" onclick="openNewModal()">+ New Prompt</button>
  </div>
  <div class="prompt-grid" id="promptGrid"></div>
</div>

<!-- 編集モーダル -->
<div class="modal-overlay" id="editModal">
  <div class="modal">
    <h2 id="editTitle">Edit Prompt</h2>
    <label>Filename</label>
    <input type="text" id="editName" placeholder="例: weekly-sentry-review">
    <div class="hint">.txt は自動付与。英数字・ハイフン・アンダースコアのみ</div>
    <label>Content</label>
    <textarea id="editContent" placeholder="Claudeへの指示内容を記述..."></textarea>
    <div class="modal-actions">
      <button class="btn-delete" id="editDeleteBtn" style="margin-right:auto;display:none" onclick="deletePrompt()">Delete</button>
      <button class="btn-cancel" onclick="closeModal()">Cancel</button>
      <button class="btn-primary" onclick="savePrompt()">Save</button>
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
    grid.innerHTML = '<div style="color:var(--text-secondary);padding:20px;font-family:var(--font-body)">プロンプトファイルがありません。「+ New Prompt」から追加できます。</div>';
    return;
  }
  prompts.forEach(p => {
    const card = document.createElement('div');
    card.className = 'prompt-card';
    card.onclick = () => openEditModal(p.name);
    const lines = (p.content || '').split('\n').length;
    card.innerHTML = `
      <h3>${esc(p.name)}</h3>
      <div class="meta">${lines} lines / ${p.size}B / ${p.modified || ''}</div>
      <div class="preview">${esc((p.content || '').slice(0, 150))}</div>`;
    grid.appendChild(card);
  });
}

function openNewModal() {
  editingFile = null;
  document.getElementById('editTitle').textContent = 'New Prompt';
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
        elif path == "/tasks":
            self._send_html(TASKS_HTML)
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
            qs = parse_qs(urlparse(self.path).query)
            include_archived = qs.get("archived", ["0"])[0] == "1"
            if include_archived:
                rows = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
            else:
                rows = conn.execute("SELECT * FROM tasks WHERE COALESCE(archived, 0) = 0 ORDER BY created_at DESC").fetchall()
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
        allowed = {"task_name", "task_type", "priority", "status", "input", "result", "assigned_session_id", "started_at", "completed_at", "model", "timeout_seconds", "max_turns", "allowed_tools", "mcp_config", "work_dir", "archived"}
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
            status = qs.get("status", [None])[0]
            if status:
                where.append("status = ?")
                params.append(status)
            model = qs.get("model", [None])[0]
            if model:
                where.append("model = ?")
                params.append(model)
            schedule = qs.get("schedule", [None])[0]
            if schedule == "spot":
                where.append("schedule_id IS NULL")
            elif schedule == "schedule":
                where.append("schedule_id IS NOT NULL")
            limit = int(qs.get("limit", [50])[0])
            offset = int(qs.get("offset", [0])[0])
            sql = "SELECT id, timestamp, runner_type, task_source, task_type, task_name, status, cost_usd, duration_seconds, model, schedule_id FROM execution_logs"
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
