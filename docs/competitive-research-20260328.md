# 競合調査資料: AI タスクランナー / スケジューラ

調査日: 2026-03-28

## 調査目的

claude-task-runner と類似するプロジェクト・ツール・記事を調査し、ポジショニングと改善の方向性を把握する。

---

## 1. 直接的な競合（cron + claude -p でタスク処理）

### backporcher (montenegronyc/backporcher) — 10 stars
- https://github.com/montenegronyc/backporcher
- GitHub Issues をタスクキューとして使い、並列の Claude Code エージェントを起動。サンドボックスされた git worktree で作業、コーディネーターレビュー、CI ゲーティング、自動マージまで行う
- 言語: Python / 更新: 2026-03-25
- **比較**: 発想が最も近いが、タスクソースが GitHub Issues に固定。SQLite ログやKanban UIはない

### junior (JHostalek/junior) — 2 stars
- https://github.com/JHostalek/junior
- タスクをキューに入れ、ジョブをスケジュールし、Claude Code が隔離された git worktree で夜間に自動実行
- 言語: TypeScript / 更新: 2026-03-13
- **比較**: 「寝ている間にタスク処理」コンセプトが完全一致。非常に小規模

### agent-queue (ElectricJack/agent-queue) — 4 stars
- https://github.com/ElectricJack/agent-queue
- Discord からClaude Code エージェントを管理。レートリミット自動回復、夜間実行、プロジェクト横断キュー管理
- 言語: Python / 更新: 2026-03-27
- **比較**: インターフェースが Discord。タスクキュー+エージェント実行の構造は類似

### Continuum (zackbrooks84/continuum) — 17 stars
- https://github.com/zackbrooks84/continuum
- 非同期タスクキュー + 永続メモリ。セッション間コンテキスト維持。Claude Code, Remote Control, Claude.ai web で動作
- 言語: Python / 更新: 2026-03-27
- **比較**: 永続メモリ（セッション間コンテキスト維持）に重点

---

## 2. スケジューラ特化

### claude-code-scheduler (jshchnz/claude-code-scheduler) — 489 stars
- https://github.com/jshchnz/claude-code-scheduler
- 自然言語でスケジュール設定（「毎日9時」等）。macOS (launchd), Linux (crontab), Windows (Task Scheduler) 対応。git worktree 分離あり
- 言語: TypeScript / 更新: 2026-03-27 / 活発
- **比較**: cron登録を抽象化。タスクキュー管理なし、個別プロンプトのスケジュール実行のみ

### opencode-scheduler (different-ai/opencode-scheduler) — 236 stars
- https://github.com/different-ai/opencode-scheduler
- OpenCode (Claude Code 代替) 用スケジューラプラグイン。macOS は launchd、Linux は systemd
- 言語: TypeScript / 更新: 2026-03-27
- **比較**: OS ネイティブスケジューラの抽象化。タスクキュー管理なし

### runCLAUDErun
- https://runclauderun.com/
- macOS ネイティブアプリ。GUIでスケジュール実行管理。無料
- **比較**: GUI フロントエンド。ローカル完結、タスクキューなし

---

## 3. マルチエージェントオーケストレーション

### claude-squad (smtg-ai/claude-squad) — 6,666 stars
- https://github.com/smtg-ai/claude-squad
- 複数のAI端末エージェント（Claude Code, Codex, OpenCode, Amp）を管理するTUIツール
- 言語: Go / 更新: 2026-03-27
- **比較**: 対話的セッション管理が中心。タスクキューからの自動処理ではない

### Mission Control (builderz-labs/mission-control) — 3,481 stars
- https://github.com/builderz-labs/mission-control
- AI エージェントフリートのオーケストレーションダッシュボード。タスクディスパッチ、コスト追跡、マルチエージェントワークフロー。SQLite ベース、セルフホスト。cron 内蔵
- 言語: TypeScript / 更新: 2026-03-27 / 非常に活発
- **比較**: claude-task-runner を大幅にスケールアップしたもの。セットアップが重い

### Composio agent-orchestrator (ComposioHQ/agent-orchestrator) — 5,523 stars
- https://github.com/ComposioHQ/agent-orchestrator
- 並列コーディングエージェントのオーケストレーター。タスク計画、CI修正、マージコンフリクト、コードレビューを自律処理
- 言語: TypeScript / 更新: 2026-03-27 / 非常に活発
- **比較**: エンタープライズ向け。イベント駆動でcronベースではない

