# work-work-work デザイン要件書

## 1. プロジェクト概要

cronで `claude -p` を定期実行し、タスクを自動処理するシステム。
spot task（手動登録）とschedule task（定期実行）を統一パイプラインで管理する。

### 現状の課題（v0での学び）

- **成功率が低い**: 900回実行中、成功368/エラー529（成功率41%）
- **Claudeの挙動が不安定**: プロンプト指示通りにDBクエリせず、過去の結果を返すケースあり
- **run-tasks.shが肥大化**: スケジュール展開・プリフライト・オーバーライド・結果処理で400行超
- **spot taskとschedule taskで実行パスが異なる**: spot taskはprompt.txt経由でClaude自身がDB操作、schedule taskはrun-tasks.shがオーバーライド
- **HTTP型MCPのOAuth認証**: `claude -p` でもClaude Codeで認証済みのトークンが使える（確認済み）
- **`claude -p` のオプション制約**: `--cwd` が存在しない（`cd` で代替が必要）

---

## 2. ユーザー要件

### 2.1 タスク管理

- [ ] spot taskを手動登録できる（CLI / Web UI）
- [ ] schedule taskをcron式で定期登録できる（CLI / Web UI）
- [ ] タスクごとに実行設定を指定できる（model, timeout, max_turns, mcp_config, work_dir, allowed_tools）
- [ ] Kanbanボードでタスクの状態を一覧・操作できる
- [ ] タスクの優先度（high/medium/low）で処理順を制御できる
- [ ] spot taskはschedule taskより優先して処理される

### 2.2 スケジュール管理

- [ ] cron式プリセット選択 + 手動入力
- [ ] 有効/無効トグル
- [ ] 手動即時実行（トリガー）
- [ ] 連続失敗時の自動無効化（閾値設定可能）
- [ ] セッション永続化（前回の会話を引き継ぐ）

### 2.3 プロンプト（スキル）管理

- [ ] プロンプトファイルをWeb UIからCRUDできる
- [ ] スケジュール作成時にプロンプトファイルを選択できる
- [ ] インラインプロンプトとファイル参照の両方に対応

### 2.4 実行ログ

- [ ] 全実行をSQLiteに記録（コスト, トークン数, 所要時間, model, schedule_id）
- [ ] ログをStatus / Model / Schedule(spot/schedule)でフィルタできる
- [ ] 日別コストチャートを表示
- [ ] ログ詳細でraw responseを確認できる

### 2.5 Web UI 全般

- [ ] 4つのページ: Kanban / Logs / Schedules / Prompts
- [ ] Python標準ライブラリのみ（外部依存なし）
- [ ] ダークテーマ
- [ ] Ctrl+Cで正常シャットダウンできる

---

## 3. 技術要件

### 3.1 実行エンジン

| 項目 | 要件 |
|---|---|
| 実行間隔 | cron 10分毎（最大10分の遅延を許容） |
| 1回の実行 | 1タスクのみ処理 |
| タイムアウト | タスクごとに設定可能（デフォルト300秒） |
| 排他制御 | mkdirロック（macOS互換、30分で自動解除） |
| 早期終了 | pendingタスクがなければclaude起動しない（sqliteソース時） |
| 作業ディレクトリ | `cd` で移動してから `claude -p` 実行（`--cwd` は存在しない） |
| 実行コマンドログ | 実行したclaude CLIコマンドをログファイルに記録 |

### 3.2 タスク実行フロー

```
run-tasks.sh
  1. ロック取得
  2. スケジュール展開（due → tasks INSERT、重複スキップ）
  3. プリフライト（次のpendingタスク特定、spot優先）
  4. 実行設定解決（task自体 → schedule → ソースデフォルト の優先順）
  5. claude -p 実行
  6. 結果パース
  7. タスクステータス同期（schedule由来タスクのcompleted/error反映）
  8. スケジュール結果処理（consecutive_failures更新、自動無効化）
  9. ログ記録（execution_logs + ファイルログ）
```

### 3.3 実行設定の解決順序（優先度高→低）

1. **タスク自体のカラム** — tasks.model, tasks.mcp_config 等
2. **スケジュール設定** — schedules.model, schedules.prompt 等（schedule_id付きタスクのみ）
3. **ソースデフォルト** — source.conf + config.env + prompt.txt

### 3.4 DB設計

#### tasks テーブル

| カラム | 型 | 用途 |
|---|---|---|
| id | INTEGER PK | |
| task_name | TEXT NOT NULL | タスク名 |
| task_type | TEXT NOT NULL | 分類ラベル（自由入力） |
| priority | TEXT | high / medium / low |
| status | TEXT | pending / in_progress / completed / error / needs_clarification / needs_review |
| input | TEXT | タスクの入力情報 |
| result | TEXT | 処理結果 |
| schedule_id | INTEGER FK | スケジュール由来の場合 |
| model | TEXT | 実行モデル（NULL=デフォルト） |
| timeout_seconds | INTEGER | タイムアウト |
| max_turns | INTEGER | 最大ターン |
| allowed_tools | TEXT | 許可ツール |
| mcp_config | TEXT | MCP設定ファイルパス |
| work_dir | TEXT | 作業ディレクトリ |

#### schedules テーブル

