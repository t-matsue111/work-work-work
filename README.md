# Claude Task Runner

cron で `claude -p` を定期実行し、タスクソース（SQLite / Notion DB / GitHub Projects）からタスクを取得して自動処理するシステム。

## アーキテクチャ概要

```
┌──────────┐     ┌──────────────────┐     ┌──────────────┐
│  cron    │────▶│  run-tasks.sh    │────▶│  claude -p   │
│ (10分毎) │     │  (排他制御付き)    │     │  (タスク実行)  │
└──────────┘     └──────────────────┘     └──────┬───────┘
                                                 │
                 ┌───────────────────────────────┼───────────────────────────────┐
                 ▼                               ▼                               ▼
        ┌────────────────┐             ┌────────────────┐             ┌─────────────────┐
        │  SQLite DB     │             │  Notion DB     │             │ GitHub Projects  │
        │  (デフォルト)    │             │  (タスクソース)  │             │ (タスクソース)    │
        └────────────────┘             └────────────────┘             └─────────────────┘

┌──────────────────┐     ┌──────────────────┐
│  cron            │────▶│ check-email.sh   │────▶ Gmail 確認・要約
│ (平日毎時)        │     │                  │
└──────────────────┘     └──────────────────┘

┌──────────────────┐
│  kanban.py       │────▶ http://localhost:8766  Kanban ボード + ログビューア(/logs)
│ (Web UI)         │
└──────────────────┘
```

### 処理フロー

1. cron が `run-tasks.sh` を起動
2. mkdir ロックによる排他制御を確認（macOS では flock が利用不可のため）
3. タスクソース（SQLite / Notion / GitHub Projects）から `pending` のタスクを1件取得
4. タスクのステータスを `in_progress` に更新
5. `claude -p` でタスクを実行
6. 実行結果をタスクソースに反映し、SQLite にログを記録
7. 異常時はステータスを `error` にし、エラー内容をログに記録

## ディレクトリ構成

```
claude-task-runner/
├── CLAUDE.md                  # Claude への指示書（基本ルール・禁止事項）
├── README.md                  # 本ファイル（設計書兼セットアップガイド）
├── metadata.json              # Datasette 用メタデータ
├── mcp-config-email.json      # メールチェッカー用 MCP 設定
├── run-tasks.sh               # タスクランナー本体（cron から呼び出し）
├── check-email.sh             # メールチェッカー本体（cron から呼び出し）
├── kanban.py                  # Kanban ボード + ログビューア（Web UI）
├── task                       # タスク管理 CLI コマンド
├── db/
│   ├── schema.sql             # SQLite スキーマ定義（実行ログ）
│   ├── logs.db                # 実行ログ DB（init-db.sh で作成）
│   └── tasks.db               # タスク DB（init-tasks-db.sh で作成）
├── logs/
│   ├── cron-tasks.log         # タスクランナーの cron 出力ログ
│   └── cron-email.log         # メールチェッカーの cron 出力ログ
├── prompts/
│   └── email-checker.txt      # メールチェッカー用プロンプト
├── scripts/
│   ├── init-db.sh             # ログ DB 初期化スクリプト
│   ├── install-cron.sh        # cron エントリ登録
│   └── uninstall-cron.sh      # cron エントリ削除
└── sources/
    ├── source.conf            # 有効なタスクソース（デフォルト: sqlite）
    ├── sqlite/
    │   ├── config.env         # SQLite 接続設定
    │   ├── schema.sql         # タスク DB スキーマ定義
    │   ├── init-tasks-db.sh   # タスク DB 初期化スクリプト
    │   ├── add-task.sh        # タスク追加スクリプト
    │   └── prompt.txt         # タスクランナー用プロンプト
    ├── notion/
    │   ├── config.env         # Notion 接続設定
    │   ├── mcp-config.json    # Notion MCP 設定
    │   └── prompt.txt         # タスクランナー用プロンプト
    └── github/
        ├── config.env         # GitHub Projects 接続設定
        └── prompt.txt         # タスクランナー用プロンプト
```