### Codexia (milisp/codexia) — 518 stars
- https://github.com/milisp/codexia
- Codex CLI + Claude Code のエージェントワークステーション。タスクスケジューラ、git worktree、リモートコントロール。Tauri v2 アプリ
- 言語: TypeScript / 更新: 2026-03-27
- **比較**: GUI ワークステーション。看板/SQLiteログなし

---

## 4. ループ/自律実行系

### Continuous Claude (AnandChowdhary/continuous-claude) — 1,273 stars
- https://github.com/AnandChowdhary/continuous-claude
- Claude Code を連続ループで実行。PR自動作成、CI待機、自動マージ。寝ている間にマルチステッププロジェクト完了
- 言語: Shell / 更新: 2026-03-27
- **比較**: 単一プロジェクトの連続実行。外部タスクキューなし

---

## 5. MCPベースのタスクキュー

### taskqueue-mcp (chriscarrollsmith/taskqueue-mcp) — 67 stars
- https://github.com/chriscarrollsmith/taskqueue-mcp
- AI エージェントワークフロー用の構造化タスクキューをMCPツールとして公開
- 言語: TypeScript / 更新: 2026-02-17
- **比較**: MCPサーバーとしてタスクキューを提供。スケジューラ部分なし

---

## 6. 汎用ワークフロープラットフォーム（AI統合あり）

### n8n — 181,415 stars
- https://github.com/n8n-io/n8n
- ビジュアルワークフロー自動化。AI エージェントをノードとして組み込み可。cron トリガー内蔵。セルフホスト対応
- **比較**: 何でもできるがオーバーキル

### Trigger.dev — 14,252 stars
- https://github.com/triggerdotdev/trigger.dev
- TypeScript ベースの AI エージェント&ワークフロープラットフォーム。cron、キュー、リトライ、可観測性
- **比較**: プロダクション向け。TypeScript でワークフロー定義が必要

---

## 7. Anthropic 公式の動き

### Claude Code /loop & /schedule
- https://code.claude.com/docs/en/scheduled-tasks
- 本体に組み込まれたスケジュール機能。セッション内最大50タスク、3日間有効
- **比較**: タスクキュー管理、タスクソース抽象化、看板UI、ログ蓄積は持たない

### Cowork Scheduled Tasks
- https://support.claude.com/en/articles/13854387-schedule-recurring-tasks-in-cowork
- Anthropic管理クラウドで定期タスク実行。PCオフでも動作。MCP サーバー継承
- **比較**: セルフホストではない。タスクソースの柔軟性なし

---

## 8. Qiita/Zenn の関連記事

### 設計思想が最も近い

| 記事 | 著者 | URL |
|---|---|---|
| Claude Codeを最大限に活用するタスクランナーを作った | tetsu.k (Nexta) | https://zenn.dev/nexta_/articles/claude-code-task-runner-automation |
| 寝ている間にAIがコードを改善してくれる仕組みを作った | きのすけ (GMOペパボ) | https://zenn.dev/kinosuke01/articles/69000f2bcbc784 |
| AIエージェントのワークフローをスキルで自動化する | kenfdev | https://zenn.dev/kenfdev/articles/e27d49b8dc12e4 |

- **Nexta記事**: タスク細分化→自動実行。時間分散、状態管理、優先度制御の5コンセプト。夜間・休日の自動実行で利用機会を2〜2.8倍に向上。claude-task-runner と設計思想がほぼ同じ
- **GMOペパボ記事**: GAS + スプレッドシート → GitHub Issue → Claude Code Action。タスクソースの別パターンとして興味深い
- **kenfdev記事**: bash while ループで `claude -p` を繰り返す「Ralph Loop」パターンとSkills。毎回新規セッションの設計が一致

### 実運用の障害事例（重要）

| 記事 | 問題 | 解決策 | URL |
|---|---|---|---|
| 定期実行が毎朝コケるので役割を分けた話 | OAuthトークン24h以内に失効 | サーバー(AI処理)+ローカル(送信)の2段構成 | https://qiita.com/iineineno03k/items/d7e34d96d2f382158e41 |
| AIエージェントのcronジョブ部分失敗をハンドリング | 部分失敗で成功率70% | 段階別ステータス+部分リトライで95%に | https://zenn.dev/anicca/articles/2026-02-26-cron-partial-failure |

### 運用ノウハウ

