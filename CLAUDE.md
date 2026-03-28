# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

cronで `claude -p` を定期実行し、タスクソースからタスクを取得して自動処理するシステム。
定期タスク（メールチェック等）はschedulesテーブルで管理し、run-tasks.shが自動展開。
ログはSQLiteに蓄積し、Kanban Web UIで閲覧可能。

## よく使うコマンド

```bash
# タスクランナー手動実行
bash run-tasks.sh

# メールチェッカー手動実行（レガシー、schedulesへ移行推奨）
bash check-email.sh

# タスクCLI操作
./task add                          # 対話的にタスク追加
./task add -n "名前" -t research    # ワンライナーで追加
./task list                         # タスク一覧（アクティブのみ）
./task list --all                   # 全ステータス表示
./task list --status in_progress    # ステータスフィルタ
./task show <id>                    # 詳細表示
./task done <id>                    # 完了
./task cancel <id>                  # キャンセル（内部的にerror+理由記録）
./task retry <id>                   # リトライ（error/needs_clarification → pending）
./task stats                        # 統計

# スケジュール管理
./task schedule-add -n "名前" -c "cron式" [オプション]  # スケジュール追加
./task schedule-list                                     # スケジュール一覧
./task schedule-show <id>                                # 詳細表示
./task schedule-enable <id>                              # 有効化
./task schedule-disable <id>                             # 無効化
./task schedule-delete <id>                              # 削除
./task schedule-run <id>                                 # 手動即時実行

# Web UI起動（Kanban + ログビューア + スケジュール管理）
python3 kanban.py                   # http://localhost:8766

# DB初期化・マイグレーション
bash scripts/init-db.sh             # ログDB（db/logs.db）
bash sources/sqlite/init-tasks-db.sh # タスクDB（db/tasks.db）
bash scripts/migrate-001-schedules.sh # schedulesテーブル追加マイグレーション

# cron管理
bash scripts/install-cron.sh        # cron登録
bash scripts/uninstall-cron.sh      # cron解除

# Datasette（オプション）
datasette db/logs.db db/tasks.db --metadata metadata.json --port 8765
```

## ランタイム依存

`claude`（Claude CLI）, `jq`, `sqlite3`, `uuidgen`, `timeout`, `python3` — すべてmacOS + Homebrew環境前提。

## アーキテクチャ

### ランナー

| ランナー | スクリプト | cron間隔 | セッション | タイムアウト | ロックファイル |
|---|---|---|---|---|---|
| タスクランナー | `run-tasks.sh` | 10分毎 | 毎回新規（schedule設定で永続可） | 300秒（schedule設定で変更可） | `/tmp/claude-task-runner.lock` |
| メールチェッカー | `check-email.sh` | レガシー（schedulesへ移行推奨） | `--resume` で永続 | 180秒 | `/tmp/claude-email-checker.lock` |

### スケジュール機能

`schedules`テーブルで定期タスクを管理。`run-tasks.sh`が10分毎に実行時、期限到来のスケジュールを`tasks`テーブルに展開する。

```
run-tasks.sh（10分毎cron）
  ├── スケジュール展開: enabled=1 AND next_run_at <= now のスケジュールをタスクに変換
  │   └── 重複チェック（同schedule_idのpending/in_progressが既にあればスキップ）
  ├── プリフライトチェック: spotタスク（schedule_id IS NULL）を優先処理
  │   └── schedule_id付き → scheduleからmodel/allowed_tools/prompt等を取得
  ├── claude -p 実行（schedule由来はprompt/model/timeoutをオーバーライド）
  ├── スケジュール結果処理
  │   ├── 成功 → consecutive_failures = 0
  │   └── 失敗 → consecutive_failures++、上限到達で自動無効化
  └── ログ記録（schedule_id付き）
```

**スケジュール設定項目**: backend(claude/ollama/codex), model, prompt/prompt_file, work_dir, mcp_config, allowed_tools, timeout_seconds, max_turns, session_persistent, max_consecutive_failures

**cron式**: 5フィールド（分 時 日 月 曜日）。`scripts/cron-next.py` で次回実行時刻を計算。

### タスクソース（プラガブル）

`sources/source.conf`（1行目）で切替。各ソースは `sources/<name>/` に `prompt.txt` + `config.env` を持つ。

- **sqlite**（デフォルト）: `db/tasks.db` を `sqlite3` コマンドで直接操作。外部サービス不要
- **github**: `gh` CLI で GitHub Projects を操作。`config.env` にプロジェクトID・フィールドID・オプションIDを定義
- **notion**: Notion MCP 経由。`mcp-config.json` + `~/.claude/secrets/notion.env`（NOTION_TOKEN）が必要

#### ソース追加手順

1. `sources/<name>/` ディレクトリを作成
2. `config.env` に設定変数を定義
3. `prompt.txt` にClaude向けプロンプトを作成（`{{VAR_NAME}}` で変数参照）
4. `run-tasks.sh` のソース検証部分とallowedTools設定を追加

### プロンプトテンプレートの変数展開

`run-tasks.sh` が `config.env` を `source` で読み込んだ後、`prompt.txt` 内の `{{VAR_NAME}}` パターンを環境変数の値で `sed` 置換する。例: `config.env` に `SQLITE_TASK_DB=/path/to/db` があれば、プロンプト内の `{{SQLITE_TASK_DB}}` が展開される。

### 処理フロー（タスクランナー）

