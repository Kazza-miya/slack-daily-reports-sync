# Slack Daily Reports to Notion Sync

Slackの日報チャンネルから「やったこと」を自動的に抽出し、Notionデータベースに同期するGitHub Actionsワークフローです。

## 機能

- Slackの日報メッセージから「やったこと」セクションを自動抽出
- ユーザーごと、日付ごとにNotionページに整理
- 重複防止機能付き
- 毎日20:05 JSTに自動実行

## セットアップ

### 1. リポジトリの作成
このコードをGitHubリポジトリにプッシュします。

### 2. GitHub Secretsの設定
リポジトリの Settings → Secrets and variables → Actions → New repository secret で以下を追加：

- `SLACK_BOT_TOKEN`: Slack Bot Token (xoxb-...)
- `SLACK_CHANNEL_ID`: 日報チャンネルのID (Cxxxx...)
- `NOTION_TOKEN`: Notion Integration Token (secret_...)
- `NOTION_DB_ID`: NotionデータベースのID

### 3. Notionデータベースの準備
- Titleプロパティ名が「Name」のデータベースを作成
- Notion Integrationをデータベースに接続

### 4. Slack Botの設定
- Bot Token Scopes: `channels:history`, `users:read`
- 日報チャンネルにBotを招待

## 動作仕様

- 日報フォーマット: 「やったこと」セクションを含むメッセージ
- 実行時間: 毎日20:05 JST (11:05 UTC)
- 手動実行: GitHub Actionsの「Run workflow」ボタンから可能
- 遡及期間: デフォルト3日分（LOOKBACK_DAYS環境変数で調整可能）

## ファイル構成

```
├── requirements.txt          # Python依存関係
├── sync_daily_reports.py     # メイン同期スクリプト
├── .github/workflows/sync.yml # GitHub Actionsワークフロー
└── README.md                 # このファイル
```
