# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

cronで `claude -p` を定期実行し、タスクソースからタスクを取得して自動処理するシステム。
定期タスク（メールチェック等）はschedulesテーブルで管理し、run-tasks.shが自動展開。
ログはSQLiteに蓄積し、Kanban Web UIで閲覧可能。

## よく使うコマンド

```bash
# サーバー起動（Web UI + タスクランナー自動実行）
python3 server.py                   # http://localhost:8766（10分毎に自動実行）
python3 server.py --interval 300    # 5分毎に変更
python3 server.py --no-runner       # Web UIのみ（タスクランナー無効）

# タスクランナー手動実行
bash run-tasks.sh

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

# DB初期化・マイグレーション
bash scripts/init-db.sh             # ログDB（db/logs.db）
bash sources/sqlite/init-tasks-db.sh # タスクDB（db/tasks.db）
bash scripts/migrate-001-schedules.sh # schedulesテーブル追加マイグレーション

# デーモン管理（macOS launchd）
bash scripts/install-daemon.sh      # デーモンインストール＆起動
bash scripts/uninstall-daemon.sh    # デーモン停止＆削除

# Datasette（オプション）
datasette db/logs.db db/tasks.db --metadata metadata.json --port 8765
```

## ランタイム依存

`claude`（Claude CLI）, `jq`, `sqlite3`, `uuidgen`, `timeout`, `python3` — すべてmacOS + Homebrew環境前提。

## アーキテクチャ

### サーバー（server.py）

Python標準ライブラリのみ（外部依存なし）。ポート8766。
- REST APIサーバー + 静的ファイル配信
- バックグラウンドスレッドでrun-tasks.shを定期実行（デフォルト10分毎）
- ターミナルから起動するためmacOSキーチェーンのOAuth認証が使える（cronでは使えない）
- `--no-runner` でタスクランナーを無効化可能
- `.pause` ファイルで一時停止/再開

### フロントエンド（static/）

Alpine.js + Kinetic Consoleデザインシステム。
- `static/css/style.css` — 共通CSS（CSS custom properties）
- `static/js/common.js` — API wrapper、ユーティリティ、キーボードショートカット
- 各ページ: `index.html`(Kanban), `tasks.html`, `logs.html`, `schedules.html`, `prompts.html`, `debug-logs.html`

### Web UIページ

| パス | ページ | 内容 |
|---|---|---|
| `/` | Kanban | ドラッグ＆ドロップ対応のタスクボード |
| `/tasks` | Tasks | 全タスク一覧（アーカイブ含む） |
| `/logs` | Logs | 実行ログ（フィルタ、日別コストチャート、詳細モーダル） |
| `/schedules` | Schedules | スケジュール管理（追加/編集/削除/トグル/手動実行） |
| `/prompts` | Prompts | プロンプトファイルのCRUD |
| `/debug-logs` | Debug | ファイルログの4ペイン同時表示 |

### キーボードショートカット

| キー | 動作 |
|---|---|
| `1`-`6` | ページ切替 |
| `n` | 新規作成 |
| `Esc` | モーダル閉じる |
| `[` / `]` | ページ送り |
| `d` | 削除（モーダル内） |
| `a` | アーカイブ（モーダル内） |
| `?` | ヘルプ表示 |

### ランナー（run-tasks.sh）

| 項目 | 設定 |
|---|---|
| 起動方式 | server.pyのバックグラウンドタイマー（10分毎） |
| セッション | 毎回新規（schedule設定で永続可） |
| タイムアウト | 300秒（タスク/schedule設定で変更可） |
| ロックファイル | `/tmp/claude-task-runner.lock` |
| 一時停止 | `.pause` ファイルの有無で判定 |

### スケジュール機能

`schedules`テーブルで定期タスクを管理。`run-tasks.sh`実行時、期限到来のスケジュールを`tasks`テーブルに展開する。

```
run-tasks.sh
  ├── 一時停止チェック（.pauseファイル）
  ├── mkdirロック取得
  ├── スケジュール展開: enabled=1 AND next_run_at <= now のスケジュールをタスクに変換
  │   └── 重複チェック（同schedule_idのpending/in_progressが既にあればスキップ）
  ├── プリフライト: 次のpendingタスク特定（spot優先）
  │   └── タスク/スケジュールの実行設定をオーバーライド
  ├── claude -p 実行
  ├── 結果パース
  ├── タスクステータス同期（schedule由来タスクのcompleted/error反映）
  ├── スケジュール結果処理（consecutive_failures更新、自動無効化）
  └── ログ記録（execution_logs + ファイルログ）
```