```
run-tasks.sh
  → mkdirロック取得（/tmp/claude-task-runner.lock）
  → スケジュール展開（期限到来のschedules → tasksにINSERT）
  → プリフライト: 次のpendingタスク確認（spot優先、schedule由来は設定オーバーライド）
  → source.conf → タスクソース決定
  → config.env source → prompt.txt 読み込み → {{VAR}} 展開
  → claude -p --output-format json --model MODEL --max-turns N
      （allowedToolsはソース別 or schedule定義）
  → Claude がタスク取得→処理→結果書き戻し（1タスクのみ）
  → スケジュール結果処理（consecutive_failures更新、自動無効化）
  → JSON結果パース → db/logs.db にログ記録（schedule_id付き）
  → logs/run-YYYYMMDD-HHMMSS.log にファイルログ
```

### 2つのDB

| DB | パス | 用途 | スキーマ |
|---|---|---|---|
| タスクDB | `db/tasks.db` | タスクキュー + スケジュール管理（CRUD） | `sources/sqlite/schema.sql` |
| ログDB | `db/logs.db` | 全実行ログ蓄積（INSERT only） | `db/schema.sql` |

タスクDBにはtasksテーブルとschedulesテーブルが含まれる。tasksテーブルのschedule_idカラムでスケジュール由来のタスクを識別。
GitHub/Notionソースではタスク管理は外部サービス側が担い、ログDBのみ使用。

### allowedTools（ソース別）

| ソース | 許可ツール |
|---|---|
| sqlite | `Read Grep Glob WebSearch WebFetch Bash(git:*) Bash(sqlite3:*) Bash(curl:*)` |
| github | `Read Grep Glob WebSearch WebFetch Bash(git:*) Bash(gh:*)` |
| notion | `Read Grep Glob WebSearch WebFetch` + Notion MCP ツール |

コロン+ワイルドカード形式（例: `Bash(gh:*)` は gh の全サブコマンドを許可）。

### 排他制御（3層）

1. **mkdir ロック**: 多重起動防止。30分で自動解除（`stat -f %m` で経過時間判定）
2. **タスクステータス**: pending のみ取得→即座に in_progress + session_id 記録
3. **stale検出**: in_progress が30分超 → pending に自動復帰（プロンプト内でClaude自身が実行）

### Web UI（kanban.py）

Python標準ライブラリのみ（外部依存なし）。ポート8766。HTMLはPython内に埋め込み。
- `/` — Kanbanボード（ドラッグ＆ドロップ対応）
- `/logs` — ログビューア（フィルタ、日別コストチャート、詳細モーダル）
- `/schedules` — スケジュール管理（有効/無効トグル、手動実行、追加/削除）
- `/api/tasks`, `/api/logs`, `/api/schedules` — REST API

## macOS固有の注意点

- `flock` は使えない → `mkdir` によるアトミックロック
- `stat -f %m` でファイル更新時間取得（Linux の `-c %Y` ではない）
- cron 実行時は PATH が通らないため、スクリプト冒頭で `export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"` を明示的に設定
- `unset CLAUDECODE` でネスト実行時のClaude Codeセッション検出を回避

## タスク処理ルール（claude -p 実行時）

1. **1回の実行で1タスクのみ処理する**
2. **指示されたスコープ外の変更は一切行わない**
3. タスク処理後、必ずタスクソースのステータスを更新する
4. 実行ログは必ずSQLiteに記録する
5. エラーが発生した場合もログに記録し、タスクステータスを "error" にする
6. 処理時間が5分を超えそうな場合は中間結果を記録して終了する
7. 不明な点があるタスクは "needs_clarification" にして人間に戻す
8. **AIがタスクを生成する場合は必ず needs_review ステータスにする**（人間ゲート必須）
9. スコープ外の作業を検出した場合は即停止しログに記録する
10. 日本語で回答すること

## タスク種別とリスクレベル

### 🟢 Read-Only（コード変更なし）
| 種別 | 内容 | max-budget |
|---|---|---|
| `research` | 技術調査・コードベース分析 | $0.50 |
| `sentry_analysis` | Sentryイシュー原因調査 | $0.50 |
| `planning` | 要件→実装計画作成 | $0.80 |

### 🟡 Comment（コメント投稿のみ）
| 種別 | 内容 | max-budget |
|---|---|---|
| `code_review` | PRにレビューコメント投稿 | $0.80 |

### 📧 別軸
| 種別 | 内容 | max-budget |
|---|---|---|
| `email_check` | Gmail確認・要約（読み取り専用） | $0.30 |

### 🔴 Code Modification（Phase 2 で追加予定）
- bug_fix, test_gen, docs → 初期リリースには含めない
- **現フェーズではコード変更を伴うタスクは実行禁止**

## ステータス遷移（看板モデル）

```
pending → in_progress → completed
                      → error
                      → needs_clarification（人間に戻す）

※ in_progress が30分経過 → stale として pending に自動復帰
※ cancel は error + result に理由記録（スキーマに cancelled がないため）
※ retry は error/needs_clarification → pending に戻す
```

## 禁止コマンド（Deny Patterns）

以下のコマンドは**絶対に実行しない**：

- `rm -rf` / `rm -r`
- `git push --force` / `git push -f` / `git reset --hard` / `git clean -f` / `git checkout .` / `git restore .` / `git branch -D`
- `drop` / `truncate`（DB操作）
- `kill -9` / `killall`
- `chmod 777`
- `curl | sh` / `curl | bash`
- `npm publish` / `gem push`
- `docker rm` / `docker rmi`
- 環境変数の外部送信
- メール送信（下書き作成も不可、email_checkタスク含む）

## 方向性ドリフト防止

- タスクに記載されたスコープのみを処理する
- 「ついでに」「改善のため」等の理由で追加作業をしない
- 判断に迷う場合は needs_clarification にして停止する
- AIが新たなタスクを提案する場合は needs_review ステータスで作成する