## タスク種別（リスクレベル別）

### 🟢 Read-Only（コード変更なし）

| 種別 | 内容 | max-budget |
|---|---|---|
| `research` | 技術調査・コードベース分析 | $0.50 |
| `sentry_analysis` | Sentry イシュー原因調査 | $0.50 |
| `planning` | 要件から実装計画を作成 | $0.80 |

### 🟡 Comment（コメント投稿のみ）

| 種別 | 内容 | max-budget |
|---|---|---|
| `code_review` | PR にレビューコメント投稿 | $0.80 |

### 📧 別軸

| 種別 | 内容 | max-budget |
|---|---|---|
| `email_check` | Gmail 確認・要約（読み取り専用） | $0.30 |

### 🔴 Code Modification（Phase 2 で追加予定）

- `bug_fix`, `test_gen`, `docs` は初期リリースには含めない
- **現フェーズではコード変更を伴うタスクは実行禁止**

## ステータス遷移

```
pending → in_progress → completed
                      → error
                      → needs_clarification（人間に戻す）
                      → needs_review（AI がタスク生成した場合）

※ in_progress が 30 分経過 → stale として pending に自動復帰
```

### ステータスの意味

| ステータス | 説明 |
|---|---|
| `pending` | 実行待ち。ランナーが次回ピックアップ可能 |
| `in_progress` | 実行中。排他制御のロック対象 |
| `completed` | 正常完了 |
| `error` | エラー終了。ログに詳細を記録 |
| `needs_clarification` | 人間の判断が必要。タスクソース上で確認 |
| `needs_review` | AI が生成したタスク。人間の承認待ち |

## 排他制御（3層構造）

並行実行によるタスクの重複処理を防止するため、3層の排他制御を実装している。

### 第1層: プロセスレベル排他

```bash
# Linux: flock を使用
exec 200>/tmp/claude-task-runner.lock
flock -n 200 || exit 0

# macOS: flock が利用不可のため mkdir ロックを使用
mkdir /tmp/claude-task-runner.lock 2>/dev/null || exit 0
trap "rmdir /tmp/claude-task-runner.lock" EXIT
```

- `run-tasks.sh` の冒頭でロックを取得
- 同時に複数の `run-tasks.sh` が起動しても、1つだけが実行される
- cron が 10 分間隔のため、前回実行が長引いた場合のガード

### 第2層: タスクステータスによる論理排他

- タスク取得時に `pending` のもののみをピックアップ
- 取得直後に `in_progress` に更新
- Notion API / GitHub API / SQLite のステータス更新がアトミックな操作として機能

### 第3層: stale 検出と自動復帰

- `in_progress` のまま 30 分以上経過したタスクを検出
- 自動的に `pending` に復帰させ、再実行可能にする
- クラッシュやタイムアウトで中途半端に残ったタスクの救済措置

## 方向性ドリフト防止

AI がタスクの範囲を超えて「ついでに」作業することを防ぐための仕組み。

### 対策

1. **CLAUDE.md による厳格なルール定義**: 「指示されたスコープ外の変更は一切行わない」を明記
2. **1実行1タスク制約**: 1回のランナー実行で処理するタスクは1件のみ
3. **禁止コマンドリスト**: 破壊的操作（`rm -rf`, `git push --force` 等）を明示的に禁止
4. **タスク生成の人間ゲート**: AI が新タスクを提案する場合は `needs_review` で必ず人間の承認を経由
5. **処理時間制限**: 5分を超えそうな場合は中間結果を記録して終了

## セットアップ手順

### 事前準備チェックリスト

- [ ] `claude` CLI がインストール済みであること
- [ ] `sqlite3` コマンドが利用可能であること
- [ ] `python3` が利用可能であること（Kanban ボード使用時）
- [ ] Notion アカウントを持っていること（Notion ソースを使う場合）
- [ ] GitHub アカウントと `gh` CLI がセットアップ済みであること（GitHub ソースを使う場合）
- [ ] Gmail の MCP 設定が完了していること（メールチェッカーを使う場合）

