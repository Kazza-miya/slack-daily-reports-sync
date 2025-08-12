# 🚀 Slack日報同期システム - 自動セットアップ手順

## 前提条件

1. **GitHub CLI** がインストールされていること
   ```bash
   # macOS
   brew install gh
   
   # Windows
   winget install GitHub.cli
   
   # Linux
   sudo apt install gh
   ```

2. **GitHub CLI** にログインしていること
   ```bash
   gh auth login
   ```

## 自動セットアップ実行

### 1. 依存関係のインストール
```bash
pip install -r requirements.txt
```

### 2. 自動セットアップスクリプト実行
```bash
python setup_automation.py
```

### 3. プロンプトに従って入力
- GitHubユーザー名または組織名を入力
- API認証情報を入力（または環境変数で設定）

## 環境変数での設定（推奨）

セキュリティのため、環境変数でAPI認証情報を設定することを推奨します：

```bash
export SLACK_BOT_TOKEN="your-slack-bot-token"
export SLACK_CHANNEL_ID="your-slack-channel-id"
export NOTION_TOKEN="your-notion-token"
export NOTION_DB_ID="your-notion-database-id"
```

## 自動セットアップの内容

スクリプトは以下の作業を自動実行します：

### ✅ ステップ1: GitHubリポジトリ作成
- 新しいリポジトリ `slack-daily-reports-sync` を作成
- 現在のコードをプッシュ

### ✅ ステップ2: GitHub Secrets設定
以下のSecretsを自動設定：
- `SLACK_BOT_TOKEN`: Slack Bot Token
- `SLACK_CHANNEL_ID`: Slack Channel ID
- `NOTION_TOKEN`: Notion Integration Token
- `NOTION_DB_ID`: Notion Database ID

### ✅ ステップ3: Notionデータベース確認
- データベースへのアクセス権限確認
- Titleプロパティ名の確認
- 必要に応じて修正案を提示

### ✅ ステップ4: Slack Bot確認
- Bot認証の確認
- チャンネルアクセス権限の確認
- 必要に応じて招待手順を提示

### ✅ ステップ5: ワークフローテスト実行
- GitHub Actionsワークフローを手動実行
- 実行状況の確認

## 手動設定が必要な場合

### Notionデータベースの修正
Titleプロパティ名が「Name」でない場合：

1. Notionデータベースを開く
2. プロパティ名を「Name」に変更
3. または `sync_daily_reports.py` の `ensure_person_page` 関数を修正

### Slack Botの招待
チャンネルアクセスが失敗した場合：

1. Slackで日報チャンネルを開く
2. `/invite @ボット名` を実行
3. またはチャンネル設定からBotを追加

## トラブルシューティング

### GitHub CLI関連
```bash
# 認証状態確認
gh auth status

# 再ログイン
gh auth login

# バージョン確認
gh --version
```

### Notion関連
- Integrationがデータベースに接続されているか確認
- データベースIDが正しいか確認

### Slack関連
- Bot Tokenが有効か確認
- Botに必要な権限が付与されているか確認
- チャンネルIDが正しいか確認

## 完了後の確認

1. **GitHub Actions** でワークフローが正常実行されているか確認
2. **Notionデータベース** にユーザーページが作成されているか確認
3. **Slack** でBotがチャンネルに参加しているか確認

## サポート

問題が発生した場合は、以下を確認してください：
- GitHub Actionsの実行ログ
- エラーメッセージの詳細
- 各APIの権限設定