| 記事 | ポイント | URL |
|---|---|---|
| cron自動化のPATH問題 | cron環境でnvm管理のNode.jsが見つからない→PATH明示設定 | https://zenn.dev/trefac/articles/fe906ee1ad0a8a |
| Skillsを定期実行で自動化する方法 | サブスク認証で`claude -p`を無人実行（API Key不要） | https://zenn.dev/tenormusica/articles/claude-code-headless-subscription-discovery-2025 |
| ヘッドレスモード活用術 | `--allowedTools`, `--max-budget-usd`, `--max-turns` の3安全設定 | https://zenn.dev/sora_biz/articles/claude-code-headless-mode |
| Headless modeでLintを確実に自動修正 | allowedToolsのコロン+ワイルドカード形式の実用例 | https://zenn.dev/gmomedia/articles/3e9f1c25b8df3d |
| 自分好みの朝刊が届く仕組み | launchd + `claude -p`。macOSサンドボックス権限の回避策 | https://zenn.dev/aoi_umigishi/articles/936073d8dd16e9 |
| Claude Code Orchestrator | 複雑タスクを段階分解→並列サブタスク管理 | https://zenn.dev/mizchi/articles/claude-code-orchestrator |

### 公式スケジューラ機能の紹介記事

| 記事 | URL |
|---|---|
| 【神機能】Schedulerで寝てる間にコードレビューさせる方法 | https://qiita.com/emi_ndk/items/c81058b20f7ecafc698b |
| スケジューリング完全ガイド — /loop と Desktop scheduled tasks | https://qiita.com/kai_kou/items/329e8be64b397ff645a8 |
| クラウド版スケジュール機能の使い方5選 | https://zenn.dev/maya_honey/articles/a13378910d902c |
| 定期作業を自動化 — スケジュールタスク機能と/loop活用方法 | https://qiita.com/nogataka/items/23884e80a1716234f068 |
| スケジュールタスクで毎朝AIニュースを自動収集 | https://qiita.com/rf_p/items/23303cde99deddd24689 |

### その他関連ツール記事

| 記事 | URL |
|---|---|
| Claude Code Runner（Tauri製macOSアプリ、Rate Limit自動リトライ） | https://zenn.dev/owayo/articles/fda9deb6741958 |
| OpenClawをラズパイで回してみた | https://zenn.dev/dokusy/articles/2b2d8d3acad4fd |

---

## 9. ポジショニングマップ

```
シンプル ←────────────────────────────────→ 高機能
  │                                              │
  │  runCLAUDErun          claude-code-scheduler  │
  │  junior                                       │
  │       agent-queue                             │
  │            backporcher                        │
  │                                               │
  │         ★ claude-task-runner                  │
  │                                               │
  │              Continuous Claude                │
  │                   Codexia                     │
  │                        claude-squad           │
  │                             Mission Control   │
  │                                  Composio     │
  │                                               │
  └───────────────────────────────────────────────┘
  個別実行                              オーケストレーション
```

### claude-task-runner の独自性

| 特徴 | 他に同等のものがあるか |
|---|---|
| プラガブルなタスクソース（SQLite/GitHub/Notion切替） | **なし** — 各ツールは特定ソースに固定 |
| 外部依存なしの看板Web UI（Python標準ライブラリのみ） | **なし** |
| SQLiteログ蓄積 + コスト追跡 | Mission Control（より大規模） |
| 排他制御3層（mkdir + ステータス + stale検出） | backporcher（worktree分離のみ） |
| メールチェッカー別軸 + セッション永続化 | **なし** |
| allowedTools による権限制御 + 禁止コマンド一覧 | backporcher（サンドボックス） |
| 方向性ドリフト防止ルール | **なし** |

### 注目すべき動向

1. **Anthropic公式のスケジュール機能**（Cowork Scheduled Tasks）が急速に進化中。基本的な定期実行ニーズはカバーされつつある
2. **claude-code-scheduler (489 stars)** が最も人気のスケジューラ。自然言語設定が差別化要因
3. **Mission Control (3,481 stars)** がダッシュボード+オーケストレーション領域で急成長
4. **OAuthトークン失効問題**（Qiita記事）は無人運用の最大リスク。要対策

---

## 10. 改善の示唆

調査から得られた改善の方向性:

1. **部分失敗ハンドリング**: 成功率70%→95%の事例あり。段階別ステータス+部分リトライの導入検討
2. **OAuthトークン失効対策**: サブスク認証フォールバック or トークンリフレッシュの仕組み
3. **few-shot examples**: 過去の成功ログから自動抽出→プロンプトに注入で精度向上
4. **`--max-budget-usd`**: タスク種別ごとのbudget制限（現在はCLAUDE.mdに記載のみ、実装なし）
5. **git worktree分離**: backporcher/claude-code-scheduler が採用。コード変更タスク（Phase 2）で必要