### 1. ログ DB 初期化

```bash
cd ~/project/claude-task-runner
./scripts/init-db.sh
```

`db/logs.db` が作成され、テーブルとビューが初期化される。

### 2. SQLite タスクソース セットアップ（デフォルト・推奨）

外部サービス不要でスタンドアロン動作するタスクソース。

#### 2-1. タスク DB 初期化

```bash
bash sources/sqlite/init-tasks-db.sh
```

`db/tasks.db` が作成され、タスク管理テーブルが初期化される。

#### 2-2. タスクの投入

`task` CLI を使ってタスクを追加する:

```bash
# 対話モード（質問に答えていくだけ）
./task add

# ワンライナーで直接追加
./task add -n "Railsのキャッシュ戦略調査" -t research -p high -i "Redis vs Memcached の比較"
```

#### 2-3. タスクソースの設定確認

`sources/source.conf` に `sqlite` が設定されていることを確認（デフォルト）:

```bash
cat sources/source.conf
# => sqlite
```

#### 2-4. 手動テスト

```bash
bash run-tasks.sh
```

### 3. task CLI リファレンス

タスクの管理は `./task` コマンドで行う:

```bash
# タスク追加（対話モード）
./task add

# タスク追加（オプション指定）
./task add -n "タスク名" -t research -p high -i "詳細な説明"

# タスク一覧（pending のみ）
./task list

# タスク一覧（全ステータス表示）
./task list --all

# タスク詳細表示
./task show 5

# タスクを完了にする
./task done 5

# タスクをリトライ（error → pending に戻す）
./task retry 5

# 統計情報
./task stats
```

### 4. Notion セットアップ（オプション）

#### 4-1. Notion 統合トークンの取得