### 実行設定の解決順序（優先度高→低）

1. **タスク自体のカラム** — tasks.model, tasks.mcp_config 等
2. **スケジュール設定** — schedules.model, schedules.prompt 等（schedule_id付きタスクのみ）
3. **ソースデフォルト** — source.conf + config.env + prompt.txt

### タスクソース（プラガブル）

`sources/source.conf`（1行目）で切替。各ソースは `sources/<name>/` に `prompt.txt` + `config.env` を持つ。

- **sqlite**（デフォルト）: `db/tasks.db` を `sqlite3` コマンドで直接操作。外部サービス不要
- **github**: `gh` CLI で GitHub Projects を操作。`config.env` にプロジェクトID・フィールドID・オプションIDを定義
- **notion**: Notion MCP 経由。`mcp-config.json` + `~/.claude/secrets/notion.env`（NOTION_TOKEN）が必要

### 2つのDB

| DB | パス | 用途 | スキーマ |
|---|---|---|---|
| タスクDB | `db/tasks.db` | タスクキュー + スケジュール管理（CRUD） | `sources/sqlite/schema.sql` |
| ログDB | `db/logs.db` | 全実行ログ蓄積（INSERT only） | `db/schema.sql` |

タスクDBにはtasksテーブルとschedulesテーブルが含まれる。tasksテーブルのschedule_idカラムでスケジュール由来のタスクを識別。

### allowedTools（ソース別デフォルト）

| ソース | 許可ツール |
|---|---|
| sqlite | `Read Grep Glob WebSearch WebFetch Bash(git:*) Bash(sqlite3:*) Bash(curl:*)` |
| github | `Read Grep Glob WebSearch WebFetch Bash(git:*) Bash(gh:*)` |
| notion | `Read Grep Glob WebSearch WebFetch` + Notion MCP ツール |

タスクごと・スケジュールごとにallowed_toolsをオーバーライド可能。

### MCP接続

| サービス | 設定ファイル | 確認状況 |
|---|---|---|
| Google Workspace | mcp-config-email.json | claude -p で動作確認済み |
| Sentry | mcp-config-sentry.json | claude -p で動作確認済み |
| Notion | sources/notion/mcp-config.json | 未確認 |
| プロジェクト固有 | 各PJの.mcp.json | work_dir + cd で利用可能 |

### 排他制御（3層）

1. **mkdir ロック**: 多重起動防止。30分で自動解除（`stat -f %m` で経過時間判定）
2. **タスクステータス**: pending のみ取得→即座に in_progress + session_id 記録
3. **stale検出**: in_progress が30分超 → pending に自動復帰（プロンプト内でClaude自身が実行）

## macOS固有の注意点

- `flock` は使えない → `mkdir` によるアトミックロック
- `stat -f %m` でファイル更新時間取得（Linux の `-c %Y` ではない）
- スクリプト冒頭で `export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"` を明示的に設定
- `unset CLAUDECODE` でネスト実行時のClaude Codeセッション検出を回避
- **cron環境からはキーチェーンのOAuth認証にアクセスできない** → server.pyタイマー方式を使用

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

## タスクラベル

ラベル（task_type）は自由入力。分類用のタグとして使用し、実行動作はプロンプトで決まる。
よく使うラベル例:

| ラベル | 用途 |
|---|---|
| `research` | 技術調査・コードベース分析 |
| `sentry_analysis` | Sentryイシュー原因調査 |
| `planning` | 要件→実装計画作成 |
| `code_review` | PRレビューコメント投稿 |
| `email_check` | メール確認・要約 |

## ステータス遷移（看板モデル）

```
pending → in_progress → completed
                      → error
                      → needs_clarification（人間に戻す）

※ in_progress が30分経過 → stale として pending に自動復帰
※ cancel は error + result に理由記録（スキーマに cancelled がないため）
※ retry は error/needs_clarification → pending に戻す
※ completed/error → archived（Kanbanから非表示、Tasksページで閲覧可能）
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
