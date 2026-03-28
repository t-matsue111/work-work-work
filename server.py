#!/usr/bin/env python3
"""Claude Task Runner - API Server + Static File Serving

フロントエンド分離版。static/ 配下のHTML/CSS/JSを配信し、
REST APIはkanban.pyと同一のエンドポイント・レスポンス形式を維持。

Usage:
    python3 server.py [--port PORT] [--db PATH]
"""

import argparse
import json
import mimetypes
import os
import re
import signal
import sqlite3
import subprocess
import sys
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# デフォルト設定
DEFAULT_PORT = 8766
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "db", "tasks.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "sources", "sqlite", "schema.sql")
PROMPTS_DIR = os.path.join(BASE_DIR, "prompts")
LOGS_DB_PATH = os.path.join(BASE_DIR, "db", "logs.db")
CRON_NEXT_SCRIPT = os.path.join(BASE_DIR, "scripts", "cron-next.py")
STATIC_DIR = os.path.join(BASE_DIR, "static")
FILE_LOGS_DIR = os.path.join(BASE_DIR, "logs")

# HTMLページルーティング
PAGE_ROUTES = {
    "/": "index.html",
    "/tasks": "tasks.html",
    "/logs": "logs.html",
    "/schedules": "schedules.html",
    "/prompts": "prompts.html",
    "/debug-logs": "debug-logs.html",
}


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
        print(f"[server] スキーマを初期化しました: {db_path}")
    return conn


def get_logs_db() -> sqlite3.Connection:
    """logs.db に接続する"""
    conn = sqlite3.connect(LOGS_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def rows_to_dicts(rows):
    return [dict(r) for r in rows]


# ── リクエストハンドラ ─────────────────────────────────────────────
class AppHandler(BaseHTTPRequestHandler):
    db_path = DEFAULT_DB_PATH

    def log_message(self, format, *args):
        # アクセスログを簡潔に
        sys.stderr.write(f"[server] {args[0]}\n")

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, filepath, content_type=None):
        """静的ファイルを配信する"""
        if not os.path.isfile(filepath):
            self._send_json({"error": "Not Found"}, 404)
            return
        if content_type is None:
            content_type, _ = mimetypes.guess_type(filepath)
            if content_type is None:
                content_type = "application/octet-stream"
        with open(filepath, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
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

        # HTMLページルーティング
        if path in PAGE_ROUTES:
            filepath = os.path.join(STATIC_DIR, PAGE_ROUTES[path])
            self._send_file(filepath, "text/html; charset=utf-8")
            return

        # 静的ファイル配信 (/static/...)
        if path.startswith("/static/"):
            # パストラバーサル防止
            rel = path[len("/static/"):]
            safe_path = os.path.normpath(os.path.join(STATIC_DIR, rel))
            if not safe_path.startswith(STATIC_DIR):
                self._send_json({"error": "Forbidden"}, 403)
                return
            self._send_file(safe_path)
            return

        # API ルーティング
        if path == "/api/debug-logs":
            self._handle_get_debug_logs(qs)
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

    # ── Tasks API ─────────────────────────────────────────────────
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
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("UPDATE schedules SET next_run_at = ?, enabled = 1 WHERE id = ?", (now, schedule_id))
            conn.commit()
            self._send_json({"triggered": schedule_id, "next_run_at": now})
        finally:
            conn.close()

    # ── Debug Logs API ─────────────────────────────────────────────
    def _handle_get_debug_logs(self, qs):
        """最新のrunログファイルとcronログファイルの内容を返す"""
        file_type = qs.get("type", ["run"])[0]  # run or cron-tasks or cron-email
        tail = int(qs.get("tail", [200])[0])

        def find_latest(prefix):
            try:
                files = sorted(
                    [f for f in os.listdir(FILE_LOGS_DIR) if f.startswith(prefix) and f.endswith(".log")],
                    reverse=True,
                )
                return os.path.join(FILE_LOGS_DIR, files[0]) if files else None
            except Exception:
                return None

        if file_type == "cron-tasks":
            fpath = os.path.join(FILE_LOGS_DIR, "cron-tasks.log")
        elif file_type == "cron-email":
            fpath = os.path.join(FILE_LOGS_DIR, "cron-email.log")
        elif file_type == "email":
            fpath = find_latest("email-")
        else:
            fpath = find_latest("run-")

        if not fpath or not os.path.isfile(fpath):
            self._send_json({"file": None, "content": "", "lines": 0})
            return

        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
            content = "".join(all_lines[-tail:])
            self._send_json({
                "file": os.path.basename(fpath),
                "content": content,
                "lines": len(all_lines),
                "showing": min(tail, len(all_lines)),
            })
        except Exception as e:
            self._send_json({"file": os.path.basename(fpath), "content": str(e), "lines": 0})

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
            sql = "SELECT id, timestamp, runner_type, task_source, task_type, task_name, task_external_id, status, cost_usd, duration_seconds, model, schedule_id FROM execution_logs"
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
    parser = argparse.ArgumentParser(description="Claude Task Runner - API Server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"ポート番号 (default: {DEFAULT_PORT})")
    parser.add_argument("--db", type=str, default=DEFAULT_DB_PATH, help=f"DBファイルパス (default: {DEFAULT_DB_PATH})")
    args = parser.parse_args()

    AppHandler.db_path = args.db

    HTTPServer.allow_reuse_address = True
    server = HTTPServer(("0.0.0.0", args.port), AppHandler)
    print(f"[server] Server: http://localhost:{args.port}")
    print(f"[server] DB: {args.db}")
    print(f"[server] Static: {STATIC_DIR}")
    print(f"[server] Ctrl+C で終了")

    def shutdown(sig, frame):
        print("\n[server] シャットダウン中...")
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
        print("[server] 停止しました")


if __name__ == "__main__":
    main()