1. [Notion Integrations](https://www.notion.so/my-integrations) にアクセス
2. 「新しいインテグレーション」を作成
3. 名前: `claude-task-runner`（任意）
4. 機能: 「コンテンツを読み取る」「コンテンツを更新する」を有効化
5. トークン（`ntn_` で始まる文字列）をコピー

#### 4-2. Notion タスク DB の作成

Notion に以下のプロパティを持つデータベースを作成する:

| プロパティ名 | 種別 | 説明 |
|---|---|---|
| タスク名 | タイトル | タスクの件名 |
| Status | セレクト | `pending` / `in_progress` / `completed` / `error` / `needs_clarification` / `needs_review` |
| Type | セレクト | `research` / `sentry_analysis` / `planning` / `code_review` |
| Target | テキスト | 対象リポジトリやファイルのパス |
| Description | テキスト | タスクの詳細説明 |

作成後、データベースページで「コネクションを追加」から `claude-task-runner` を接続する。

#### 4-3. config.env の設定

```bash
# sources/notion/config.env
NOTION_TASK_DB_ID="YOUR_TASK_DB_ID_HERE"  # Notion DB URL の末尾32文字
```

トークンは `~/.claude/secrets/notion.env` に保存する:

```bash
mkdir -p ~/.claude/secrets
echo 'NOTION_API_TOKEN="ntn_xxxxx"' > ~/.claude/secrets/notion.env
chmod 600 ~/.claude/secrets/notion.env
```

### 5. GitHub Projects セットアップ（オプション）

#### 5-1. config.env の設定

```bash
# sources/github/config.env
GH_PROJECT_OWNER="YOUR_OWNER_HERE"          # organization or user
GH_PROJECT_NUMBER="YOUR_PROJECT_NUMBER_HERE" # プロジェクト番号
GH_STATUS_FIELD="Status"
GH_STATUS_PENDING="Todo"
GH_STATUS_IN_PROGRESS="In Progress"
GH_STATUS_COMPLETED="Done"
GH_STATUS_ERROR="Error"
GH_STATUS_NEEDS_CLARIFICATION="Needs Clarification"
```

#### 5-2. タスクソースの有効化

```bash
# sources/source.conf に使いたいソースを1行ずつ記載（デフォルトは sqlite）
echo "notion" > ~/project/claude-task-runner/sources/source.conf
# GitHub も使う場合:
# echo -e "notion\ngithub" > ~/project/claude-task-runner/sources/source.conf
```

### 6. cron 登録

```bash
./scripts/install-cron.sh
```

登録される cron エントリ:
- タスクランナー: 10分毎に実行
- メールチェッカー: 平日 8:00-20:00 に毎時7分に実行
- DB 最適化: 毎日深夜3時に VACUUM 実行

削除する場合:

```bash
./scripts/uninstall-cron.sh
```

### 7. Kanban ボード（Web UI）

Python 標準ライブラリのみで動作する軽量 Web UI。タスクの Kanban ボードとログビューアを統合している。

```bash
python3 kanban.py
# => http://localhost:8766 で起動
```

機能:
- **Kanban ボード** (`/`): タスクのステータス別表示、ドラッグ&ドロップ、新規タスク作成
- **ログビューア** (`/logs`): 実行ログの閲覧・検索

> **Note:** Datasette は不要。kanban.py 単体で完結する。

### 8. Datasette（オプション・レガシー）

Datasette を使いたい場合は別途インストールが必要:

```bash
pip install datasette datasette-vega
datasette db/logs.db --metadata metadata.json --port 8765
```

ブラウザで http://localhost:8765 にアクセスすると、実行ログの閲覧・検索が可能。

用意されているクエリ:
- **直近のエラー**: エラーで終了したタスクの一覧
- **日別コスト**: 日ごとの実行回数とコスト
- **月別コスト**: 月ごとの実行回数とコスト

## macOS での注意事項

- **flock が利用不可**: macOS には `flock` コマンドがないため、`run-tasks.sh` では `mkdir` ベースのロックを使用する
- **CLAUDECODE 環境変数**: cron 実行時に `CLAUDECODE` 環境変数が設定されていると問題が起きる場合がある。`run-tasks.sh` 内で `unset CLAUDECODE` を実行して回避する

## 手動テスト

cron を待たずに手動で実行する場合:

```bash
# タスクランナーを手動実行
/bin/bash ~/project/claude-task-runner/run-tasks.sh

# メールチェッカーを手動実行
/bin/bash ~/project/claude-task-runner/check-email.sh
```

ログは以下で確認:

```bash
# 実行ログ DB を直接参照
sqlite3 ~/project/claude-task-runner/db/logs.db \
  "SELECT timestamp, task_type, task_name, status FROM execution_logs ORDER BY timestamp DESC LIMIT 10;"

# タスク一覧を確認
./task list --all

# cron ログを確認
tail -50 ~/project/claude-task-runner/logs/cron-tasks.log
tail -50 ~/project/claude-task-runner/logs/cron-email.log
```

## 検証方法

### DB スキーマの確認

```bash
# ログ DB
sqlite3 ~/project/claude-task-runner/db/logs.db ".schema"

# タスク DB
sqlite3 ~/project/claude-task-runner/db/tasks.db ".schema"
```

### cron 登録の確認

```bash
crontab -l | grep claude-task-runner
```

### タスクソース接続の確認

SQLite の場合:

```bash
./task list
./task stats
```

Notion の場合、MCP 経由で DB にアクセスできるか確認:

```bash
claude -p "Notion DB ID: $(grep NOTION_TASK_DB_ID ~/project/claude-task-runner/sources/notion/config.env | cut -d'"' -f2) のタスク一覧を取得してください" \
  --mcp-config ~/project/claude-task-runner/sources/notion/mcp-config.json
```

### ログ記録の確認

テスト実行後、SQLite にログが記録されていることを確認:

```bash
sqlite3 ~/project/claude-task-runner/db/logs.db \
  "SELECT COUNT(*) FROM execution_logs;"
```

### Kanban ボードの動作確認

```bash
python3 kanban.py &
curl -s http://localhost:8766 | head -20
```