| カラム | 型 | 用途 |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT UNIQUE | スケジュール名 |
| cron_expr | TEXT | cron式（5フィールド） |
| enabled | INTEGER | 0/1 |
| backend | TEXT | claude / ollama / codex |
| model | TEXT | 実行モデル |
| prompt | TEXT | インラインプロンプト |
| prompt_file | TEXT | プロンプトファイルパス |
| work_dir | TEXT | 作業ディレクトリ |
| mcp_config | TEXT | MCP設定ファイルパス |
| allowed_tools | TEXT | 許可ツール |
| session_persistent | INTEGER | セッション永続化 0/1 |
| timeout_seconds | INTEGER | タイムアウト |
| max_turns | INTEGER | 最大ターン |
| next_run_at | TEXT | 次回実行時刻 |
| last_run_at | TEXT | 最終実行時刻 |
| last_status | TEXT | 最終実行結果 |
| consecutive_failures | INTEGER | 連続失敗数 |
| max_consecutive_failures | INTEGER | 自動無効化閾値 |

#### execution_logs テーブル

| カラム | 型 | 用途 |
|---|---|---|
| id | INTEGER PK | |
| timestamp | TEXT | 実行日時 |
| runner_type | TEXT | task_runner |
| task_source | TEXT | sqlite / github / notion |
| session_id | TEXT | セッションID |
| task_name | TEXT | タスク名 |
| task_type | TEXT | ラベル |
| status | TEXT | success / error / timeout / skipped |
| model | TEXT | 使用モデル |
| cost_usd | REAL | コスト |
| input_tokens | INTEGER | 入力トークン数 |
| output_tokens | INTEGER | 出力トークン数 |
| duration_seconds | INTEGER | 所要時間 |
| schedule_id | INTEGER | スケジュールID |
| result_summary | TEXT | 結果要約 |
| error_message | TEXT | エラー内容 |
| raw_response | TEXT | claude CLIの生レスポンス |

### 3.5 MCP接続

| サービス | 設定ファイル | 認証方式 | 確認状況 |
|---|---|---|---|
| Google Workspace | mcp-config-email.json | OAuth（スクリプト経由） | claude -p で動作確認済み |
| Sentry | mcp-config-sentry.json | HTTP OAuth | claude -p で動作確認済み |
| Notion | sources/notion/mcp-config.json | HTTP OAuth | 未確認 |
| プロジェクト固有 | .mcp.json（各PJ） | 混在 | work_dir + cd で利用可能 |

### 3.6 制約・禁止事項

- コード変更を伴うタスクは実行禁止（現フェーズ）
- メール送信・下書き作成は禁止
- `rm -rf`, `git push --force`, `drop`, `truncate` 等の破壊コマンドは禁止
- AIが新タスクを生成する場合は needs_review ステータス必須

---

## 4. UI設計要件

### 4.1 Kanban（/）

- 5カラム: Todo / In Progress / Done / Error / 要確認
- ドラッグ&ドロップでステータス変更
- タスク追加モーダル（詳細設定は折りたたみ）
- カードにラベルバッジ、優先度ドット、相対時間を表示

### 4.2 Logs（/logs）

- 統計: 総実行回数 / 成功率 / 合計コスト
- 日別コストチャート（14日間）
- フィルタ: Status / Model / Schedule(spot/schedule)
- テーブル: Timestamp, Task Name(scheduleバッジ付き), Status, Model, Cost, Duration, Source
- 行クリックで詳細モーダル（session_id, schedule_id, raw_response等）
- ページネーション（50件/ページ）

### 4.3 Schedules（/schedules）

- テーブル: ID, 有効, 名前, cron式, バックエンド, ラベル, 次回実行, 状態, 失敗数, 操作
- 有効/無効トグル
- 手動実行ボタン
- 追加モーダル:
  - 基本: 名前, cron式（プリセット+手入力）, ラベル（datalistサジェスト）, 優先度, バックエンド, モデル（select）
  - プロンプト: テキストエリア + ファイル選択（/api/promptsから動的読み込み）
  - MCP接続: datalistサジェスト（自由入力可）
  - 許可ツール: プリセットselect + カスタム入力
  - 詳細設定（折りたたみ）: タイムアウト, 最大ターン, 連続失敗上限, セッション永続, 作業ディレクトリ
- 名前クリックで詳細モーダル

### 4.4 Prompts（/prompts）

- カード型グリッド: ファイル名, 行数/サイズ, 更新日時, プレビュー
- クリックで編集モーダル（モノスペースフォントのtextarea）
- 新規作成 / 保存 / 削除
- ファイル名は英数字・ハイフン・アンダースコアのみ（.txt自動付与）

---

## 5. ランタイム環境

| 項目 | 要件 |
|---|---|
| OS | macOS（Homebrew前提） |
| シェル | bash 5.0+ |
| Python | 3.6+（標準ライブラリのみ） |
| 必須CLI | claude, jq, sqlite3, uuidgen, timeout, python3 |
| cron | macOS crontab（フルディスクアクセス権限必要） |
| ロック | mkdir（flock不可） |
| 時刻取得 | stat -f %m（macOS固有） |
| PATH | スクリプト冒頭で明示設定（cron環境対策） |

---

## 6. 今後の拡張候補（Phase 2以降）

- [ ] backend: ollama / codex 対応
- [ ] コード変更タスク（bug_fix, test_gen, docs）
- [ ] Slack通知（失敗時、自動無効化時）
- [ ] コストアラート（日次/月次の上限設定）
- [ ] タスク依存関係（A完了後にBを実行）
- [ ] Web UIでの認証（複数ユーザー対応）
- [ ] check-email.sh の完全廃止（schedules完全移行後）
